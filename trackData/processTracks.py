#!/usr/bin/env python3
"""Build a provenance-first, frontend-ready F1 circuit data catalog.

Inputs (root is the directory containing this script by default):
  circuitMap.json
  raw/sections/*.json
  raw/sessions/<event>/<session>/{corners.json,cor.json,weather.json,rcm.json}
  raw/images/eventMap.json, raw/images/svg/*, raw/images/webp/*
  Optional Straight Mode CSV references:
    raw/straight_mode_zones_2026/<event-slug>.csv
    raw/active_aero_zones/<event-slug>.csv
    references/straight_mode_zones_2026/<event-slug>.csv
    trackData_Australia/extracted/australia/straight_mode_zones_2026.csv (Australia only)

Outputs (under --out-root, default = root):
  processed/track_catalog.json
  processed/<event-slug>/master_track.json and normalized CSV files   (EVENT-LEVEL references)
  processed/<event-slug>/sessions/<resolved-session-slug>/{weather,race_control}.{csv,json}, session_manifest.json
  reports/process_tracks_report.json
  reports/straight_mode_map_candidates.csv        (all events, image-space review candidates)
  reports/straight_mode_map_review_sheet.png      (contact sheet of every per-event review image)

Scope rules enforced here:
  * Geometry, corners, markers and sections are EVENT-LEVEL references. Their source folder is kept only as
    provenance (source_folder_label); they are never labelled as session data.
  * Weather and race-control are SESSION-LEVEL. The session is resolved from an explicit session field in the
    payload when one exists; otherwise the raw folder label is kept and flagged session_verification=unverified_session.
    LayoutLapSession (inside corners.json) describes the historical lap the layout was traced from; it is NEVER
    used to relabel weather/race-control data.
  * Straight Mode (2026 active aero) offsets come only from explicit CSV references. Image detections are
    image-space review candidates and are never converted into offsets or lap distances.

The script never edits raw sources, infers track units, averages different sessions,
reconstructs track geometry from images, or invents unavailable zone data.
Core track processing uses the standard library. Optional map annotation extraction uses Pillow.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Core extraction remains usable without Pillow.
    Image = None  # type: ignore[assignment,misc]
    ImageDraw = None  # type: ignore[assignment,misc]
    ImageFont = None  # type: ignore[assignment,misc]

SCHEMA_VERSION = "4.0"
SCRIPT_NAME = "processTracks.py"
EXCLUDED_EVENT_LABELS = ["Bahrain Grand Prix", "Chinese Grand Prix", "Japanese Grand Prix", "Spanish Grand Prix"]
EXCLUDED_EVENTS = {
    "bahrain grand prix",
    "chinese grand prix",
    "china grand prix",
    "japanese grand prix",
    "japan grand prix",
    "spanish grand prix",
    "spain grand prix",
}
SESSION_ALIASES = {
    "race": "Race", "r": "Race", "grand prix": "Race",
    "qualifying": "Qualifying", "q": "Qualifying", "quali": "Qualifying",
    "sprint": "Sprint", "s": "Sprint", "sprint race": "Sprint",
    "sprint qualifying": "Sprint Qualifying", "sprint shootout": "Sprint Qualifying", "sq": "Sprint Qualifying", "ss": "Sprint Qualifying",
    "practice 1": "Practice 1", "fp1": "Practice 1", "free practice 1": "Practice 1", "p1": "Practice 1",
    "practice 2": "Practice 2", "fp2": "Practice 2", "free practice 2": "Practice 2", "p2": "Practice 2",
    "practice 3": "Practice 3", "fp3": "Practice 3", "free practice 3": "Practice 3", "p3": "Practice 3",
}
# Top-level payload keys that may carry the session a weather/race-control file belongs to.
# LayoutLapSession is deliberately NOT here: it is the session of the layout reference lap.
PAYLOAD_SESSION_KEYS = ("session", "Session", "SessionName", "session_name", "SessionType", "session_type")
MIN_GEOMETRY_POINTS = 20
FORBIDDEN_TERM_PATTERN = r"\b" + "d" + "rs" + r"\b"  # retired rear-wing terminology must never appear in outputs
SESSION_PRIORITY = (
    "Race",
    "Qualifying",
    "Sprint",
    "Sprint Qualifying",
    "Sprint Shootout",
    "Practice 3",
    "Practice 2",
    "Practice 1",
)
WEATHER_FIELD_MAP = {
    "wT": "session_time_s",
    "wAT": "ambient_air_temp_c",
    "wH": "relative_humidity_pct",
    "wP": "pressure_mbar",
    "wR": "rainfall",
    "wTT": "track_temp_c",
    "wWD": "wind_direction_deg",
    "wWS": "wind_speed_mps",
}
RCM_FIELD_MAP = {
    "time": "timestamp",
    "cat": "category",
    "msg": "message",
    "status": "status",
    "flag": "flag",
    "scope": "scope",
    "sector": "sector",
    "dNum": "driver_number",
    "lap": "lap",
}
GEOMETRY_HEADERS = [
    "point_index", "x_raw", "y_raw", "source_file", "source_folder_label",
    "coordinate_reference", "units", "source_fields_json",
]
CORNER_HEADERS = [
    "corner_index", "corner_number", "corner_label", "corner_letter", "x_raw", "y_raw",
    "angle_deg_source", "distance_source", "mv_distance_source", "source_file",
    "source_folder_label", "source_fields_json",
]
SECTION_HEADERS = [
    "section_index", "section_label", "start_percent", "end_percent",
    "source_file", "source_format", "source_fields_json",
]
LAYOUT_SECTION_HEADERS = [
    "section_index", "section_type", "start_percent", "end_percent",
    "start_distance_source", "end_distance_source", "source_file", "source_folder_label",
    "source_fields_json",
]
MARKER_HEADERS = [
    "marker_index", "marker_number", "marker_letter", "x_raw", "y_raw", "angle_deg_source",
    "distance_source", "mv_distance_source", "source_file", "source_folder_label", "source_fields_json",
]
MINI_SECTOR_HEADERS = [
    "marker_number", "source_track_point_index", "x_raw", "y_raw", "source_file", "source_folder_label",
]
AERO_HEADERS = [
    "zone_id", "mode", "normal_grip_activation_offset_m_after_corner", "normal_grip_corner",
    "low_grip_activation_offset_m_after_corner", "low_grip_corner", "source_note",
    "source_file", "verification_status", "source_fields_json",
]
MAP_ANNOTATION_HEADERS = [
    "annotation_id", "event_name", "annotation_class", "candidate_confidence", "candidate_basis",
    "source_image_webp", "source_image_svg", "svg_semantic_text_elements",
    "image_width_px", "image_height_px", "coordinate_space", "component_red_pixel_count",
    "bbox_x_min_px", "bbox_y_min_px", "bbox_x_max_px_inclusive", "bbox_y_max_px_inclusive",
    "centroid_x_px", "centroid_y_px", "bbox_x_min_norm", "bbox_y_min_norm", "bbox_x_max_norm", "bbox_y_max_norm",
    "bbox_aspect_ratio", "bbox_fill_ratio", "manual_review_status", "activation_offset_status", "source_note",
]
WEATHER_HEADERS = [
    "event_name", "raw_folder_session", "resolved_session", "session_verification", "sample_index", "session_time_s", "ambient_air_temp_c", "relative_humidity_pct",
    "pressure_mbar", "rainfall", "track_temp_c", "wind_direction_deg", "wind_speed_mps",
    "source_file", "source_fields_json",
]
RCM_HEADERS = [
    "event_name", "raw_folder_session", "resolved_session", "session_verification", "message_index", "timestamp", "category", "message", "status", "flag", "scope",
    "sector", "driver_number", "lap", "source_file", "source_fields_json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).strip().casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def slug(value: str) -> str:
    text = re.sub(r"[^\w.-]+", "-", str(value).strip(), flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-._")
    return text.lower() or "unnamed"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def nullish(value: Any) -> Any:
    if isinstance(value, str) and value.strip().casefold() in {"", "none", "null", "nan", "n/a"}:
        return None
    return json_safe(value)


def parse_number(value: Any) -> float | None:
    value = nullish(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def rel_path(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, root: Path, kind: str, folder_label: str | None = None) -> dict[str, Any]:
    return {
        "file": rel_path(path, root),
        "kind": kind,
        "folder_label": folder_label,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            cooked = {}
            for key, value in row.items():
                if isinstance(value, (dict, list, tuple)):
                    cooked[key] = json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"))
                elif value is None:
                    cooked[key] = ""
                else:
                    cooked[key] = value
            writer.writerow(cooked)


def read_csv_path(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def resolve_map_path(root: Path, raw_root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value_norm = value.strip().replace("\\", "/")
    relative = Path(value_norm)
    candidates = [root / relative, raw_root / relative]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_case_insensitive(directory: Path, filename: str) -> Path | None:
    direct = directory / filename
    if direct.is_file():
        return direct
    if not directory.is_dir():
        return None
    name_fold = filename.casefold()
    for child in directory.iterdir():
        if child.is_file() and child.name.casefold() == name_fold:
            return child
    return None


def is_excluded(event: str) -> bool:
    label = norm_text(event)
    if label in EXCLUDED_EVENTS:
        return True
    return "bahrain" in label or label in {
        "china grand prix", "chinese grand prix", "japan grand prix",
        "japanese grand prix", "spain grand prix", "spanish grand prix",
    }


def session_rank(name: str) -> tuple[int, str]:
    label = norm_text(name)
    priorities = [norm_text(s) for s in SESSION_PRIORITY]
    if label in priorities:
        return priorities.index(label), label
    # Accept common naming variants without changing the intended preference order.
    if "race" == label or label.endswith(" race"):
        return 0, label
    if "qualifying" in label and "sprint" not in label:
        return 1, label
    if label == "sprint":
        return 2, label
    if ("sprint" in label and ("qualifying" in label or "shootout" in label)):
        return 3, label
    if "practice 3" in label or "free practice 3" in label:
        return 5, label
    if "practice 2" in label or "free practice 2" in label:
        return 6, label
    if "practice 1" in label or "free practice 1" in label:
        return 7, label
    return len(SESSION_PRIORITY) + 1, label


def canonical_session(value: Any) -> str | None:
    """Map a session label to its canonical name; None when the label is not recognized."""
    return SESSION_ALIASES.get(norm_text(value))


def payload_session_label(payload: Any) -> tuple[str | None, str | None]:
    """Return (key, value) for an explicit top-level session field in a weather/race-control payload."""
    if isinstance(payload, dict):
        for key in PAYLOAD_SESSION_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return key, value.strip()
    return None, None


def rcm_utc_span(payload: Any) -> dict[str, Any] | None:
    """Timestamp evidence from race-control payloads (corroboration only; never used to relabel a session)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("time"), list):
        return None
    stamps = [str(t) for t in payload["time"] if isinstance(t, str) and re.match(r"\d{4}-\d{2}-\d{2}T", t)]
    if not stamps:
        return None
    return {"first_utc": min(stamps), "last_utc": max(stamps), "utc_dates": sorted({t[:10] for t in stamps})}


def resolve_session(event: str, folder: str, payloads: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve the canonical session for one raw folder from explicit payload metadata.

    payloads maps source kind ('weather', 'rcm') to the parsed JSON. Folder provenance is always preserved.
    """
    warnings: list[dict[str, Any]] = []
    folder_canonical = canonical_session(folder)
    found: list[dict[str, Any]] = []
    for kind, payload in payloads.items():
        key, value = payload_session_label(payload)
        if value is not None:
            found.append({"source": kind, "key": key, "value": value, "canonical": canonical_session(value)})
    resolution: dict[str, Any] = {
        "raw_folder_session": folder,
        "raw_folder_canonical": folder_canonical,
        "payload_session_fields": found,
        "timestamp_evidence": {k: rcm_utc_span(p) for k, p in payloads.items() if rcm_utc_span(p)},
    }
    recognized = sorted({f["canonical"] for f in found if f["canonical"]})
    if not found:
        resolution.update({
            "resolved_session": folder_canonical or folder,
            "session_verification": "unverified_session",
            "resolution": "raw folder label retained; weather/race-control payloads carry no session field",
        })
    elif len(recognized) > 1:
        resolution.update({
            "resolved_session": folder_canonical or folder,
            "session_verification": "unverified_session",
            "resolution": "weather and race-control payloads name different sessions; raw folder label retained",
        })
        warnings.append({"severity": "error", "event": event, "stage": "session_provenance", "folder_session": folder,
                         "payload_sessions": found, "chosen_resolution": resolution["resolved_session"],
                         "warning": f"Payload session fields disagree with each other in folder '{folder}'; folder label kept."})
    elif not recognized:
        resolution.update({
            "resolved_session": folder_canonical or folder,
            "session_verification": "unverified_session",
            "resolution": "payload session label not recognized; raw folder label retained",
        })
        warnings.append({"severity": "warning", "event": event, "stage": "session_provenance", "folder_session": folder,
                         "payload_sessions": found, "chosen_resolution": resolution["resolved_session"],
                         "warning": f"Payload session label(s) {[f['value'] for f in found]} are not a recognized session in folder '{folder}'; folder label kept."})
    elif folder_canonical == recognized[0]:
        resolution.update({
            "resolved_session": recognized[0],
            "session_verification": "payload_confirms_folder",
            "resolution": "payload session field matches folder label",
        })
    else:
        resolution.update({
            "resolved_session": recognized[0],
            "session_verification": "payload_overrides_folder",
            "resolution": "explicit payload session field takes precedence over folder label; both preserved",
        })
        warnings.append({"severity": "warning", "event": event, "stage": "session_provenance", "folder_session": folder,
                         "payload_sessions": found, "chosen_resolution": recognized[0],
                         "warning": f"Folder '{folder}' holds data whose payload says '{found[0]['value']}'; resolved to '{recognized[0]}'. Both labels are preserved in the session manifest."})
    return resolution, warnings


def assign_session_slugs(event: str, resolutions: dict[str, dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Name output folders by resolved session. Two folders resolving to the same session are never merged."""
    slugs: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    for folder in sorted(resolutions, key=lambda f: (session_rank(resolutions[f]["resolved_session"]), 0 if resolutions[f]["session_verification"] != "payload_overrides_folder" else 1, f)):
        base = slug(resolutions[folder]["resolved_session"])
        if base not in owners:
            owners[base] = folder
            slugs[folder] = base
        else:
            slugs[folder] = f"{base}__folder-{slug(folder)}"
            warnings.append({"severity": "warning", "event": event, "stage": "session_collision", "folders": [owners[base], folder],
                             "resolved_session": resolutions[folder]["resolved_session"],
                             "chosen_resolution": f"'{owners[base]}' keeps '{base}'; '{folder}' exported separately as '{slugs[folder]}'. Records were not merged.",
                             "warning": f"Folders '{owners[base]}' and '{folder}' both resolve to session '{resolutions[folder]['resolved_session']}'. Review whether they are duplicates."})
    return slugs, warnings


def validate_sections(rows: list[dict[str, Any]]) -> list[str]:
    """Return actionable problems for a section list expressed as percentages of a lap."""
    problems: list[str] = []
    if not rows:
        return problems
    for row in rows:
        s, e = row.get("start_percent"), row.get("end_percent")
        if s is None or e is None:
            problems.append(f"Section {row['section_index']} has a missing/non-finite boundary.")
        elif e <= s:
            problems.append(f"Section {row['section_index']} has end_percent <= start_percent.")
    complete = [r for r in rows if r.get("start_percent") is not None and r.get("end_percent") is not None]
    if complete:
        if abs(complete[0]["start_percent"]) > 0.05:
            problems.append(f"Sections do not start at 0% (first starts at {complete[0]['start_percent']}).")
        if abs(complete[-1]["end_percent"] - 100.0) > 0.05:
            problems.append(f"Sections do not end at 100% (last ends at {complete[-1]['end_percent']}).")
        for a, b in zip(complete, complete[1:]):
            if abs(a["end_percent"] - b["start_percent"]) > 0.05:
                problems.append(f"Gap/overlap between sections {a['section_index']} and {b['section_index']} ({a['end_percent']} -> {b['start_percent']}).")
    return problems


def load_circuit_map(root: Path, raw_root: Path) -> tuple[dict[str, Any], Path]:
    candidates = [root / "circuitMap.json", raw_root / "circuitMap.json"]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise FileNotFoundError("circuitMap.json was not found at project root or raw/circuitMap.json")
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError(f"Invalid circuit map schema in {path}: expected an object containing an events list")
    return data, path


def mapped_events(root: Path, raw_root: Path, cmap: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    section_dir = raw_root / "sections"
    for entry in cmap.get("events", []):
        if not isinstance(entry, dict):
            warnings.append({"severity": "warning", "stage": "circuit_map", "warning": "Non-object event entry ignored."})
            continue
        event = entry.get("event_name") or entry.get("event") or entry.get("name")
        if not isinstance(event, str) or not event.strip():
            warnings.append({"severity": "warning", "stage": "circuit_map", "warning": f"Event mapping with no usable name ignored: {entry!r}"})
            continue
        event = event.strip()
        if is_excluded(event):
            continue
        event_key = norm_text(event)
        if event_key in seen:
            warnings.append({"severity": "warning", "event": event, "stage": "circuit_map", "warning": "Duplicate event mapping; first mapping retained."})
            continue
        seen.add(event_key)
        section_path = resolve_map_path(root, raw_root, entry.get("local_path") or entry.get("section_local_path"))
        if section_path is None:
            file_value = entry.get("section_file") or entry.get("section_file_stem") or entry.get("section_stem") or entry.get("section")
            if isinstance(file_value, str) and file_value.strip():
                filename = Path(file_value.replace("\\", "/")).name
                if not filename.casefold().endswith(".json"):
                    filename += ".json"
                section_path = find_case_insensitive(section_dir, filename)
        output.append({"event_name": event, "event_slug": slug(event), "map_entry": entry, "section_path": section_path})
    return output


def match_event_session_directory(sessions_root: Path, event: str, warnings: list[dict[str, Any]]) -> Path | None:
    if not sessions_root.is_dir():
        return None
    direct = sessions_root / event
    if direct.is_dir():
        return direct
    target = norm_text(event)
    matches = [p for p in sessions_root.iterdir() if p.is_dir() and norm_text(p.name) == target]
    if len(matches) == 1:
        warnings.append({"severity": "warning", "event": event, "stage": "session_matching", "warning": f"Used exact normalized folder-name match '{matches[0].name}' because the canonical folder name was absent."})
        return matches[0]
    if len(matches) > 1:
        warnings.append({"severity": "error", "event": event, "stage": "session_matching", "warning": f"Ambiguous session folders match this event: {[p.name for p in matches]}. No session folder was selected."})
    return None


def list_sessions(event_dir: Path | None) -> list[Path]:
    if event_dir is None or not event_dir.is_dir():
        return []
    return sorted((p for p in event_dir.iterdir() if p.is_dir()), key=lambda p: session_rank(p.name))


def find_named_json(session_dir: Path, filename: str) -> Path | None:
    return find_case_insensitive(session_dir, filename)


def get_parallel_arrays(payload: Any) -> dict[str, list[Any]]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, list)}


def parallel_length(arrays: dict[str, list[Any]]) -> int:
    return max((len(values) for values in arrays.values()), default=0)


def parallel_rows(arrays: dict[str, list[Any]]) -> list[dict[str, Any]]:
    length = parallel_length(arrays)
    return [{key: (values[index] if index < len(values) else None) for key, values in arrays.items()} for index in range(length)]


def source_metadata(payload: Any, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"source_file": source}
    keys = (
        "CircuitKey", "CircuitId", "CircuitID", "CircuitName", "Location", "CountryName", "CountryKey",
        "CountryIocCode", "LayoutYear", "LayoutRound", "LayoutRaceDate", "LayoutMeetingKey",
        "LayoutMeetingName", "LayoutMeetingOfficialName", "LayoutLapDriverNumber", "LayoutLapNumber",
        "LayoutLapSession", "LayoutLapTime", "LayoutLapStartDate", "LayoutLapStartSessionTime",
        "LayoutLapSessionStartTime", "TrackLength", "TrackLengthKm", "Length", "Rotation", "rotation",
        "PitLossNormal", "PitLossSC", "PitLossVSC",
    )
    result = {"source_file": source}
    for key in keys:
        value = payload.get(key)
        if not isinstance(value, (dict, list)):
            result[key] = json_safe(value)
    return result


def candidate_geometry(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Return valid TrackX/TrackY points; reject partial, tiny, degenerate or non-numeric geometry."""
    if not isinstance(payload, dict):
        return [], "geometry source is not a JSON object"
    containers = [payload]
    for key in ("geometry", "track", "circuit", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    pairs = [("TrackX", "TrackY"), ("track_x", "track_y"), ("trackX", "trackY"), ("X", "Y")]
    for container in containers:
        for x_key, y_key in pairs:
            xs, ys = container.get(x_key), container.get(y_key)
            if not isinstance(xs, list) and not isinstance(ys, list):
                continue
            # X/Y arrays in a corner-reference object are markers unless there is evidence they are track points.
            if x_key == "X" and any(k in container for k in ("CornerNumber", "CornerLabel", "CornerLetter", "CornerDistance", "Number", "corners")):
                continue
            if not isinstance(xs, list) or not isinstance(ys, list):
                return [], f"geometry has only one coordinate array ({x_key}/{y_key})"
            if len(xs) != len(ys):
                return [], f"coordinate-array length mismatch: {x_key}={len(xs)}, {y_key}={len(ys)}"
            if len(xs) < MIN_GEOMETRY_POINTS:
                return [], f"{x_key}/{y_key} has only {len(xs)} points; at least {MIN_GEOMETRY_POINTS} are required for a track outline"
            points = []
            for index, (x, y) in enumerate(zip(xs, ys)):
                nx, ny = parse_number(x), parse_number(y)
                if nx is None or ny is None:
                    return [], f"non-numeric or non-finite coordinate at index {index}"
                points.append({"point_index": index, "x_raw": nx, "y_raw": ny})
            if (max(p["x_raw"] for p in points) == min(p["x_raw"] for p in points)
                    or max(p["y_raw"] for p in points) == min(p["y_raw"] for p in points)):
                return [], f"{x_key}/{y_key} is degenerate (zero extent on at least one axis)"
            return points, None
    return [], "no recognized continuous coordinate arrays found"


def extract_named_records(payload: Any, key_names: Iterable[str]) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(payload, dict):
        return [], None
    for key in key_names:
        value = payload.get(key)
        if isinstance(value, list):
            rows = []
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    rows.append({"_record_index": index, **item})
                else:
                    rows.append({"_record_index": index, "value": item})
            return rows, key
    return [], None


def records_from_parallel(payload: Any, family: str) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Pair parallel arrays only when they share the anchor (number) array's length; never pad or truncate."""
    if not isinstance(payload, dict):
        return [], None, []
    if family == "corners":
        relevant = {
            "CornerNumber", "CornerLabel", "CornerLetter", "CornerX", "CornerY", "CornerAngle", "CornerDistance", "CornerMVDistance",
            "Number", "X", "Y", "Angle", "Distance", "MVDistance",
        }
        anchors = ("CornerNumber", "Number")
    elif family == "marshal_lights":
        relevant = {"MarshalLightNumber", "MarshalLightX", "MarshalLightY", "MarshalLightAngle", "MarshalLightDistance", "MarshalLightMVDistance"}
        anchors = ("MarshalLightNumber",)
    else:
        relevant = {"MarshalSectorNumber", "MarshalSectorX", "MarshalSectorY", "MarshalSectorAngle", "MarshalSectorDistance", "MarshalSectorMVDistance"}
        anchors = ("MarshalSectorNumber",)
    arrays = {k: v for k, v in payload.items() if k in relevant and isinstance(v, list)}
    if not arrays:
        return [], None, []
    anchor = next((k for k in anchors if k in arrays), None)
    if anchor is not None:
        length = len(arrays[anchor])
    else:
        counts: dict[int, int] = {}
        for values in arrays.values():
            counts[len(values)] = counts.get(len(values), 0) + 1
        length = max(counts, key=lambda n: (counts[n], n))
    paired = {k: v for k, v in arrays.items() if len(v) == length}
    unpaired = {k: len(v) for k, v in arrays.items() if len(v) != length}
    warnings = []
    if unpaired:
        warnings.append(f"{family}: arrays {unpaired} do not match the {length}-record index set ({anchor or 'modal length'}); "
                        "they were not paired by index and are not exported to the record CSV.")
    return parallel_rows(paired), "parallel arrays", warnings


def marker_rows(records: list[dict[str, Any]], family: str, source_file: str, session: str | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if family == "corners":
            number_keys = ("Number", "CornerNumber", "number", "corner_number")
            label_keys = ("CornerLabel", "Label", "label")
            letter_keys = ("Letter", "CornerLetter", "letter")
            x_keys = ("X", "CornerX", "x")
            y_keys = ("Y", "CornerY", "y")
            angle_keys = ("Angle", "CornerAngle", "angle")
            distance_keys = ("Distance", "CornerDistance", "distance")
            mv_keys = ("MVDistance", "CornerMVDistance", "mv_distance")
        elif family == "marshal_lights":
            number_keys = ("Number", "MarshalLightNumber", "number")
            label_keys = ()
            letter_keys = ("Letter", "MarshalLightLetter", "letter")
            x_keys = ("X", "MarshalLightX", "x")
            y_keys = ("Y", "MarshalLightY", "y")
            angle_keys = ("Angle", "MarshalLightAngle", "angle")
            distance_keys = ("Distance", "MarshalLightDistance", "distance")
            mv_keys = ("MVDistance", "MarshalLightMVDistance", "mv_distance")
        else:
            number_keys = ("Number", "MarshalSectorNumber", "number")
            label_keys = ()
            letter_keys = ("Letter", "MarshalSectorLetter", "letter")
            x_keys = ("X", "MarshalSectorX", "x")
            y_keys = ("Y", "MarshalSectorY", "y")
            angle_keys = ("Angle", "MarshalSectorAngle", "angle")
            distance_keys = ("Distance", "MarshalSectorDistance", "distance")
            mv_keys = ("MVDistance", "MarshalSectorMVDistance", "mv_distance")

        def get_first(keys: Iterable[str]) -> Any:
            for key in keys:
                if key in record:
                    return nullish(record.get(key))
            return None

        x, y = parse_number(get_first(x_keys)), parse_number(get_first(y_keys))
        output.append({
            "marker_index": index,
            "marker_number": get_first(number_keys),
            "marker_letter": get_first(letter_keys),
            "x_raw": x,
            "y_raw": y,
            "angle_deg_source": parse_number(get_first(angle_keys)),
            "distance_source": parse_number(get_first(distance_keys)),
            "mv_distance_source": parse_number(get_first(mv_keys)),
            "source_file": source_file,
            "source_folder_label": session,
            "source_fields_json": record,
            **({
                "corner_index": index,
                "corner_number": get_first(number_keys),
                "corner_label": get_first(label_keys) or str(get_first(number_keys) or ""),
                "corner_letter": get_first(letter_keys),
            } if family == "corners" else {}),
        })
    return output


def extract_corner_records(payload: Any, source_file: str, session: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    # Preferred object-array schema used by cor.json.
    direct, source_array = extract_named_records(payload, ("corners", "Corners", "corner_records", "cornerRecords"))
    if direct and any(any(k in row for k in ("Number", "CornerNumber", "Distance", "CornerDistance", "X", "CornerX")) for row in direct):
        rows = marker_rows(direct, "corners", source_file, session)
        for row in rows:
            row["source_fields_json"] = {k: v for k, v in row["source_fields_json"].items() if k != "_record_index"}
        return rows, warnings
    # Parallel-array schema used by corners.json.
    parallel, _, parallel_warnings = records_from_parallel(payload, "corners")
    warnings.extend(parallel_warnings)
    if parallel:
        rows = marker_rows(parallel, "corners", source_file, session)
        return rows, warnings
    return [], warnings


def extract_marker_family(payload: Any, family: str, source_file: str, session: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    key_names = {
        "marshal_lights": ("marshal_lights", "MarshalLights", "marshalLights"),
        "marshal_sectors": ("marshal_sectors", "MarshalSectors", "marshalSectors"),
    }[family]
    direct, _ = extract_named_records(payload, key_names)
    warnings: list[str] = []
    if direct:
        return marker_rows(direct, family, source_file, session), warnings
    parallel, _, parallel_warnings = records_from_parallel(payload, family)
    warnings.extend(parallel_warnings)
    if parallel:
        return marker_rows(parallel, family, source_file, session), warnings
    return [], warnings


def extract_section_file(payload: Any, source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    output: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                label, start, end = item[0], item[1], item[2]
                output.append({
                    "section_index": index,
                    "section_label": nullish(label),
                    "start_percent": parse_number(start),
                    "end_percent": parse_number(end),
                    "source_file": source_file,
                    "source_format": "array_tuple_label_start_end",
                    "source_fields_json": list(item),
                })
            elif isinstance(item, dict):
                label = next((item.get(k) for k in ("section_label", "Section", "section", "type", "name", "label") if k in item), None)
                start = next((item.get(k) for k in ("start_percent", "SectionStartPercent", "start", "StartPercent") if k in item), None)
                end = next((item.get(k) for k in ("end_percent", "SectionEndPercent", "end", "EndPercent") if k in item), None)
                output.append({"section_index": index, "section_label": nullish(label), "start_percent": parse_number(start), "end_percent": parse_number(end),
                               "source_file": source_file, "source_format": "object_record", "source_fields_json": item})
            else:
                warnings.append(f"Section entry {index} is not a recognized tuple/object; retained only in source inventory.")
    elif isinstance(payload, dict):
        entries, _ = extract_named_records(payload, ("sections", "Sections", "track_sections", "trackSections"))
        if entries:
            return extract_section_file(entries, source_file)
        aliases = {
            "section_label": ("Section", "section", "SectionLabel", "section_label", "SectionType", "section_type"),
            "start_percent": ("SectionStartPercent", "start_percent", "StartPercent"),
            "end_percent": ("SectionEndPercent", "end_percent", "EndPercent"),
        }
        fields = {}
        for output_key, keys in aliases.items():
            for key in keys:
                if isinstance(payload.get(key), list):
                    fields[output_key] = payload[key]
                    break
        lengths = {len(v) for v in fields.values()}
        if len(lengths) > 1:
            warnings.append("Section parallel arrays have unequal lengths; not paired by index: " + ", ".join(f"{k}={len(v)}" for k, v in fields.items()))
            fields = {}
        if fields:
            for index, record in enumerate(parallel_rows(fields)):
                output.append({"section_index": index, "section_label": nullish(record.get("section_label")),
                               "start_percent": parse_number(record.get("start_percent")), "end_percent": parse_number(record.get("end_percent")),
                               "source_file": source_file, "source_format": "parallel_arrays", "source_fields_json": record})
        else:
            warnings.append("Section JSON object has no recognized section records/arrays.")
    else:
        warnings.append("Section JSON root is neither a list nor an object.")
    for row in output:
        s, e = row.get("start_percent"), row.get("end_percent")
        if s is not None and e is not None and not (0 <= s <= 100 and 0 <= e <= 100):
            warnings.append(f"Section {row['section_index']} has percentage boundary outside 0..100.")
        if s is not None and e is not None and e < s:
            warnings.append(f"Section {row['section_index']} has end_percent before start_percent.")
    return output, warnings


def extract_layout_section_metadata(payload: Any, source_file: str, folder: str | None) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Pair SectionType/Start/End arrays only when they share one length. `Section` (a different length in
    every inspected source; equal to the corner count) is preserved raw and is never index-paired."""
    if not isinstance(payload, dict):
        return [], [], {}
    aligned_keys = {
        "section_type": "SectionType", "start_percent": "SectionStartPercent", "end_percent": "SectionEndPercent",
        "start_distance_source": "SectionStartDistance", "end_distance_source": "SectionEndDistance",
    }
    present = {out: payload[src] for out, src in aligned_keys.items() if isinstance(payload.get(src), list)}
    warnings: list[str] = []
    unpaired: dict[str, Any] = {}
    if isinstance(payload.get("Section"), list):
        unpaired["Section"] = payload["Section"]
    if not present:
        return [], warnings, unpaired
    counts: dict[int, int] = {}
    for values in present.values():
        counts[len(values)] = counts.get(len(values), 0) + 1
    length = max(counts, key=lambda n: (counts[n], n))
    group = {k: v for k, v in present.items() if len(v) == length}
    for out, values in present.items():
        if len(values) != length:
            unpaired[aligned_keys[out]] = values
    if "start_percent" not in group or "end_percent" not in group:
        for out, values in group.items():
            unpaired[aligned_keys[out]] = values
        warnings.append("Layout section start/end percentage arrays do not share a length; section arrays preserved raw and not paired.")
        return [], warnings, unpaired
    if "Section" in unpaired and len(unpaired["Section"]) != length:
        warnings.append(f"Layout array 'Section' has {len(unpaired['Section'])} values versus {length} section records "
                        f"({aligned_keys.get('section_type')}/percent arrays); preserved raw and not paired by index.")
    rows = []
    for index, source_row in enumerate(parallel_rows(group)):
        rows.append({
            "section_index": index,
            "section_type": nullish(source_row.get("section_type")),
            "start_percent": parse_number(source_row.get("start_percent")),
            "end_percent": parse_number(source_row.get("end_percent")),
            "start_distance_source": parse_number(source_row.get("start_distance_source")),
            "end_distance_source": parse_number(source_row.get("end_distance_source")),
            "source_file": source_file,
            "source_folder_label": folder,
            "source_fields_json": source_row,
        })
    return rows, warnings, unpaired


def extract_mini_sector_markers(payload: Any, geometry: list[dict[str, Any]], source_file: str, session: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("MiniSectorIndex"), list):
        return [], []
    points_by_index = {p["point_index"]: p for p in geometry}
    warnings: list[str] = []
    output = []
    for marker_index, raw_index in enumerate(payload["MiniSectorIndex"], start=1):
        parsed = parse_number(raw_index)
        if parsed is None or not parsed.is_integer():
            warnings.append(f"Mini-sector marker {marker_index} has a non-integer source point index: {raw_index!r}")
            continue
        source_index = int(parsed)
        point = points_by_index.get(source_index)
        if point is None:
            warnings.append(f"Mini-sector marker {marker_index} references unavailable track point index {source_index}.")
        output.append({
            "marker_number": marker_index,
            "source_track_point_index": source_index,
            "x_raw": point.get("x_raw") if point else None,
            "y_raw": point.get("y_raw") if point else None,
            "source_file": source_file,
            "source_folder_label": session,
        })
    return output, warnings


def array_payload_rows(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if isinstance(payload, list):
        return [({str(k): nullish(v) for k, v in item.items()} if isinstance(item, dict) else {"value": nullish(item)}) for item in payload], warnings
    if not isinstance(payload, dict):
        return [], ["Expected a JSON object of parallel arrays or a list of records."]
    arrays = get_parallel_arrays(payload)
    if not arrays:
        return [], ["No arrays found in JSON payload."]
    lengths = {key: len(values) for key, values in arrays.items()}
    if len(set(lengths.values())) > 1:
        modal = max(set(lengths.values()), key=lambda n: (list(lengths.values()).count(n), n))
        off = {k: n for k, n in lengths.items() if n != modal}
        warnings.append(f"Parallel arrays have unequal lengths ({lengths}); arrays {off} were not paired by index with the {modal}-record set and are omitted from rows.")
        arrays = {k: v for k, v in arrays.items() if len(v) == modal}
    return [{key: nullish(value) for key, value in row.items()} for row in parallel_rows(arrays)], warnings


def extract_weather(payload: Any, source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    raw_rows, warnings = array_payload_rows(payload)
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        normalized = {field: nullish(raw.get(source_key)) for source_key, field in WEATHER_FIELD_MAP.items()}
        normalized.update({"sample_index": index, "source_file": source_file, "source_fields_json": raw})
        rows.append(normalized)
    return rows, warnings


def extract_race_control(payload: Any, source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    raw_rows, warnings = array_payload_rows(payload)
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        normalized = {field: nullish(raw.get(source_key)) for source_key, field in RCM_FIELD_MAP.items()}
        normalized.update({
            "message_index": index,
            "source_file": source_file,
            "source_fields_json": raw,
        })
        rows.append(normalized)
    return rows, warnings


def load_image_map(root: Path, raw_root: Path, warnings: list[dict[str, Any]]) -> tuple[dict[str, str], Path | None]:
    candidates = [raw_root / "images" / "eventMap.json", root / "eventMap.json", raw_root / "eventMap.json"]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        warnings.append({"severity": "warning", "stage": "image_mapping", "warning": "eventMap.json not found; circuits will have no image-map association."})
        return {}, None
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append({"severity": "error", "stage": "image_mapping", "file": rel_path(path, root), "warning": f"Could not parse eventMap.json: {exc}"})
        return {}, path
    if isinstance(data, dict) and isinstance(data.get("events"), dict):
        data = data["events"]
    event_to_svg: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            # The project map uses SVG filename -> event name; the reverse form is accepted too.
            if isinstance(value, str) and key.lower().endswith(".svg"):
                event_to_svg[norm_text(value)] = Path(key.replace("\\", "/")).name
            elif isinstance(value, str) and value.lower().endswith(".svg"):
                event_to_svg[norm_text(key)] = Path(value.replace("\\", "/")).name
            elif isinstance(value, dict):
                event_name = value.get("event_name") or value.get("event")
                filename = value.get("svg") or value.get("file") or value.get("image")
                if isinstance(event_name, str) and isinstance(filename, str):
                    event_to_svg[norm_text(event_name)] = Path(filename.replace("\\", "/")).name
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            event_name = item.get("event_name") or item.get("event")
            filename = item.get("svg") or item.get("file") or item.get("image")
            if isinstance(event_name, str) and isinstance(filename, str):
                event_to_svg[norm_text(event_name)] = Path(filename.replace("\\", "/")).name
    return event_to_svg, path


def image_assets(root: Path, raw_root: Path, event: str, event_to_svg: dict[str, str], image_map_path: Path | None) -> dict[str, Any]:
    mapped_name = event_to_svg.get(norm_text(event))
    if not mapped_name:
        return {
            "event_map_file": rel_path(image_map_path, root), "mapped": False,
            "mapping_filename": None, "svg": {"path": None, "exists": False},
            "webp": {"path": None, "exists": False},
            "status": "no_event_map_entry",
            "note": "Image assets are retained for display. WebP red annotation components may be exported as image-space candidates only; no track-distance or corner anchor is inferred.",
        }
    svg_root, webp_root = raw_root / "images" / "svg", raw_root / "images" / "webp"
    svg_path = find_case_insensitive(svg_root, mapped_name)
    webp_name = Path(mapped_name).stem + ".webp"
    webp_path = find_case_insensitive(webp_root, webp_name)
    return {
        "event_map_file": rel_path(image_map_path, root), "mapped": True, "mapping_filename": mapped_name,
        "svg": {"path": rel_path(svg_path, root), "exists": svg_path is not None},
        "webp": {"path": rel_path(webp_path, root), "exists": webp_path is not None},
        "status": "assets_found" if svg_path or webp_path else "mapping_exists_but_assets_missing",
        "note": "Image assets are retained for display. WebP red annotation components may be exported as image-space candidates only; no track-distance or corner anchor is inferred.",
    }


def _red_annotation_pixel(rgb: tuple[int, int, int]) -> bool:
    """Detect saturated red pixels while excluding magenta circuit-line pixels.

    These circuit SVGs are image-traced paths rather than semantically tagged vector
    layers, so pixel color is used only to nominate regions for human review.
    """
    r, g, b = rgb
    mx = max(r, g, b)
    mn = min(r, g, b)
    delta = mx - mn
    if r < 50 or mx != r or delta == 0 or (delta / mx) < (70 / 255):
        return False
    # Since red must be the maximum channel, this is the red-channel HSV hue branch.
    hue = (60.0 * (g - b) / delta) % 360.0
    return hue <= 14.0 or hue >= 346.0


def extract_map_red_annotations(
    webp_path: Path | None, svg_path: Path | None, event: str, root: Path, preview_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Extract red map-image components into pixel-space review candidates.

    This deliberately does not invent corner-relative activation offsets or lap distance.
    Red components can include a zone stroke, a label, or both; every record requires
    visual review before being used as a measured Straight Mode zone.
    """
    warnings: list[str] = []
    info: dict[str, Any] = {
        "file": "straight_mode_map_annotations.csv",
        "preview_file": None,
        "candidate_count": 0,
        "zone_like_candidate_count": 0,
        "compact_annotation_count": 0,
        "coordinate_space": "source WebP image pixels; origin at top-left",
        "telemetry_aligned": False,
        "activation_offsets_extracted": False,
        "status": "not_available",
    }
    if webp_path is None or not webp_path.is_file():
        info["status"] = "webp_asset_unavailable"
        return [], info, warnings
    if Image is None or ImageDraw is None:
        info["status"] = "pillow_not_installed"
        warnings.append("Map annotation extraction skipped because Pillow is unavailable; install it with 'python -m pip install pillow'.")
        return [], info, warnings

    try:
        image = Image.open(webp_path).convert("RGB")
        width, height = image.size
        # RGB bytes avoid Pillow's deprecated Image.getdata() API.
        pixel_bytes = image.tobytes()
    except (OSError, ValueError) as exc:
        info["status"] = "webp_unreadable"
        warnings.append(f"Could not inspect mapped WebP image {rel_path(webp_path, root)}: {exc}")
        return [], info, warnings

    svg_description = None
    svg_text_elements = 0
    if svg_path is not None and svg_path.is_file():
        try:
            svg_text = svg_path.read_text(encoding="utf-8", errors="replace")
            desc_match = re.search(r'<desc[^>]*>(.*?)</desc>', svg_text, flags=re.IGNORECASE | re.DOTALL)
            if desc_match:
                svg_description = re.sub(r"\s+", " ", desc_match.group(1)).strip()
            else:
                # ImageTracer exports often store their provenance in a root desc= attribute.
                attr_match = re.search(r'\bdesc\s*=\s*"([^"]*)"', svg_text[:10000], flags=re.IGNORECASE | re.DOTALL)
                svg_description = re.sub(r"\s+", " ", attr_match.group(1)).strip() if attr_match else None
            svg_text_elements = len(re.findall(r'<text(?:\s|>)', svg_text, flags=re.IGNORECASE))
        except OSError:
            pass

    # Make the mask as a byte array. Connected components are computed with an iterative
    # flood fill so the extractor needs only Pillow, not OpenCV or NumPy.
    mask = bytearray()
    for pixel_index in range(0, len(pixel_bytes), 3):
        mask.append(1 if _red_annotation_pixel((pixel_bytes[pixel_index], pixel_bytes[pixel_index + 1], pixel_bytes[pixel_index + 2])) else 0)
    red_pixel_count = sum(mask)
    del pixel_bytes
    components: list[dict[str, Any]] = []
    total = width * height
    for start in range(total):
        if not mask[start]:
            continue
        mask[start] = 0
        stack = [start]
        area = 0
        x_min, y_min, x_max, y_max = width, height, -1, -1
        sum_x = sum_y = 0
        while stack:
            current = stack.pop()
            y, x = divmod(current, width)
            area += 1
            sum_x += x
            sum_y += y
            if x < x_min: x_min = x
            if x > x_max: x_max = x
            if y < y_min: y_min = y
            if y > y_max: y_max = y
            y0 = max(0, y - 1); y1 = min(height - 1, y + 1)
            x0 = max(0, x - 1); x1 = min(width - 1, x + 1)
            for ny in range(y0, y1 + 1):
                base = ny * width
                for nx in range(x0, x1 + 1):
                    neighbor = base + nx
                    if mask[neighbor]:
                        mask[neighbor] = 0
                        stack.append(neighbor)
        bw, bh = x_max - x_min + 1, y_max - y_min + 1
        long_dim, short_dim = max(bw, bh), min(bw, bh)
        density = area / max(1, bw * bh)
        aspect = long_dim / max(1, short_dim)
        # Discard tiny speckles, but retain compact items (possible labels) as low-confidence review rows.
        if area < 500 or long_dim < 80:
            continue
        # Shape-based nomination only. A thin, long red component hugging the track edge is the hatch-mark
        # pattern seen on the supplied Australian map; a compact blob is more likely a label or legend swatch.
        if aspect >= 5.0:
            annotation_class, confidence = "red_edge_strip_candidate", ("medium" if area >= 1500 else "low")
            basis = f"thin elongated red component (aspect {aspect:.1f}, fill {density:.2f})"
        elif density < 0.35:
            annotation_class, confidence = "red_curved_region_candidate", ("medium" if area >= 1500 else "low")
            basis = f"sparse red component spanning a large box (fill {density:.2f}), consistent with a curved edge pattern"
        else:
            annotation_class, confidence = "compact_red_annotation", "low"
            basis = f"compact red component (aspect {aspect:.1f}, fill {density:.2f}); more likely a label or swatch than a zone"
        components.append({
            "area": area, "x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max,
            "width": bw, "height": bh, "density": density, "aspect": aspect,
            "centroid_x": sum_x / area, "centroid_y": sum_y / area,
            "annotation_class": annotation_class, "confidence": confidence, "basis": basis,
        })

    # Stable IDs in approximate reading order, not assumed lap/traversal order.
    components.sort(key=lambda c: (c["y_min"], c["x_min"], -c["area"]))
    source_webp = rel_path(webp_path, root) or webp_path.as_posix()
    source_svg = rel_path(svg_path, root) if svg_path and svg_path.is_file() else None
    rows: list[dict[str, Any]] = []
    for idx, comp in enumerate(components, 1):
        x0, y0, x1, y1 = comp["x_min"], comp["y_min"], comp["x_max"], comp["y_max"]
        rows.append({
            "annotation_id": f"{slug(event)}-MAP-{idx:02d}",
            "event_name": event,
            "annotation_class": comp["annotation_class"],
            "candidate_confidence": comp["confidence"],
            "candidate_basis": comp["basis"],
            "source_image_webp": source_webp,
            "source_image_svg": source_svg,
            "svg_semantic_text_elements": svg_text_elements,
            "image_width_px": width, "image_height_px": height,
            "coordinate_space": "webp_image_pixels_top_left_origin",
            "component_red_pixel_count": comp["area"],
            "bbox_x_min_px": x0, "bbox_y_min_px": y0,
            "bbox_x_max_px_inclusive": x1, "bbox_y_max_px_inclusive": y1,
            "centroid_x_px": round(comp["centroid_x"], 3), "centroid_y_px": round(comp["centroid_y"], 3),
            "bbox_x_min_norm": round(x0 / max(1, width - 1), 6),
            "bbox_y_min_norm": round(y0 / max(1, height - 1), 6),
            "bbox_x_max_norm": round(x1 / max(1, width - 1), 6),
            "bbox_y_max_norm": round(y1 / max(1, height - 1), 6),
            "bbox_aspect_ratio": round(comp["aspect"], 3),
            "bbox_fill_ratio": round(comp["density"], 6),
            "manual_review_status": "required_before_any_use",
            "activation_offset_status": "none_image_space_only",
            "source_note": "Image-space red component for human review. Not a measured Straight Mode zone: no corner anchor, activation offset or lap distance is inferred. Overtake detection/activation callouts are a separate feature and are not classified here.",
        })

    # Generate a review copy without modifying the original map.
    if components:
        try:
            preview = Image.open(webp_path).convert("RGB")
            draw = ImageDraw.Draw(preview)
            for idx, comp in enumerate(components, 1):
                if comp["annotation_class"] == "compact_red_annotation":
                    color = (80, 170, 255)
                elif comp["confidence"] == "medium":
                    color = (35, 255, 90)
                else:
                    color = (255, 220, 50)
                box = (comp["x_min"], comp["y_min"], comp["x_max"], comp["y_max"])
                draw.rectangle(box, outline=color, width=3)
                label = f"MAP-{idx:02d} {comp['annotation_class'].split('_')[1]}"
                tx, ty = comp["x_min"], max(0, comp["y_min"] - 16)
                draw.text((tx, ty), label, fill=color, stroke_width=2, stroke_fill=(0, 0, 0))
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview.save(preview_path)
            info["preview_file"] = rel_path(preview_path, root)
        except (OSError, ValueError) as exc:
            warnings.append(f"Could not write map annotation preview: {exc}")

    info.update({
        "source_image_webp": source_webp, "source_image_svg": source_svg,
        "image_width_px": width, "image_height_px": height,
        "svg_description": svg_description,
        "svg_semantic_text_elements": svg_text_elements,
        "image_method": "red-hue connected-component segmentation on WebP pixels; SVG retained as source/provenance",
        "raw_red_pixel_count": red_pixel_count,
        "candidate_count": len(rows),
        "zone_like_candidate_count": sum(1 for row in rows if row["annotation_class"] != "compact_red_annotation"),
        "compact_annotation_count": sum(1 for row in rows if row["annotation_class"] == "compact_red_annotation"),
        "coordinate_space": "source WebP pixels (origin top-left) and normalized image ratios only",
        "telemetry_aligned": False, "activation_offsets_extracted": False,
        "all_candidates_unverified": True,
        "status": "visual_candidates_need_review" if rows else ("red_pixels_found_no_qualifying_regions" if red_pixel_count else "no_red_regions_detected"),
    })
    if svg_description and "imagetracer" in svg_description.casefold() and svg_text_elements == 0:
        info["svg_semantics_note"] = "SVG is an ImageTracer-rendered vector trace with no <text> elements; text/zone identity is not encoded as semantic SVG labels."
    elif svg_text_elements == 0:
        info["svg_semantics_note"] = "SVG contains no <text> elements; zone identity is not encoded as semantic SVG labels, so WebP segmentation is the only visual evidence."
    else:
        info["svg_semantics_note"] = f"SVG has {svg_text_elements} <text> element(s); they are counted but not used to assign Straight Mode activation offsets."
    if not rows:
        warnings.append("No sufficiently large red image regions were extracted; this does not prove the circuit has no 2026 Straight Mode zones.")
    return rows, info, warnings


def write_review_sheet(entries: list[tuple[str, Path]], out_path: Path, columns: int = 3, thumb_width: int = 620) -> bool:
    """Tile each event's review PNG into one sheet for fast human checking."""
    if Image is None or ImageDraw is None or not entries:
        return False
    tiles = []
    for label, path in entries:
        if not path.is_file():
            continue
        try:
            img = Image.open(path).convert("RGB")
        except (OSError, ValueError):
            continue
        ratio = thumb_width / img.width
        img = img.resize((thumb_width, max(1, int(img.height * ratio))))
        tile = Image.new("RGB", (thumb_width, img.height + 22), (20, 20, 20))
        tile.paste(img, (0, 22))
        ImageDraw.Draw(tile).text((6, 5), label, fill=(255, 255, 255))
        tiles.append(tile)
    if not tiles:
        return False
    rows_n = (len(tiles) + columns - 1) // columns
    cell_h = max(t.height for t in tiles)
    sheet = Image.new("RGB", (columns * thumb_width, rows_n * cell_h), (0, 0, 0))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % columns) * thumb_width, (i // columns) * cell_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return True


def csv_zone_rows(rows: list[dict[str, Any]], source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Accept Straight Mode rows only when a finite offset is paired with its corner anchor in the source CSV."""
    warnings: list[str] = []
    output: list[dict[str, Any]] = []
    if "straight_mode_map_annotations" in source_file.casefold():
        return [], ["Refused to read image-derived annotations as Straight Mode offsets."]
    for index, raw in enumerate(rows):
        lower = {str(k).strip().casefold(): v for k, v in raw.items()}

        def find(*names: str) -> Any:
            for name in names:
                if name.casefold() in lower:
                    return nullish(lower[name.casefold()])
            return None

        zone = find("zone_id", "zone", "zone_name", "name") or f"unknown-{index + 1}"
        normal_offset = parse_number(find("normal_grip_activation_offset_m_after_corner", "normal_grip_offset_m_after_corner", "normal_grip_activation_offset_m"))
        normal_corner = parse_number(find("normal_grip_corner", "normal_corner", "corner_normal_grip"))
        low_offset = parse_number(find("low_grip_activation_offset_m_after_corner", "low_grip_offset_m_after_corner", "low_grip_activation_offset_m"))
        low_corner = parse_number(find("low_grip_corner", "low_corner", "corner_low_grip"))
        normal_ok = normal_offset is not None and normal_corner is not None
        low_ok = low_offset is not None and low_corner is not None
        if not (normal_ok or low_ok):
            warnings.append(f"Straight Mode zone {zone} in {source_file} has no finite activation offset paired with a corner anchor; row rejected (not exported).")
            continue
        output.append({
            "zone_id": zone,
            "mode": "Straight Mode",
            "normal_grip_activation_offset_m_after_corner": normal_offset if normal_ok else None,
            "normal_grip_corner": normal_corner if normal_ok else None,
            "low_grip_activation_offset_m_after_corner": low_offset if low_ok else None,
            "low_grip_corner": low_corner if low_ok else None,
            "source_note": find("source_note", "source", "notes"),
            "source_file": source_file,
            "verification_status": "source supplied; corner anchor and absolute lap distance not validated",
            "source_fields_json": raw,
        })
    return output, warnings


def load_straight_mode_zones(root: Path, raw_root: Path, event: str) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    event_slug = slug(event)
    candidates = [
        raw_root / "straight_mode_zones_2026" / f"{event_slug}.csv",
        raw_root / "active_aero_zones" / f"{event_slug}.csv",
        root / "references" / "straight_mode_zones_2026" / f"{event_slug}.csv",
    ]
    is_australia = norm_text(event) == "australian grand prix"
    if is_australia:
        candidates.append(root / "trackData_Australia" / "extracted" / "australia" / "straight_mode_zones_2026.csv")
    path = next((p for p in candidates if p.is_file()), None)
    archive_member = None
    archive_path = root / "Project_AIML_F1_Australia_TrackData.zip"
    if path is None and is_australia and archive_path.is_file():
        try:
            with zipfile.ZipFile(archive_path) as archive:
                member = "trackData_Australia/extracted/australia/straight_mode_zones_2026.csv"
                if member in archive.namelist():
                    content = archive.read(member).decode("utf-8-sig")
                    rows = list(csv.DictReader(io.StringIO(content)))
                    source = f"{rel_path(archive_path, root)}::{member}"
                    normalized, warnings = csv_zone_rows(rows, source)
                    return normalized, source, warnings
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            return [], None, [f"Could not read Australian Straight Mode reference archive: {exc}"]
    if path is None:
        return [], None, []
    try:
        rows = read_csv_path(path)
    except (OSError, csv.Error) as exc:
        return [], rel_path(path, root), [f"Could not read Straight Mode CSV: {exc}"]
    source = rel_path(path, root) or str(path)
    normalized, warnings = csv_zone_rows(rows, source)
    return normalized, source, warnings


def raw_session_inventory(event_sessions: list[Path], root: Path) -> list[dict[str, Any]]:
    inventory = []
    for session_dir in event_sessions:
        for path in sorted(session_dir.glob("*.json")):
            try:
                inventory.append(file_record(path, root, path.stem, session_dir.name))
            except OSError:
                inventory.append({"file": rel_path(path, root), "kind": path.stem, "folder_label": session_dir.name, "error": "file not readable"})
    return inventory


def _fingerprint(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _count_map_entries(cmap: dict[str, Any], event: str) -> int:
    target = norm_text(event)
    return sum(1 for item in cmap.get("session_files", []) if isinstance(item, dict) and norm_text(item.get("event_name")) == target)


def compare_tables(base_rows: list[dict[str, Any]], alt_tables: dict[str, list[dict[str, Any]]], columns: Iterable[str],
                   key_column: str | None = None) -> dict[str, Any]:
    """Field-by-field comparison of the selected source table against the same family in other source files.
    Rows are compared by position only when row counts (and the key column, if any) agree; otherwise it is reported as not comparable."""
    differing: dict[str, dict[str, Any]] = {}
    identical: set[str] = set(columns)
    not_comparable: list[str] = []
    for label, rows in alt_tables.items():
        if len(rows) != len(base_rows) or (key_column and [r.get(key_column) for r in rows] != [r.get(key_column) for r in base_rows]):
            not_comparable.append(label)
            continue
        for column in columns:
            pairs = [(a.get(column), b.get(column)) for a, b in zip(base_rows, rows)]
            if all(x == y for x, y in pairs):
                continue
            identical.discard(column)
            deltas = [abs(x - y) for x, y in pairs if isinstance(x, (int, float)) and isinstance(y, (int, float))]
            differing.setdefault(column, {})[label] = round(max(deltas), 3) if deltas else "non-numeric difference"
    return {"files_compared": len(alt_tables) - len(not_comparable), "not_comparable_files": not_comparable,
            "fields_differing_max_abs_diff": differing, "fields_identical": sorted(identical) if len(alt_tables) > len(not_comparable) else []}


def build_reference_for_event(root: Path, raw_root: Path, out_root: Path, event_entry: dict[str, Any], sessions_root: Path,
                              cmap: dict[str, Any], event_to_svg: dict[str, str], image_map_path: Path | None,
                              global_warnings: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    event = event_entry["event_name"]
    event_slug = event_entry["event_slug"]
    out_dir = out_root / "processed" / event_slug
    event_warnings: list[str] = []

    def src_rel(path: Path | None) -> str | None:
        return rel_path(path, root)

    def out_rel(path: Path | None) -> str | None:
        return rel_path(path, out_root)

    # ---- event-level section reference (raw/sections) ----
    section_path: Path | None = event_entry.get("section_path")
    section_rows: list[dict[str, Any]] = []
    if section_path is not None:
        try:
            section_rows, section_warnings = extract_section_file(read_json(section_path), src_rel(section_path) or str(section_path))
            event_warnings.extend(section_warnings)
            event_warnings.extend(validate_sections(section_rows))
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"Mapped section source could not be read: {exc}"
            event_warnings.append(msg)
            global_warnings.append({"severity": "error", "event": event, "stage": "sections", "file": src_rel(section_path), "warning": msg})
    else:
        event_warnings.append("No mapped section file was found.")

    # ---- raw session folders ----
    event_session_dir = match_event_session_directory(sessions_root, event, global_warnings)
    session_dirs = sorted(list_sessions(event_session_dir), key=lambda p: (session_rank(p.name), p.name))
    parsed: dict[tuple[str, str], Any] = {}
    paths: dict[tuple[str, str], Path] = {}
    for session_dir in session_dirs:
        for filename in ("corners.json", "cor.json", "weather.json", "rcm.json"):
            path = find_named_json(session_dir, filename)
            if path is None:
                continue
            paths[(session_dir.name, filename)] = path
            try:
                parsed[(session_dir.name, filename)] = read_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                global_warnings.append({"severity": "error", "event": event, "session": session_dir.name, "stage": "source_read",
                                        "file": src_rel(path), "warning": f"Could not parse JSON: {exc}"})
                event_warnings.append(f"Could not parse {src_rel(path)}: {exc}")

    def source_record(folder: str, filename: str, kind: str, checked: list[dict[str, Any]]) -> dict[str, Any]:
        path = paths[(folder, filename)]
        return {**file_record(path, root, kind, folder), "files_checked": checked}

    # ---- EVENT-LEVEL static references: each family selected independently, Race > Qualifying > ... ----
    # Folder labels are provenance only; static references are not session data.
    geometry: list[dict[str, Any]] = []
    geometry_pick: tuple[str, str] | None = None
    geometry_checked: list[dict[str, Any]] = []
    geometry_versions: dict[str, list[str]] = {}
    for session_dir in session_dirs:
        for filename in ("corners.json", "cor.json"):
            key = (session_dir.name, filename)
            if key not in paths:
                continue
            if key not in parsed:
                geometry_checked.append({"folder_label": session_dir.name, "file": src_rel(paths[key]), "result": "unreadable_json"})
                continue
            points, reason = candidate_geometry(parsed[key])
            version = _fingerprint([[p["x_raw"], p["y_raw"]] for p in points]) if points else None
            geometry_checked.append({"folder_label": session_dir.name, "file": src_rel(paths[key]),
                                     "result": "valid_geometry" if points else "no_valid_geometry",
                                     "point_count": len(points), "geometry_fingerprint": version, "reason": reason})
            if points and version is not None:
                geometry_versions.setdefault(version, []).append(f"{session_dir.name}/{filename}")
                if geometry_pick is None:
                    geometry, geometry_pick = points, key
    if len(geometry_versions) > 1:
        event_warnings.append("Valid geometry differs between source files (" + "; ".join(f"{v}: {f}" for v, f in geometry_versions.items())
                              + "); the highest-priority source was used unchanged and nothing was averaged.")

    corners: list[dict[str, Any]] = []
    corner_pick: tuple[str, str] | None = None
    corner_checked: list[dict[str, Any]] = []
    for session_dir in session_dirs:
        for filename in ("cor.json", "corners.json"):
            key = (session_dir.name, filename)
            if key not in parsed:
                continue
            rows, corner_warnings = extract_corner_records(parsed[key], src_rel(paths[key]) or str(paths[key]), session_dir.name)
            corner_checked.append({"folder_label": session_dir.name, "file": src_rel(paths[key]),
                                   "result": "corner_records" if rows else "no_corner_records", "row_count": len(rows)})
            if rows:
                if corner_pick is None:
                    corners, corner_pick = rows, key
                    event_warnings.extend(corner_warnings)
    def pick_markers(family: str) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
        for session_dir in session_dirs:
            for filename in ("cor.json", "corners.json"):
                key = (session_dir.name, filename)
                if key not in parsed:
                    continue
                rows, marker_warnings = extract_marker_family(parsed[key], family, src_rel(paths[key]) or str(paths[key]), session_dir.name)
                if rows:
                    event_warnings.extend(marker_warnings)
                    return rows, key
        return [], None

    marshal_lights, lights_pick = pick_markers("marshal_lights")
    marshal_sectors, sectors_pick = pick_markers("marshal_sectors")

    layout_rows: list[dict[str, Any]] = []
    layout_pick: tuple[str, str] | None = None
    layout_unpaired: dict[str, Any] = {}
    for session_dir in session_dirs:
        for filename in ("corners.json", "cor.json"):
            key = (session_dir.name, filename)
            if key not in parsed or layout_pick is not None:
                continue
            rows, layout_warnings, unpaired = extract_layout_section_metadata(parsed[key], src_rel(paths[key]) or str(paths[key]), session_dir.name)
            if rows or unpaired:
                layout_rows, layout_pick, layout_unpaired = rows, key, unpaired
                event_warnings.extend(layout_warnings)

    mini_sectors: list[dict[str, Any]] = []
    if geometry_pick is not None:
        mini_sectors, mini_warnings = extract_mini_sector_markers(parsed[geometry_pick], geometry, src_rel(paths[geometry_pick]) or str(paths[geometry_pick]), geometry_pick[0])
        event_warnings.extend(mini_warnings)

    # Geometry bookkeeping and honest unavailability evidence.
    if geometry:
        assert geometry_pick is not None
        for point in geometry:
            point.update({"source_file": src_rel(paths[geometry_pick]), "source_folder_label": geometry_pick[0],
                          "coordinate_reference": "source-local; axes/origin/direction not verified", "units": "unknown; raw values retained",
                          "source_fields_json": {"x": point["x_raw"], "y": point["y_raw"]}})
        geometry_status = "extracted_source_coordinates_unscaled"
        geometry_reason = None
    else:
        geometry_status = "unavailable_no_valid_source"
        dir_note = (f"raw session directory '{src_rel(event_session_dir)}' found with folders {[p.name for p in session_dirs]}"
                    if event_session_dir else f"no raw session directory matching '{event}' under {src_rel(sessions_root) or 'raw/sessions'}")
        geometry_reason = (f"No valid geometry. Checked: {dir_note}; corners.json/cor.json files examined: {len(geometry_checked)}; "
                           f"circuitMap.json session_files entries for this event: {_count_map_entries(cmap, event)}; "
                           f"section file: {src_rel(section_path) or 'none'} (section percentages only, no coordinates). "
                           "Geometry is not reconstructed from SVG/WebP images and no other circuit is substituted.")
        event_warnings.append(geometry_reason)
    if not corners:
        event_warnings.append("No corner records available from any source file for this event" +
                              ("" if session_dirs else f" (no raw session folders were found; circuitMap.json lists {_count_map_entries(cmap, event)} fetched session files)") + ".")


    # ---- cross-file consistency of event-level families (field by field) ----
    def tables_for(extract_fn) -> dict[str, list[dict[str, Any]]]:
        tables: dict[str, list[dict[str, Any]]] = {}
        for session_dir in session_dirs:
            for filename in ("cor.json", "corners.json"):
                key = (session_dir.name, filename)
                if key in parsed:
                    rows = extract_fn(parsed[key], key)
                    if rows:
                        tables[f"{key[0]}/{key[1]}"] = rows
        return tables

    family_consistency: dict[str, Any] = {}
    for family, rows_, pick, extract_fn, columns, key_col in (
        ("corners", corners, corner_pick, lambda p, k: extract_corner_records(p, src_rel(paths[k]) or "", k[0])[0],
         ("corner_number", "x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), "corner_number"),
        ("layout_section_metadata", layout_rows, layout_pick, lambda p, k: extract_layout_section_metadata(p, src_rel(paths[k]) or "", k[0])[0],
         ("section_type", "start_percent", "end_percent", "start_distance_source", "end_distance_source"), None),
        ("marshal_lights", marshal_lights, lights_pick, lambda p, k: extract_marker_family(p, "marshal_lights", src_rel(paths[k]) or "", k[0])[0],
         ("x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), None),
        ("marshal_sectors", marshal_sectors, sectors_pick, lambda p, k: extract_marker_family(p, "marshal_sectors", src_rel(paths[k]) or "", k[0])[0],
         ("x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), None),
    ):
        if not rows_ or pick is None:
            continue
        selected_label = f"{pick[0]}/{pick[1]}"
        alts = {label: t for label, t in tables_for(extract_fn).items() if label != selected_label}
        if not alts:
            continue
        report_ = compare_tables(rows_, alts, columns, key_col)
        report_["selected_source"] = selected_label
        family_consistency[family] = report_
        differing = report_["fields_differing_max_abs_diff"]
        if differing:
            detail = "; ".join(f"{col}: max |delta| " + (str(max((v for v in vals.values() if isinstance(v, (int, float))), default="n/a")) if any(isinstance(v, (int, float)) for v in vals.values()) else "non-numeric") for col, vals in differing.items())
            event_warnings.append(
                f"{family}: field(s) {sorted(differing)} differ between the selected source ({selected_label}) and {report_['files_compared']} other source file(s) ({detail}); "
                f"identical fields: {report_['fields_identical']}. Values that vary by source file are not event-level; do not use them as lap-distance anchors until the intended reference lap is confirmed.")

    # ---- event-level layout provenance (NOT session data) ----
    metadata_keys: dict[str, tuple[str, str]] = {}
    for key in (geometry_pick, corner_pick, lights_pick, sectors_pick, layout_pick):
        if key is not None:
            metadata_keys[src_rel(paths[key]) or str(paths[key])] = key
    metadata_candidates = [source_metadata(parsed[key], rel) for rel, key in metadata_keys.items()]
    meta_by_key: dict[str, list[dict[str, Any]]] = {}
    for meta in metadata_candidates:
        for key, value in meta.items():
            if key != "source_file" and value is not None:
                meta_by_key.setdefault(key, []).append({"source_file": meta["source_file"], "value": value})
    metadata_conflicts: dict[str, list[dict[str, Any]]] = {}
    for key, values in meta_by_key.items():
        if len({json.dumps(v["value"], sort_keys=True, ensure_ascii=False) for v in values}) > 1:
            metadata_conflicts[key] = values
            event_warnings.append(f"Metadata conflict for {key} between selected sources; all candidates retained in master_track.json.")
    lap_versions: dict[str, list[str]] = {}
    for (folder, filename), payload in parsed.items():
        if filename == "corners.json" and isinstance(payload, dict) and payload.get("LayoutLapSession") is not None:
            sig = _fingerprint([payload.get(k) for k in ("LayoutYear", "LayoutRaceDate", "LayoutLapSession", "LayoutLapStartDate", "LayoutLapNumber", "LayoutLapDriverNumber")])
            lap_versions.setdefault(sig, []).append(folder)
    if len(lap_versions) > 1:
        event_warnings.append(f"Layout reference-lap metadata differs between session folders {sorted(lap_versions.values())}; the selected source is used unchanged.")
    lap_payload = parsed.get(geometry_pick) if geometry_pick else (parsed.get(corner_pick) if corner_pick else None)
    layout_lap = None
    if isinstance(lap_payload, dict):
        layout_lap = {
            "layout_year": lap_payload.get("LayoutYear"), "layout_race_date": lap_payload.get("LayoutRaceDate"),
            "layout_meeting_name": lap_payload.get("LayoutMeetingName"),
            "reference_lap_session_label": lap_payload.get("LayoutLapSession"),
            "reference_lap_session_canonical": canonical_session(lap_payload.get("LayoutLapSession")),
            "reference_lap_driver_number": lap_payload.get("LayoutLapDriverNumber"),
            "reference_lap_number": lap_payload.get("LayoutLapNumber"),
            "reference_lap_start_date": lap_payload.get("LayoutLapStartDate"),
            "scope": "Historical lap the layout was traced from. It says nothing about which session any weather or race-control file belongs to and is never used to relabel session data.",
        }
    layout_years = [meta.get("LayoutYear") for meta in metadata_candidates if meta.get("LayoutYear") is not None]
    layout_identity = {
        "layout_year_source_values": sorted({str(v) for v in layout_years}),
        "status": "requires_verification",
        "reference_lap": layout_lap,
        "metadata_candidates": metadata_candidates,
        "conflicting_metadata": metadata_conflicts,
        "note": "Source layout metadata is preserved but does not by itself prove that coordinates match the intended current-season layout.",
    }
    if any(y is not None and y < 2026 for y in (parse_number(v) for v in layout_years)):
        layout_identity["status"] = "historical_source_year_requires_compatibility_check"
        layout_identity["note"] = "The selected reference is tagged with a pre-2026 layout year. Do not assume it is an exact 2026 reference until layout compatibility is checked."
        event_warnings.append(f"Selected reference metadata is tagged layout year {sorted({str(v) for v in layout_years})}; current-season layout compatibility remains unverified.")

    # ---- images, image-space candidates, explicit Straight Mode offsets ----
    image_info = image_assets(root, raw_root, event, event_to_svg, image_map_path)
    if image_info.get("status") == "no_event_map_entry":
        event_warnings.append("No eventMap.json entry exists for this event; image links are omitted rather than guessed.")
    elif image_info.get("status") == "mapping_exists_but_assets_missing":
        event_warnings.append(f"Image mapping exists for {event}, but neither mapped SVG nor matching WebP asset was found in the expected image folders.")
    aero_rows, aero_source, aero_warnings = load_straight_mode_zones(root, raw_root, event)
    event_warnings.extend(aero_warnings)
    map_svg_path = map_webp_path = None
    if image_info.get("mapping_filename"):
        map_svg_path = find_case_insensitive(raw_root / "images" / "svg", str(image_info["mapping_filename"]))
        map_webp_path = find_case_insensitive(raw_root / "images" / "webp", Path(str(image_info["mapping_filename"])).stem + ".webp")
    preview_path = out_dir / "straight_mode_map_review.png"
    map_annotation_rows, map_annotation_info, map_annotation_warnings = extract_map_red_annotations(map_webp_path, map_svg_path, event, root, preview_path)
    if map_annotation_info.get("preview_file"):
        map_annotation_info["preview_file"] = out_rel(preview_path)
    event_warnings.extend(map_annotation_warnings)

    # ---- SESSION-LEVEL data: weather and race control ----
    resolutions: dict[str, dict[str, Any]] = {}
    session_prov_warnings: list[dict[str, Any]] = []
    for session_dir in session_dirs:
        kinds = {kind: parsed[(session_dir.name, fn)] for kind, fn in (("weather", "weather.json"), ("rcm", "rcm.json")) if (session_dir.name, fn) in parsed}
        resolution, res_warnings = resolve_session(event, session_dir.name, kinds)
        resolutions[session_dir.name] = resolution
        session_prov_warnings.extend(res_warnings)
    slugs, collision_warnings = assign_session_slugs(event, resolutions)
    session_prov_warnings.extend(collision_warnings)
    global_warnings.extend(session_prov_warnings)

    stale = []
    sessions_out = out_dir / "sessions"
    if sessions_out.is_dir():
        stale = sorted(p.name for p in sessions_out.iterdir() if p.is_dir() and p.name not in set(slugs.values()))
    if stale:
        event_warnings.append(f"Existing session output folders {stale} are not produced by this run (not deleted). Re-run with --clean or a fresh --out-root to remove stale labels.")

    session_outputs: list[dict[str, Any]] = []
    session_inventory = raw_session_inventory(session_dirs, root)
    ordered_folders = sorted(resolutions, key=lambda f: (session_rank(resolutions[f]["resolved_session"]), f))
    for folder in ordered_folders:
        resolution = resolutions[folder]
        session_slug = slugs[folder]
        session_out = out_dir / "sessions" / session_slug
        session_out.mkdir(parents=True, exist_ok=True)
        session_warnings: list[str] = []
        session_src_list = []
        for kind, filename, output_name, extractor, headers in (
            ("weather", "weather.json", "weather.csv", extract_weather, WEATHER_HEADERS),
            ("rcm", "rcm.json", "race_control.csv", extract_race_control, RCM_HEADERS),
        ):
            source_path = paths.get((folder, filename))
            if source_path is None:
                rows, status, source_rel = [], "not_supplied", None
            else:
                source_rel = src_rel(source_path) or str(source_path)
                payload = parsed.get((folder, filename))
                if payload is None:
                    rows, status = [], "source_unreadable"
                else:
                    rows, extraction_warnings = extractor(payload, source_rel)
                    session_warnings.extend(f"{output_name}: {w}" for w in extraction_warnings)
                    status = "exported" if rows else "source_present_but_no_rows_extracted"
                    session_src_list.append(file_record(source_path, root, kind, folder))
            for row in rows:
                row.update({"event_name": event, "raw_folder_session": folder, "resolved_session": resolution["resolved_session"],
                            "session_verification": resolution["session_verification"]})
            write_csv(session_out / output_name, rows, headers)
            json_name = "weather.json" if output_name == "weather.csv" else "race_control.json"
            write_json(session_out / json_name, {
                "schema_version": SCHEMA_VERSION, "event_name": event, "raw_folder_session": folder,
                "resolved_session": resolution["resolved_session"], "session_verification": resolution["session_verification"],
                "data_kind": output_name.removesuffix(".csv"), "source_file": source_rel, "row_count": len(rows), "status": status,
                "units": ({"session_time_s": "seconds", "ambient_air_temp_c": "degrees Celsius", "relative_humidity_pct": "percent",
                           "pressure_mbar": "mbar", "rainfall": "boolean source flag", "track_temp_c": "degrees Celsius",
                           "wind_direction_deg": "degrees", "wind_speed_mps": "m/s"} if output_name == "weather.csv" else {}),
                "records": rows,
            })
            csv_ok, csv_error = verify_csv(session_out / output_name, len(rows), headers, WEATHER_NUMERIC if output_name == "weather.csv" else (), require_columns=("event_name", "resolved_session", "raw_folder_session"))
            if not csv_ok:
                global_warnings.append({"severity": "error", "event": event, "session": folder, "stage": "output_validation",
                                        "file": out_rel(session_out / output_name), "warning": csv_error})
            session_outputs.append({"raw_folder_session": folder, "resolved_session": resolution["resolved_session"],
                                    "session_verification": resolution["session_verification"], "session_slug": session_slug,
                                    "data_kind": output_name.removesuffix(".csv"), "source_file": source_rel,
                                    "output_file": out_rel(session_out / output_name), "json_output_file": out_rel(session_out / json_name),
                                    "row_count": len(rows), "status": status})
        write_json(session_out / "session_manifest.json", {
            "schema_version": SCHEMA_VERSION, "generated_at_utc": utc_now(), "event_name": event,
            "raw_folder_session": folder, "resolved_session": resolution["resolved_session"],
            "session_resolution": resolution, "priority_rank": session_rank(resolution["resolved_session"])[0],
            "static_references_included": False,
            "static_reference_note": "Geometry, corners and sections are event-level references in ../../master_track.json, not part of this session.",
            "source_files": session_src_list,
            "json_source_inventory": [row for row in session_inventory if row.get("folder_label") == folder],
            "exports": [row for row in session_outputs if row["raw_folder_session"] == folder],
            "warnings": session_warnings,
        })
        for warning in session_warnings:
            global_warnings.append({"severity": "warning", "event": event, "session": folder, "stage": "session_export", "warning": warning})

    # ---- event-level CSV outputs ----
    write_csv(out_dir / "track_geometry.csv", geometry, GEOMETRY_HEADERS)
    write_csv(out_dir / "corners.csv", corners, CORNER_HEADERS)
    write_csv(out_dir / "sections.csv", section_rows, SECTION_HEADERS)
    write_csv(out_dir / "layout_section_metadata.csv", layout_rows, LAYOUT_SECTION_HEADERS)
    write_csv(out_dir / "marshal_lights.csv", marshal_lights, MARKER_HEADERS)
    write_csv(out_dir / "marshal_sectors.csv", marshal_sectors, MARKER_HEADERS)
    write_csv(out_dir / "mini_sector_markers.csv", mini_sectors, MINI_SECTOR_HEADERS)
    write_csv(out_dir / "active_aero_zones.csv", aero_rows, AERO_HEADERS)
    write_csv(out_dir / "straight_mode_map_annotations.csv", map_annotation_rows, MAP_ANNOTATION_HEADERS)

    geometry_object = {
        "file": "track_geometry.csv", "point_count": len(geometry), "status": geometry_status, "scope": "event_level",
        "source_file": src_rel(paths[geometry_pick]) if geometry_pick else None,
        "source_folder_label": geometry_pick[0] if geometry_pick else None,
        "coordinate_reference": "source-local; x/y axes, origin, direction and coordinate transform not verified",
        "units": "unknown; raw source units retained without scaling",
        "files_checked": geometry_checked,
        "warnings": [geometry_reason] if geometry_reason else [],
    }
    if geometry:
        xy = [(p["x_raw"], p["y_raw"]) for p in geometry]
        duplicates = sum(1 for a, b in zip(xy, xy[1:]) if a == b)
        geometry_object["quality_checks"] = {
            "all_coordinates_finite": all(math.isfinite(x) and math.isfinite(y) for x, y in xy),
            "consecutive_duplicate_points": duplicates,
            "closed_loop_endpoint_distance_raw_units": math.hypot(xy[-1][0] - xy[0][0], xy[-1][1] - xy[0][1]),
            "distance_units_verified": False, "track_length_verified": False,
        }
        if duplicates:
            event_warnings.append(f"Geometry contains {duplicates} consecutive duplicate coordinate pairs; retained as source data.")
    else:
        geometry_object["evidence"] = {
            "raw_session_directory": src_rel(event_session_dir), "raw_session_directory_found": event_session_dir is not None,
            "session_folders_found": [p.name for p in session_dirs],
            "circuit_map_session_file_entries": _count_map_entries(cmap, event),
            "section_file": src_rel(section_path),
        }

    def source_obj(pick: tuple[str, str] | None, kind: str, checked: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        return source_record(pick[0], pick[1], kind, checked or []) if pick else None

    static_reference = {
        "scope": "event_level",
        "note": "Track geometry, corners, markers, layout sections, section percentages and map images are common to the event. Source folder names are provenance only.",
        "selection_rule": "Each family is selected independently from the first source file that yields valid records, searching folders Race > Qualifying > Sprint > Practice 3 > 2 > 1.",
        "geometry_source": source_obj(geometry_pick, "geometry", geometry_checked),
        "corner_source": source_obj(corner_pick, "corners", corner_checked),
        "marshal_light_source": source_obj(lights_pick, "marshal_lights"),
        "marshal_sector_source": source_obj(sectors_pick, "marshal_sectors"),
        "layout_section_source": source_obj(layout_pick, "layout_sections"),
        "section_percentage_source": file_record(section_path, root, "section_reference") if section_path and section_path.is_file() else None,
        "cross_folder_consistency": {
            "geometry_distinct_versions": len(geometry_versions), "geometry_files_by_version": geometry_versions,
            "families": family_consistency,
        },
    }

    exported_weather = [row for row in session_outputs if row["data_kind"] == "weather" and row["row_count"] > 0]
    exported_weather.sort(key=lambda r: (session_rank(r["resolved_session"]), r["raw_folder_session"]))
    session_model_inputs = {
        "precedence": "Race, then Qualifying, then Sprint, then Practice 3/2/1. Lower-priority sessions are retained, not discarded.",
        "primary_session_for_weather": exported_weather[0]["resolved_session"] if exported_weather else None,
        "primary_session_verification": exported_weather[0]["session_verification"] if exported_weather else None,
        "primary_session_raw_folder": exported_weather[0]["raw_folder_session"] if exported_weather else None,
        "available_sessions": [
            {"resolved_session": r["resolved_session"], "raw_folder_session": r["raw_folder_session"], "session_verification": r["session_verification"],
             "weather_rows": r["row_count"], "output_file": r["output_file"]} for r in exported_weather],
    }

    straight_mode_obj = {
        "file": "active_aero_zones.csv", "mode": "Straight Mode", "row_count": len(aero_rows), "source_file": aero_source,
        "status": "source_supplied_anchor_unverified" if aero_rows else "not_provided",
        "distance_semantics": "Only structured source offsets paired with a corner anchor belong here. Absolute lap distances are not calculated by this processor.",
        "items": aero_rows,
        "map_annotation_candidates_file": "straight_mode_map_annotations.csv",
        "map_annotation_candidate_count": len(map_annotation_rows),
        "map_annotation_note": "Separate visual evidence; image coordinates are not activation offsets and are not telemetry-aligned.",
    }
    map_annotations_obj = {**map_annotation_info, "file": "straight_mode_map_annotations.csv",
                           "status": map_annotation_info.get("status", "not_available"),
                           "manual_review_required": True, "not_valid_for_physics_until_anchor_alignment": True}

    # ---- output validation (headers, row counts, finite numbers, labels, source paths) ----
    checks = [
        ("track_geometry.csv", len(geometry), GEOMETRY_HEADERS, ("x_raw", "y_raw"), ("source_file",)),
        ("corners.csv", len(corners), CORNER_HEADERS, ("x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), ("source_file",)),
        ("sections.csv", len(section_rows), SECTION_HEADERS, ("start_percent", "end_percent"), ("source_file",)),
        ("layout_section_metadata.csv", len(layout_rows), LAYOUT_SECTION_HEADERS, ("start_percent", "end_percent", "start_distance_source", "end_distance_source"), ("source_file",)),
        ("marshal_lights.csv", len(marshal_lights), MARKER_HEADERS, ("x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), ("source_file",)),
        ("marshal_sectors.csv", len(marshal_sectors), MARKER_HEADERS, ("x_raw", "y_raw", "angle_deg_source", "distance_source", "mv_distance_source"), ("source_file",)),
        ("mini_sector_markers.csv", len(mini_sectors), MINI_SECTOR_HEADERS, ("x_raw", "y_raw"), ("source_file",)),
        ("active_aero_zones.csv", len(aero_rows), AERO_HEADERS, ("normal_grip_activation_offset_m_after_corner", "normal_grip_corner", "low_grip_activation_offset_m_after_corner", "low_grip_corner"), ("source_file",)),
        ("straight_mode_map_annotations.csv", len(map_annotation_rows), MAP_ANNOTATION_HEADERS, ("bbox_x_min_px", "bbox_y_min_px", "bbox_x_max_px_inclusive", "bbox_y_max_px_inclusive", "centroid_x_px", "centroid_y_px"), ("source_image_webp", "event_name")),
    ]
    for name, expected, headers, numeric, required in checks:
        ok, error = verify_csv(out_dir / name, expected, headers, numeric, require_columns=required)
        if not ok:
            global_warnings.append({"severity": "error", "event": event, "stage": "output_validation", "file": out_rel(out_dir / name), "warning": error})

    warnings_sorted = sorted(set(event_warnings))
    write_json(out_dir / "source_manifest.json", {
        "schema_version": SCHEMA_VERSION, "generated_at_utc": utc_now(), "event_name": event, "event_slug": event_slug,
        "static_reference": static_reference,
        "straight_mode_zone_source": aero_source,
        "image_map_source": file_record(image_map_path, root, "event_map") if image_map_path and image_map_path.is_file() else None,
        "session_resolutions": resolutions,
        "session_source_inventory": session_inventory,
        "session_exports": sorted(session_outputs, key=lambda r: (session_rank(r["resolved_session"]), r["data_kind"])),
        "outputs": ["master_track.json", "source_manifest.json", "track_geometry.csv", "corners.csv", "sections.csv",
                    "layout_section_metadata.csv", "marshal_lights.csv", "marshal_sectors.csv", "mini_sector_markers.csv",
                    "active_aero_zones.csv", "straight_mode_map_annotations.csv", "straight_mode_map_review.png",
                    "sessions/<resolved-session-slug>/{weather,race_control}.{csv,json}", "sessions/<resolved-session-slug>/session_manifest.json"],
        "exclusions": EXCLUDED_EVENT_LABELS,
        "warnings": warnings_sorted,
    })

    master = {
        "schema_version": SCHEMA_VERSION, "generated_at_utc": utc_now(), "event_name": event, "event_slug": event_slug,
        "source_manifest_file": "source_manifest.json",
        "source_map": {"file": rel_path(root / "circuitMap.json", root) if (root / "circuitMap.json").is_file() else "raw/circuitMap.json",
                       "repository": cmap.get("source_repository"), "branch": cmap.get("source_branch")},
        "static_reference": static_reference,
        "layout_identity": layout_identity,
        "images": image_info,
        "straight_mode_map_annotations": map_annotations_obj,
        "geometry": geometry_object,
        "corners": {"file": "corners.csv", "scope": "event_level", "row_count": len(corners),
                    "source_file": src_rel(paths[corner_pick]) if corner_pick else None,
                    "source_folder_label": corner_pick[0] if corner_pick else None,
                    "files_checked": corner_checked, "status": "extracted" if corners else "not_available"},
        "sections": {"file": "sections.csv", "scope": "event_level", "row_count": len(section_rows), "source_file": src_rel(section_path),
                     "status": "extracted" if section_rows else "not_available", "validation": validate_sections(section_rows)},
        "layout_section_metadata": {"file": "layout_section_metadata.csv", "scope": "event_level", "row_count": len(layout_rows),
                                    "source_file": src_rel(paths[layout_pick]) if layout_pick else None,
                                    "source_folder_label": layout_pick[0] if layout_pick else None,
                                    "status": "extracted" if layout_rows else "not_available",
                                    "unpaired_source_arrays": layout_unpaired,
                                    "note": "Only arrays sharing one length are paired. Arrays of a different length (e.g. 'Section') are preserved raw and are not matched to section rows by index."},
        "marshal_lights": {"file": "marshal_lights.csv", "row_count": len(marshal_lights), "status": "extracted" if marshal_lights else "not_available"},
        "marshal_sectors": {"file": "marshal_sectors.csv", "row_count": len(marshal_sectors), "status": "extracted" if marshal_sectors else "not_available"},
        "mini_sector_markers": {"file": "mini_sector_markers.csv", "row_count": len(mini_sectors), "status": "extracted" if mini_sectors else "not_available"},
        "active_aero_zones": straight_mode_obj,
        "session_data": {
            "scope": "session_level",
            "session_model_inputs": session_model_inputs,
            "session_resolutions": resolutions,
            "provenance_warnings": session_prov_warnings,
            "exports": sorted(session_outputs, key=lambda r: (session_rank(r["resolved_session"]), r["data_kind"])),
        },
        "source_inventory": session_inventory,
        "validation": {"status": "warnings" if warnings_sorted else "passed_with_source_limits", "warnings": warnings_sorted,
                       "coordinate_units_verified": False, "layout_compatible_with_2026_verified": False,
                       "telemetry_alignment_performed": False, "weather_sensitivity_model_performed": False},
    }
    write_json(out_dir / "master_track.json", master)
    master_record = {
        **master, "master_track_file": out_rel(out_dir / "master_track.json"), "output_directory": out_rel(out_dir),
        "geometry": {**geometry_object, "points": geometry},
        "corners": {**master["corners"], "items": corners},
        "sections": {**master["sections"], "items": section_rows},
        "layout_section_metadata": {**master["layout_section_metadata"], "items": layout_rows},
        "marshal_lights": {**master["marshal_lights"], "items": marshal_lights},
        "marshal_sectors": {**master["marshal_sectors"], "items": marshal_sectors},
        "mini_sector_markers": {**master["mini_sector_markers"], "items": mini_sectors},
        "straight_mode_map_annotations": {**map_annotations_obj, "items": map_annotation_rows},
    }
    result = {
        "event_name": event, "event_slug": event_slug, "output_directory": out_rel(out_dir),
        "geometry_source_folder_label": geometry_pick[0] if geometry_pick else None,
        "corner_source_folder_label": corner_pick[0] if corner_pick else None,
        "geometry_status": geometry_status,
        "geometry_points": len(geometry), "corner_rows": len(corners), "section_rows": len(section_rows),
        "layout_section_metadata_rows": len(layout_rows), "marshal_light_rows": len(marshal_lights),
        "marshal_sector_rows": len(marshal_sectors), "mini_sector_marker_rows": len(mini_sectors),
        "straight_mode_zone_rows": len(aero_rows), "map_annotation_rows": len(map_annotation_rows),
        "map_annotation_zone_like_candidates": map_annotation_info.get("zone_like_candidate_count", 0),
        "map_annotation_status": map_annotation_info.get("status"),
        "session_folders": len(session_dirs),
        "sessions": [{"raw_folder_session": f, "resolved_session": resolutions[f]["resolved_session"],
                      "session_verification": resolutions[f]["session_verification"], "output_slug": slugs[f]} for f in ordered_folders],
        "weather_session_exports": sum(1 for s in session_outputs if s["data_kind"] == "weather" and s["row_count"] > 0),
        "race_control_session_exports": sum(1 for s in session_outputs if s["data_kind"] == "race_control" and s["row_count"] > 0),
        "image_status": image_info.get("status"), "layout_status": layout_identity["status"],
        "warnings": warnings_sorted,
    }
    for warning in warnings_sorted:
        global_warnings.append({"severity": "warning", "event": event, "stage": "event_validation", "warning": warning})
    return master_record, result



WEATHER_NUMERIC = ("session_time_s", "ambient_air_temp_c", "relative_humidity_pct", "pressure_mbar", "track_temp_c", "wind_direction_deg", "wind_speed_mps")


def verify_csv(path: Path, expected_rows: int, headers: list[str] | None = None, numeric_cols: Iterable[str] = (),
               require_columns: Iterable[str] = ()) -> tuple[bool, str | None]:
    """Check header, row count, finite numeric cells and non-empty required columns of a written CSV."""
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return False, "CSV header missing"
            if headers is not None and list(reader.fieldnames) != list(headers):
                return False, f"header mismatch: expected {headers}, read {list(reader.fieldnames)}"
            count = 0
            for line_no, row in enumerate(reader, start=2):
                count += 1
                for column in numeric_cols:
                    cell = row.get(column)
                    if cell not in (None, ""):
                        try:
                            if not math.isfinite(float(cell)):
                                return False, f"non-finite value in {column} at line {line_no}"
                        except ValueError:
                            return False, f"non-numeric value {cell!r} in {column} at line {line_no}"
                for column in require_columns:
                    if column in row and not str(row[column] or "").strip():
                        return False, f"empty required column {column} at line {line_no}"
        if count != expected_rows:
            return False, f"row count mismatch: expected {expected_rows}, read {count}"
        return True, None
    except (OSError, csv.Error, UnicodeError) as exc:
        return False, str(exc)



def build(root: Path, clean: bool = False, out_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    out_root = (out_root or root).resolve()
    raw_root = root / "raw"
    processed_root = out_root / "processed"
    reports_root = out_root / "reports"
    global_warnings: list[dict[str, Any]] = []
    if clean:
        # Only this processor's own outputs are removed. Refuse if they could overlap raw/.
        for owned in (processed_root, reports_root):
            if owned == raw_root or raw_root in owned.parents or owned in raw_root.parents:
                raise ValueError(f"Refusing --clean: output folder {owned} overlaps the raw folder {raw_root}.")
        if processed_root.is_dir():
            shutil.rmtree(processed_root)
        for name in ("process_tracks_report.json", "straight_mode_map_candidates.csv", "straight_mode_map_review_sheet.png"):
            target = reports_root / name
            if target.is_file():
                target.unlink()
    processed_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    cmap, cmap_path = load_circuit_map(root, raw_root)
    event_entries = mapped_events(root, raw_root, cmap, global_warnings)
    image_map, image_map_path = load_image_map(root, raw_root, global_warnings)
    sessions_root = raw_root / "sessions"
    circuits: list[dict[str, Any]] = []
    event_results: list[dict[str, Any]] = []
    for event_entry in event_entries:
        try:
            circuit, result = build_reference_for_event(root, raw_root, out_root, event_entry, sessions_root, cmap,
                                                        image_map, image_map_path, global_warnings)
            circuits.append(circuit)
            event_results.append(result)
            out_dir = out_root / str(result["output_directory"])
            try:
                saved_master = read_json(out_dir / "master_track.json")
                if saved_master.get("event_name") != result["event_name"]:
                    raise ValueError("master_track event_name does not match event output directory")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                global_warnings.append({"severity": "error", "event": result["event_name"], "stage": "output_validation",
                                        "file": rel_path(out_dir / "master_track.json", out_root), "warning": str(exc)})
        except Exception as exc:
            global_warnings.append({"severity": "error", "event": event_entry["event_name"], "stage": "event_build",
                                    "warning": f"Event processing failed: {type(exc).__name__}: {exc}"})

    # ---- cross-event image review artifacts ----
    candidate_rows = [row for c in circuits for row in c["straight_mode_map_annotations"]["items"]]
    write_csv(reports_root / "straight_mode_map_candidates.csv", candidate_rows, MAP_ANNOTATION_HEADERS)
    sheet_entries = [(f'{c["event_name"]} - {len(c["straight_mode_map_annotations"]["items"])} candidate(s), UNVERIFIED',
                      out_root / str(c["straight_mode_map_annotations"].get("preview_file")))
                     for c in circuits if c["straight_mode_map_annotations"].get("preview_file")]
    sheet_written = write_review_sheet(sheet_entries, reports_root / "straight_mode_map_review_sheet.png")

    # ---- image-map coverage: which eventMap entries were used, excluded, or have no circuit reference ----
    catalogued = {norm_text(r["event_name"]) for r in event_results}
    image_coverage = {"catalogued": [], "excluded_by_rule": [], "image_entry_without_circuit_reference": []}
    for event_key, svg_name in sorted(image_map.items()):
        if is_excluded(event_key):
            image_coverage["excluded_by_rule"].append({"event_key": event_key, "svg": svg_name})
        elif event_key in catalogued:
            image_coverage["catalogued"].append({"event_key": event_key, "svg": svg_name})
        else:
            image_coverage["image_entry_without_circuit_reference"].append({"event_key": event_key, "svg": svg_name,
                "note": "eventMap.json names this event but circuitMap.json has no entry for it; it was not processed and nothing was substituted."})
    for item in image_coverage["image_entry_without_circuit_reference"]:
        global_warnings.append({"severity": "warning", "stage": "image_mapping", "event": item["event_key"],
                                "warning": f"eventMap.json maps '{item['svg']}' to '{item['event_key']}', which has no circuitMap.json entry; not processed."})

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "title": "F1 Track Reference Catalog",
        "description": "Event-level circuit references plus separately labelled session-level weather and race-control exports. Image-derived Straight Mode candidates are linked separately and are not telemetry-aligned.",
        "source_map": {"file": rel_path(cmap_path, root), "repository": cmap.get("source_repository"), "branch": cmap.get("source_branch")},
        "exclusions": EXCLUDED_EVENT_LABELS,
        "session_selection_priority": list(SESSION_PRIORITY),
        "methodology": [
            "Geometry, corners, markers, section percentages and map images are event-level references; source folder labels are provenance only.",
            "Each static-reference family is selected independently (Race > Qualifying > Sprint > Practice) from the first valid source and recorded separately.",
            "Geometry is exported in original coordinate units; coordinate frames and units are not guessed and geometry is never rebuilt from images.",
            "Weather and race-control are session-level. The session comes from an explicit payload field when present; otherwise the raw folder label is kept and marked unverified_session.",
            "LayoutLapSession in corners.json is the historical layout reference lap and is never used to relabel weather or race-control data.",
            "Straight Mode activation offsets are stored only when an explicit structured CSV supplies an offset with its corner anchor. WebP red regions remain image-space candidates.",
        ],
        "circuits": circuits,
    }
    catalog_path = processed_root / "track_catalog.json"
    write_json(catalog_path, catalog)

    script_path = Path(__file__).resolve()
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "script": {"name": SCRIPT_NAME, "path": script_path.as_posix(), "sha256": sha256_file(script_path), "schema_version": SCHEMA_VERSION},
        "run": {"clean": clean, "input_root": str(root), "output_root": str(out_root)},
        "input_root": str(root),
        "raw_root_found": raw_root.is_dir(),
        "circuit_map_file": rel_path(cmap_path, root),
        "image_map_file": rel_path(image_map_path, root),
        "catalog_file": rel_path(catalog_path, out_root),
        "mapped_events_in_scope": len(event_entries),
        "events_successfully_catalogued": len(event_results),
        "excluded_events": EXCLUDED_EVENT_LABELS,
        "image_map_coverage": image_coverage,
        "geometry_unavailable_events": [
            {"event_name": r["event_name"], "geometry_status": r["geometry_status"], "session_folders": r["session_folders"],
             "evidence": next(c for c in circuits if c["event_name"] == r["event_name"])["geometry"].get("evidence"),
             "reason": next(c for c in circuits if c["event_name"] == r["event_name"])["geometry"]["warnings"]}
            for r in event_results if r["geometry_points"] == 0],
        "events": event_results,
        "map_review": {"candidates_csv": "reports/straight_mode_map_candidates.csv", "contact_sheet": "reports/straight_mode_map_review_sheet.png" if sheet_written else None,
                       "candidate_rows": len(candidate_rows), "all_unverified": True},
        "summary": {
            "events_with_geometry": sum(1 for item in event_results if item["geometry_points"] > 0),
            "events_with_corners": sum(1 for item in event_results if item["corner_rows"] > 0),
            "events_with_sections": sum(1 for item in event_results if item["section_rows"] > 0),
            "events_with_straight_mode_zones": sum(1 for item in event_results if item["straight_mode_zone_rows"] > 0),
            "events_with_map_annotation_candidates": sum(1 for item in event_results if item["map_annotation_rows"] > 0),
            "total_map_annotation_components": sum(item["map_annotation_rows"] for item in event_results),
            "total_zone_like_map_candidates": sum(item["map_annotation_zone_like_candidates"] for item in event_results),
            "events_with_image_map_entry": sum(1 for item in event_results if item["image_status"] in {"assets_found", "mapping_exists_but_assets_missing"}),
            "events_with_image_assets": sum(1 for item in event_results if item["image_status"] == "assets_found"),
            "sessions_with_weather_rows": sum(item["weather_session_exports"] for item in event_results),
            "sessions_with_race_control_rows": sum(item["race_control_session_exports"] for item in event_results),
            "sessions_unverified": sum(1 for item in event_results for s in item["sessions"] if s["session_verification"] == "unverified_session"),
            "sessions_confirmed_by_payload": sum(1 for item in event_results for s in item["sessions"] if s["session_verification"] == "payload_confirms_folder"),
            "sessions_relabelled_by_payload": sum(1 for item in event_results for s in item["sessions"] if s["session_verification"] == "payload_overrides_folder"),
            "warnings": 0, "errors": 0,
        },
        "warnings": global_warnings,
        "scope_limits": [
            "Source completeness and factual correctness are not guaranteed by successful parsing.",
            "Track layout year/compatibility, coordinate axes/units, total length and telemetry alignment remain unverified unless independently validated.",
            "Weather records are exported as observations, not used for a counterfactual weather/ERS simulation.",
            "Red regions detected in WebP images are unverified image-space candidates; zone identity, exact bounds, corner anchors and distances require human validation.",
            "Structured Straight Mode offsets come only from explicit CSV references; image candidates never fill or alter those fields.",
            "Overtake detection/activation callouts are a separate feature, are not detected here, and are never Straight Mode zones.",
            "Excluded events are not processed and no substitute circuit data is used.",
        ],
    }
    report_path = reports_root / "process_tracks_report.json"

    try:
        check_catalog = read_json(catalog_path)
        if len(check_catalog.get("circuits", [])) != len(circuits):
            global_warnings.append({"severity": "error", "stage": "catalog_validation", "warning": "track_catalog circuit count did not survive JSON round-trip."})
        leaked = [c.get("event_name") for c in check_catalog.get("circuits", []) if is_excluded(str(c.get("event_name", "")))]
        if leaked:
            global_warnings.append({"severity": "error", "stage": "exclusion_validation", "warning": f"Excluded events leaked into catalog: {leaked}"})
        blob = json.dumps(check_catalog).casefold()
        if re.search(FORBIDDEN_TERM_PATTERN, blob):
            global_warnings.append({"severity": "error", "stage": "terminology_validation", "warning": "Retired pre-2026 terminology found in catalog output; Straight Mode is the only active-aero concept."})
    except (OSError, json.JSONDecodeError) as exc:
        global_warnings.append({"severity": "error", "stage": "catalog_validation", "warning": str(exc)})

    report["warnings"] = global_warnings
    report["summary"]["warnings"] = sum(1 for item in global_warnings if item.get("severity") == "warning")
    report["summary"]["errors"] = sum(1 for item in global_warnings if item.get("severity") == "error")
    write_json(report_path, report)
    print(f"Mapped events catalogued: {len(event_results)} / {len(event_entries)}")
    print(f"Consolidated catalog: {catalog_path}")
    print(f"Validation report: {report_path}")
    print(f"Events with geometry: {report['summary']['events_with_geometry']}; with corners: {report['summary']['events_with_corners']}; with sections: {report['summary']['events_with_sections']}")
    print(f"Sessions unverified/confirmed/relabelled: {report['summary']['sessions_unverified']}/{report['summary']['sessions_confirmed_by_payload']}/{report['summary']['sessions_relabelled_by_payload']}")
    print(f"Warnings: {report['summary']['warnings']}; errors: {report['summary']['errors']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the consolidated F1 track reference catalog.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent,
                        help="Project trackData directory containing circuitMap.json and raw/ (default: script directory)")
    parser.add_argument("--out-root", type=Path, default=None,
                        help="Write processed/ and reports/ here instead of --root (use a temporary folder for a safe first run).")
    parser.add_argument("--clean", action="store_true",
                        help="Delete processed/ and this script's report files under --out-root before rebuilding. raw/ is never touched; the run aborts if outputs would overlap raw/.")
    parser.add_argument("--strict", action="store_true",
                        help="Return a non-zero exit code if output validation or source-read errors are reported.")
    args = parser.parse_args()
    try:
        report = build(args.root, clean=args.clean, out_root=args.out_root)
        return 1 if args.strict and report.get("summary", {}).get("errors", 0) else 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())