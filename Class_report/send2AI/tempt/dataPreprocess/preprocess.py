#!/usr/bin/env python3

from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

RAW_DIR = SCRIPT_DIR / "rawData"
PROCESSED_DIR = SCRIPT_DIR / "processedData"
REPORT_DIR = SCRIPT_DIR / "reports"

for directory in (RAW_DIR, PROCESSED_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# DriverAhead is optional because fetchKimi.py does not export it.
REQUIRED_COLUMNS = [
    "time",
    "rpm",
    "speed",
    "gear",
    "throttle",
    "brake",
    "distance",
    "rel_distance",
    "DistanceToDriverAhead",
    "acc_x",
    "acc_y",
    "acc_z",
    "x",
    "y",
    "z",
]

OPTIONAL_COLUMNS = ["DriverAhead"]

NUMERIC_COLUMNS = REQUIRED_COLUMNS.copy()

# Diagnostic ranges only. These are not definitive F1 car limits.
PLAUSIBILITY = {
    "speed": (0, 450),       # Assumed km/h
    "rpm": (0, 25000),
    "gear": (0, 10),
    "throttle": (0, 100),    # Assumed percentage
    "brake": (0, 100),       # Assumed percentage
    "rel_distance": (-0.05, 1.05),
}

LARGE_GAP_SECONDS = 0.50
TIME_TOLERANCE = 1e-9


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def infer_session(filename):
    """Infer event and session from filenames such as australiafp1.csv."""
    stem = filename.stem.lower()

    session_suffixes = ["fp1", "fp2", "fp3", "sq", "sr", "q", "r"]

    for suffix in session_suffixes:
        if stem.endswith(suffix):
            return {
                "event": stem[:-len(suffix)],
                "session": suffix,
            }

    return {
        "event": stem,
        "session": "unknown",
    }


def safe_numeric(series):
    """Convert a series to numeric; invalid strings become NaN."""
    return pd.to_numeric(series, errors="coerce")


def robust_summary(series):
    """Return a compact summary of numeric data."""
    values = pd.to_numeric(series, errors="coerce").dropna()

    if values.empty:
        return None

    return {
        "min": float(values.min()),
        "median": float(values.median()),
        "max": float(values.max()),
        "mean": float(values.mean()),
    }


def add_flag(flags, mask, label):
    """Add a diagnostic flag to rows matching a boolean mask."""
    mask = pd.Series(mask, index=flags.index).fillna(False).astype(bool)

    for index in flags.index[mask]:
        current = flags.at[index]
        flags.at[index] = (
            f"{current};{label}" if current else label
        )


def calculate_speed_acceleration(time_s, speed_kmh):
    """
    Calculate a diagnostic acceleration estimate from speed.

    Uses actual timestamp differences rather than assuming uniform
    sampling. This estimates longitudinal acceleration from speed;
    it is not a replacement for a validated accelerometer signal.
    """
    time_s = np.asarray(time_s, dtype=float)
    speed_ms = np.asarray(speed_kmh, dtype=float) / 3.6

    n = len(time_s)
    result = np.full(n, np.nan, dtype=float)

    if n < 2:
        return result

    dt = np.diff(time_s)
    dv = np.diff(speed_ms)

    valid = (
        np.isfinite(time_s[:-1])
        & np.isfinite(time_s[1:])
        & np.isfinite(speed_ms[:-1])
        & np.isfinite(speed_ms[1:])
        & (dt > TIME_TOLERANCE)
    )

    interval_acceleration = np.full(n - 1, np.nan, dtype=float)
    interval_acceleration[valid] = dv[valid] / dt[valid]

    sums = np.zeros(n, dtype=float)
    counts = np.zeros(n, dtype=int)

    for i, value in enumerate(interval_acceleration):
        if np.isfinite(value):
            sums[i] += value
            counts[i] += 1

            sums[i + 1] += value
            counts[i + 1] += 1

    valid_samples = counts > 0
    result[valid_samples] = (
        sums[valid_samples] / counts[valid_samples]
    )

    return result


def calculate_distance_diagnostics(time_s, speed_ms):
    """
    Estimate distance increments using trapezoidal speed integration.

    Invalid or non-positive time intervals are left as NaN.
    """
    time_s = np.asarray(time_s, dtype=float)
    speed_ms = np.asarray(speed_ms, dtype=float)

    n = len(time_s)

    increments = np.full(n, np.nan, dtype=float)

    if n < 2:
        return increments

    dt = np.diff(time_s)

    valid = (
        np.isfinite(time_s[:-1])
        & np.isfinite(time_s[1:])
        & np.isfinite(speed_ms[:-1])
        & np.isfinite(speed_ms[1:])
        & (dt > TIME_TOLERANCE)
    )

    interval_distance = np.full(n - 1, np.nan, dtype=float)

    interval_distance[valid] = (
        0.5
        * (speed_ms[:-1][valid] + speed_ms[1:][valid])
        * dt[valid]
    )

    # Store each interval's distance at its ending sample.
    increments[1:] = interval_distance

    return increments


# ============================================================
# PREPROCESS ONE CSV
# ============================================================

def preprocess_file(csv_path):
    print(f"\nProcessing: {csv_path.name}")

    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [str(column).strip() for column in df.columns]

    original_rows = len(df)
    original_columns = list(df.columns)

    # --------------------------------------------------------
    # 1. Validate required columns
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    missing_optional_columns = [
        column
        for column in OPTIONAL_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        warnings.warn(
            f"{csv_path.name}: missing required columns: "
            f"{missing_columns}"
        )

        for column in missing_columns:
            df[column] = np.nan

    # Preserve source row order for traceability.
    df["source_row"] = np.arange(len(df))

    # --------------------------------------------------------
    # 2. Convert numeric columns
    # --------------------------------------------------------

    conversion_failures = {}

    for column in NUMERIC_COLUMNS:
        original_nonempty = df[column].notna()
        converted = safe_numeric(df[column])

        conversion_failures[column] = int(
            (original_nonempty & converted.isna()).sum()
        )

        df[column] = converted

    # --------------------------------------------------------
    # 3. Initialize row-level flags
    # --------------------------------------------------------

    df["quality_flags"] = ""

    for column in NUMERIC_COLUMNS:
        add_flag(
            df["quality_flags"],
            df[column].isna(),
            f"missing_or_invalid_{column}",
        )

    # DriverAhead is optional.
    if "DriverAhead" in df.columns:
        df["DriverAhead"] = (
            df["DriverAhead"]
            .astype("string")
            .str.strip()
            .replace({
                "": pd.NA,
                "None": pd.NA,
                "none": pd.NA,
                "nan": pd.NA,
            })
        )

    # --------------------------------------------------------
    # 4. Timestamp validation
    # --------------------------------------------------------

    time_values = df["time"].to_numpy(dtype=float)

    repeated_timestamp = np.zeros(len(df), dtype=bool)
    reversed_timestamp = np.zeros(len(df), dtype=bool)
    large_sampling_gap = np.zeros(len(df), dtype=bool)

    if len(df) > 1:
        dt = np.diff(time_values)

        repeated = (
            np.isfinite(time_values[:-1])
            & np.isfinite(time_values[1:])
            & (np.abs(dt) <= TIME_TOLERANCE)
        )

        reversed_ = (
            np.isfinite(time_values[:-1])
            & np.isfinite(time_values[1:])
            & (dt < -TIME_TOLERANCE)
        )

        large_gap = (
            np.isfinite(dt)
            & (dt > LARGE_GAP_SECONDS)
        )

        repeated_timestamp[1:] |= repeated
        reversed_timestamp[1:] |= reversed_
        large_sampling_gap[1:] |= large_gap

    add_flag(
        df["quality_flags"],
        repeated_timestamp,
        "repeated_timestamp",
    )

    add_flag(
        df["quality_flags"],
        reversed_timestamp,
        "time_reversal",
    )

    add_flag(
        df["quality_flags"],
        large_sampling_gap,
        "large_sampling_gap",
    )

    # Do not sort or modify timestamps automatically.
    # Source row order is preserved for investigation.

    # --------------------------------------------------------
    # 5. Duplicate-row detection
    # --------------------------------------------------------

    comparison_columns = [
        column for column in original_columns
        if column in df.columns
    ]

    duplicate_rows = df.duplicated(
        subset=comparison_columns,
        keep=False,
    )

    add_flag(
        df["quality_flags"],
        duplicate_rows,
        "exact_duplicate_row",
    )

    # --------------------------------------------------------
    # 6. Basic plausibility checks
    # --------------------------------------------------------

    for column, (minimum, maximum) in PLAUSIBILITY.items():
        values = df[column]

        outside_range = (
            values.notna()
            & ((values < minimum) | (values > maximum))
        )

        add_flag(
            df["quality_flags"],
            outside_range,
            f"{column}_outside_diagnostic_range",
        )

    # Large negative distance changes may indicate resets or
    # extraction artefacts. They are flagged, not corrected.
    distance_change = df["distance"].diff()

    add_flag(
        df["quality_flags"],
        distance_change < -1.0,
        "distance_decreased",
    )

    relative_distance_change = df["rel_distance"].diff()

    add_flag(
        df["quality_flags"],
        relative_distance_change < -0.25,
        "relative_distance_discontinuity",
    )

    # --------------------------------------------------------
    # 7. Derived acceleration
    # --------------------------------------------------------

    df["speed_ms"] = df["speed"] / 3.6

    df["accel_from_speed_ms2"] = calculate_speed_acceleration(
        df["time"].to_numpy(dtype=float),
        df["speed"].to_numpy(dtype=float),
    )

    # Exploratory comparison only. Interpretation depends on the
    # units and sign convention of the source acc_x field.
    df["acc_x_minus_speed_accel"] = (
        df["acc_x"] - df["accel_from_speed_ms2"]
    )

    # --------------------------------------------------------
    # 8. Distance integration diagnostics
    # --------------------------------------------------------

    df["integrated_distance_increment_m"] = (
        calculate_distance_diagnostics(
            df["time"].to_numpy(dtype=float),
            df["speed_ms"].to_numpy(dtype=float),
        )
    )

    # Cumulative integrated distance is diagnostic only.
    df["integrated_distance_m"] = (
        df["integrated_distance_increment_m"]
        .fillna(0.0)
        .cumsum()
    )

    df["distance_increment_m"] = df["distance"].diff()

    df["distance_increment_error_m"] = (
        df["distance_increment_m"]
        - df["integrated_distance_increment_m"]
    )

    # --------------------------------------------------------
    # 9. Sampling statistics
    # --------------------------------------------------------

    valid_times = df["time"].dropna()

    if len(valid_times) > 1:
        timestamp_differences = valid_times.diff().dropna()

        positive_differences = timestamp_differences[
            timestamp_differences > TIME_TOLERANCE
        ]

        sampling_summary = {
            "median_positive_dt_s": (
                float(positive_differences.median())
                if not positive_differences.empty else None
            ),
            "min_positive_dt_s": (
                float(positive_differences.min())
                if not positive_differences.empty else None
            ),
            "max_positive_dt_s": (
                float(positive_differences.max())
                if not positive_differences.empty else None
            ),
            "nonpositive_dt_count": int(
                (timestamp_differences <= TIME_TOLERANCE).sum()
            ),
        }
    else:
        sampling_summary = {
            "median_positive_dt_s": None,
            "min_positive_dt_s": None,
            "max_positive_dt_s": None,
            "nonpositive_dt_count": 0,
        }

    # --------------------------------------------------------
    # 10. Flag counts
    # --------------------------------------------------------

    flag_counts = {}

    exploded_flags = (
        df["quality_flags"]
        .fillna("")
        .str.split(";")
        .explode()
    )

    for flag, count in exploded_flags.value_counts().items():
        if flag:
            flag_counts[flag] = int(count)

    flagged = df[df["quality_flags"].ne("")]
    flagged_row_count = int(len(flagged))

    # --------------------------------------------------------
    # 11. Session report
    # --------------------------------------------------------

    metadata = infer_session(csv_path)

    report = {
        "file": csv_path.name,
        "event": metadata["event"],
        "session": metadata["session"],

        "rows_original": int(original_rows),
        "rows_output": int(len(df)),
        "flagged_row_count": flagged_row_count,

        "columns_missing_in_source": missing_columns,
        "optional_columns_missing": missing_optional_columns,
        "numeric_conversion_failures": conversion_failures,

        "missing_values_by_column": {
            column: int(df[column].isna().sum())
            for column in REQUIRED_COLUMNS
        },

        "timestamp": {
            "first_s": (
                float(valid_times.iloc[0])
                if not valid_times.empty else None
            ),
            "last_s": (
                float(valid_times.iloc[-1])
                if not valid_times.empty else None
            ),
            **sampling_summary,
        },

        "numeric_summaries": {
            column: robust_summary(df[column])
            for column in [
                "time", "rpm", "speed", "gear", "throttle",
                "brake", "distance", "rel_distance",
                "DistanceToDriverAhead", "acc_x", "acc_y", "acc_z",
                "x", "y", "z",
            ]
        },

        "quality_flag_counts": flag_counts,

        "distance_diagnostics": {
            "supplied_distance_increment_m": robust_summary(
                df["distance_increment_m"]
            ),
            "integrated_distance_increment_m": robust_summary(
                df["integrated_distance_increment_m"]
            ),
            "distance_increment_error_m": robust_summary(
                df["distance_increment_error_m"]
            ),
            "total_supplied_distance_change_m": (
                float(df["distance"].iloc[-1] - df["distance"].iloc[0])
                if df["distance"].notna().sum() >= 2 else None
            ),
            "total_integrated_distance_m": (
                float(df["integrated_distance_m"].iloc[-1])
                if not df.empty else None
            ),
        },

        "interpretation_notes": [
            "Raw CSV was not modified.",
            "Flagged rows were retained.",
            "Source row order and timestamps were preserved.",
            "Speed is assumed to be in km/h for derived calculations.",
            "Throttle and brake are assumed to be percentages for range checks.",
            "Acceleration comparison requires compatible units and sign convention.",
            "Integrated distance is diagnostic and does not replace source distance.",
            "Missing DriverAhead values do not prove there was no car ahead.",
            "Row counts alone do not establish complete session coverage.",
        ],
    }

    # --------------------------------------------------------
    # 12. Save processed CSV and reports
    # --------------------------------------------------------

    output_csv = PROCESSED_DIR / csv_path.name
    output_json = REPORT_DIR / f"{csv_path.stem}_report.json"
    output_flags = REPORT_DIR / f"{csv_path.stem}_flagged_rows.csv"

    df.to_csv(
        output_csv,
        index=False,
        encoding="utf-8",
    )

    with output_json.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    flagged.to_csv(
        output_flags,
        index=False,
        encoding="utf-8",
    )

    print(f"  Rows: {original_rows:,}")
    print(f"  Flagged rows: {flagged_row_count:,}")
    print(f"  Processed CSV: {output_csv.name}")

    return report


# ============================================================
# PROCESS ALL RAW CSV FILES
# ============================================================

def main():
    csv_files = sorted(
        path
        for path in RAW_DIR.glob("*.csv")
        if path.is_file()
    )

    if not csv_files:
        print(f"No raw CSV files found in: {RAW_DIR}")
        return

    print(f"Raw directory:       {RAW_DIR}")
    print(f"Processed directory: {PROCESSED_DIR}")
    print(f"Reports directory:   {REPORT_DIR}")
    print(f"CSV files discovered: {len(csv_files)}")

    reports = []
    failures = []

    for csv_path in csv_files:
        try:
            report = preprocess_file(csv_path)
            reports.append(report)

        except Exception as exc:
            failures.append({
                "file": csv_path.name,
                "error": f"{type(exc).__name__}: {exc}",
            })

            print(
                f"[ERROR] {csv_path.name}: "
                f"{type(exc).__name__}: {exc}"
            )

    # --------------------------------------------------------
    # Combined session summary
    # --------------------------------------------------------

    summary_rows = []

    for report in reports:
        timestamp = report["timestamp"]

        summary_rows.append({
            "file": report["file"],
            "event": report["event"],
            "session": report["session"],
            "rows_original": report["rows_original"],
            "rows_output": report["rows_output"],
            "flagged_row_count": report["flagged_row_count"],
            "first_time_s": timestamp["first_s"],
            "last_time_s": timestamp["last_s"],
            "median_dt_s": timestamp["median_positive_dt_s"],
            "min_dt_s": timestamp["min_positive_dt_s"],
            "max_dt_s": timestamp["max_positive_dt_s"],
            "nonpositive_dt_count":
                timestamp["nonpositive_dt_count"],
            "exact_duplicate_rows":
                report["quality_flag_counts"].get(
                    "exact_duplicate_row", 0
                ),
            "missing_columns": ", ".join(
                report["columns_missing_in_source"]
            ),
        })

    summary_path = REPORT_DIR / "all_sessions_summary.csv"

    pd.DataFrame(summary_rows).to_csv(
        summary_path,
        index=False,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Processing failure report
    # --------------------------------------------------------

    failure_path = REPORT_DIR / "processing_failures.json"

    with failure_path.open("w", encoding="utf-8") as file:
        json.dump(failures, file, indent=2, ensure_ascii=False)

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("PREPROCESSING COMPLETE")
    print("=" * 60)
    print(f"Raw CSVs discovered: {len(csv_files)}")
    print(f"Sessions processed:  {len(reports)}")
    print(f"Sessions failed:     {len(failures)}")
    print(f"Summary:             {summary_path}")

    if failures:
        print(
            "\nWARNING: Some sessions failed. "
            "Check reports/processing_failures.json."
        )


if __name__ == "__main__":
    main()