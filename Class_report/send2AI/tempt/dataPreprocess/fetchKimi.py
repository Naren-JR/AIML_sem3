#!/usr/bin/env python3
"""
Download Kimi Antonelli's telemetry directly from:
https://github.com/TracingInsights/2026

Creates one CSV per Grand Prix/session in the same folder as this script.
Existing CSVs are skipped without validation.

Example output:
    australiafp1.csv
    australiafp2.csv
    australiafp3.csv
    australiasq.csv
    australiasr.csv
    australiaq.csv
    australiar.csv

Time starts at zero for each session and continues cumulatively across laps.
Only these columns are exported:
time, rpm, speed, gear, throttle, brake, distance, rel_distance,
DistanceToDriverAhead, acc_x, acc_y, acc_z, x, y, z

Uses Python's standard library only; no pip installs required.
"""

import csv
import json
import re
import sys
import time
import http.client
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

# All downloaded raw session CSVs go into dataPreprocess/rawData/
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR / "rawData"
ROOT.mkdir(parents=True, exist_ok=True)

GITHUB_API = "https://api.github.com"
REPO_API = f"{GITHUB_API}/repos/TracingInsights/2026"
RAW_BASE = "https://raw.githubusercontent.com/TracingInsights/2026/main"
USER_AGENT = "dataExtractKimi/1.0 (public telemetry CSV exporter)"

COLUMNS = [
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

# Kimi Antonelli's common FastF1 driver abbreviation is ANT.
DRIVER_FOLDER_ALIASES = {
    "ant",
    "kim",
    "kimi",
    "kimi antonelli",
    "andrea kimi antonelli",
}

# Session codes also determine output file suffix and processing order.
SESSION_ALIASES = {
    "fp1": ("practice 1", "free practice 1", "fp1"),
    "fp2": ("practice 2", "free practice 2", "fp2"),
    "fp3": ("practice 3", "free practice 3", "fp3"),
    "sq": ("sprint qualifying", "sprint quali", "sprint shootout", "sq"),
    "sr": ("sprint race", "sprint", "sr"),
    "q": ("qualifying", "quali", "qualification", "q"),
    "r": ("race", "grand prix", "gp", "r"),
}

# Friendly event prefixes for output filenames.
EVENT_PREFIXES = {
    "Australian Grand Prix": "australia",
    "Austrian Grand Prix": "austria",
    "Chinese Grand Prix": "china",
    "Japanese Grand Prix": "japan",
    "Bahrain Grand Prix": "bahrain",
    "Saudi Arabian Grand Prix": "saudiarabia",
    "Miami Grand Prix": "miami",
    "Canadian Grand Prix": "canada",
    "Monaco Grand Prix": "monaco",
    "Spanish Grand Prix": "spain",
    "Spanish Grand Prix (Barcelona)": "barcelona",
    "British Grand Prix": "britain",
    "Belgian Grand Prix": "belgium",
    "Hungarian Grand Prix": "hungary",
    "Dutch Grand Prix": "netherlands",
    "Italian Grand Prix": "italy",
    "Azerbaijan Grand Prix": "azerbaijan",
    "Singapore Grand Prix": "singapore",
    "United States Grand Prix": "usa",
    "Mexico City Grand Prix": "mexicocity",
    "Mexican Grand Prix": "mexico",
    "São Paulo Grand Prix": "saopaulo",
    "Sao Paulo Grand Prix": "saopaulo",
    "Las Vegas Grand Prix": "lasvegas",
    "Qatar Grand Prix": "qatar",
    "Abu Dhabi Grand Prix": "abudhabi",
    "Emilia Romagna Grand Prix": "emiliaromagna",
    "Portuguese Grand Prix": "portugal",
    "Turkish Grand Prix": "turkey",
    "Russian Grand Prix": "russia",
    "Eifel Grand Prix": "eifel",
    "Styrian Grand Prix": "styria",
}

LAP_FILE_RE = re.compile(r"^(\d+)_tel\.json$", re.IGNORECASE)
SESSION_ORDER = {"fp1": 0, "fp2": 1, "fp3": 2, "sq": 3, "sr": 4, "q": 5, "r": 6}


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def api_get_json(url, retries=5):
    """GET a GitHub API endpoint with retries for transient connection closures."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
        "Connection": "close",
    }
    last_error = None
    for attempt in range(retries):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=90) as response:
                payload = response.read()
                return json.loads(payload.decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if (exc.code in (403, 429, 500, 502, 503, 504)) and attempt < retries - 1:
                wait = min(2 ** attempt, 20)
                print(f"[RETRY] GitHub returned HTTP {exc.code}; retrying in {wait}s...")
                time.sleep(wait)
                continue
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"GitHub API returned HTTP {exc.code} for {url}\\n{detail}\\n"
                "If this is a rate limit or temporary server error, wait and run again."
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError, http.client.HTTPException, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                wait = min(2 ** attempt, 20)
                print(f"[RETRY] Connection to {url} failed ({exc}); retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"Could not access GitHub API endpoint: {url}\\n"
                f"Last error: {type(exc).__name__}: {exc}\\n"
                "Check your internet connection, VPN/proxy/firewall settings, and try again."
            ) from exc
    raise RuntimeError(f"Could not access GitHub API endpoint {url}: {last_error}")


def get_repo_tree():
    """
    Fetch the repository tree event-by-event rather than requesting one enormous
    recursive tree. The 2026 repository is very large, and GitHub can return HTTP
    500 for a single recursive tree request covering the entire repository.
    """
    repo = api_get_json(REPO_API)
    default_branch = repo.get("default_branch", "main")
    branch_data = api_get_json(f"{REPO_API}/branches/{quote(default_branch, safe='')}")
    root_sha = branch_data["commit"]["commit"]["tree"]["sha"]

    # First request only the root listing (non-recursive).
    root_data = api_get_json(f"{REPO_API}/git/trees/{root_sha}")
    root_entries = root_data.get("tree", [])
    if not root_entries:
        raise RuntimeError("GitHub returned an empty repository root tree.")

    all_entries = []
    event_dirs = [
        item for item in root_entries
        if item.get("type") == "tree"
        and "grand prix" in normalize(item.get("path", ""))
    ]

    if not event_dirs:
        raise RuntimeError(
            "Could not find Grand Prix folders at the repository root. "
            "The repository structure may have changed."
        )

    print(f"Found {len(event_dirs)} Grand Prix folders. Scanning each event separately...")
    for index, event_dir in enumerate(event_dirs, start=1):
        event_name = event_dir["path"]
        event_sha = event_dir["sha"]
        print(f"[SCAN {index}/{len(event_dirs)}] {event_name}")
        event_tree = api_get_json(f"{REPO_API}/git/trees/{event_sha}?recursive=1")

        if event_tree.get("truncated"):
            # If one event is still too large, use its immediate subdirectories
            # and recursively query each session subtree separately.
            for child in event_tree.get("tree", []):
                if child.get("type") != "tree":
                    continue
                child_path = child["path"]
                child_tree = api_get_json(
                    f"{REPO_API}/git/trees/{child['sha']}?recursive=1"
                )
                for entry in child_tree.get("tree", []):
                    full_entry = dict(entry)
                    full_entry["path"] = f"{event_name}/{child_path}/{entry['path']}"
                    all_entries.append(full_entry)
        else:
            for entry in event_tree.get("tree", []):
                full_entry = dict(entry)
                full_entry["path"] = f"{event_name}/{entry['path']}"
                all_entries.append(full_entry)

    return default_branch, all_entries


def is_driver_folder(segment):
    """Match the known Kimi folder names/codes, tolerating minor spelling differences."""
    value = normalize(segment)
    compact = value.replace(" ", "")
    return value in {normalize(x) for x in DRIVER_FOLDER_ALIASES} or compact in {
        "ant", "kim", "kimiantonelli", "andre kimiantonelli".replace(" ", "")
    }


def identify_session(path_parts):
    """Find the session name in a telemetry file's parent path."""
    for part in path_parts:
        label = normalize(part)
        if not label:
            continue

        # Check the more specific sprint-qualifying label before sprint.
        if any(normalize(a) in label for a in SESSION_ALIASES["sq"][:-1]):
            return "sq"
        if label == "sq":
            return "sq"
        if any(normalize(a) in label for a in SESSION_ALIASES["fp1"]):
            return "fp1"
        if any(normalize(a) in label for a in SESSION_ALIASES["fp2"]):
            return "fp2"
        if any(normalize(a) in label for a in SESSION_ALIASES["fp3"]):
            return "fp3"
        if label in ("sr", "sprint", "sprint race") or label.startswith("sprint race"):
            return "sr"
        if "qualifying" in label or label in ("q", "quali", "qualification"):
            return "q"
        if label in ("r", "race", "gp", "grand prix") or label.startswith("race "):
            return "r"
    return None


def get_event_name(path_parts):
    """Return the top-level event directory name, excluding repository-level files."""
    if len(path_parts) < 4:
        return None
    first = path_parts[0]
    # Ignore common repository-level folders.
    if first.casefold() in {"images", "scripts", "schemas", ".github"}:
        return None
    return first


def event_prefix(event_name):
    """Make a compact, stable filename prefix for an event."""
    if event_name in EVENT_PREFIXES:
        return EVENT_PREFIXES[event_name]

    cleaned = normalize(event_name)
    cleaned = re.sub(r"\bgrand prix\b", "", cleaned).strip()
    return re.sub(r"[^a-z0-9]", "", cleaned)


def find_telemetry_groups(tree_paths):
    """
    Return {(event_name, session_code): [(lap_number, repo_path), ...]}.
    Expected repository path pattern:
    Event/Session/Driver/1_tel.json
    """
    groups = {}
    for repo_path in tree_paths:
        if not repo_path.endswith("_tel.json"):
            continue

        filename = repo_path.rsplit("/", 1)[-1]
        match = LAP_FILE_RE.match(filename)
        if not match:
            continue

        parts = repo_path.split("/")
        if len(parts) < 4:
            continue

        # Driver folder should be the directory immediately above the lap file.
        if not is_driver_folder(parts[-2]):
            continue

        event_name = get_event_name(parts)
        if not event_name:
            continue

        session = identify_session(parts[1:-2])
        if not session:
            print(f"[SKIP] Unrecognized session folder: {repo_path}")
            continue

        groups.setdefault((event_name, session), []).append((int(match.group(1)), repo_path))

    for key in groups:
        groups[key].sort(key=lambda item: item[0])
    return groups


def time_to_seconds(value):
    """Convert common JSON time values to seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    days = 0
    day_match = re.search(r"(-?\d+)\s+days?\s+", text, re.IGNORECASE)
    if day_match:
        days = int(day_match.group(1))
        text = text[day_match.end():]

    match = re.fullmatch(r"(-?)(\d+):(\d{2}):(\d{2})(?:\.(\d+))?", text)
    if match:
        sign = -1 if match.group(1) else 1
        fraction = float("0." + match.group(5)) if match.group(5) else 0.0
        total = days * 86400 + int(match.group(2)) * 3600 + int(match.group(3)) * 60 + int(match.group(4)) + fraction
        return sign * total

    match = re.fullmatch(r"(-?)(\d+):(\d{2})(?:\.(\d+))?", text)
    if match:
        sign = -1 if match.group(1) else 1
        fraction = float("0." + match.group(4)) if match.group(4) else 0.0
        total = days * 86400 + int(match.group(2)) * 60 + int(match.group(3)) + fraction
        return sign * total

    raise ValueError(f"Unrecognized time value: {value!r}")


def normalize_field_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).casefold())


def find_field(mapping, requested):
    """Find a field case-insensitively, tolerating underscore/case differences."""
    normalized_mapping = {normalize_field_name(key): value for key, value in mapping.items()}
    aliases = {
        "rpm": ("rpm",),
        "speed": ("speed",),
        "gear": ("gear", "ngear"),
        "throttle": ("throttle",),
        "brake": ("brake",),
        "distance": ("distance",),
        "reldistance": ("reldistance", "relativ edistance".replace(" ", "")),
        "distancetodriverahead": ("distancetodriverahead", "distancetodriveraheadm"),
        "accx": ("accx",),
        "accy": ("accy",),
        "accz": ("accz",),
        "x": ("x",),
        "y": ("y",),
        "z": ("z",),
        "time": ("time",),
    }
    target = normalize_field_name(requested)
    candidates = aliases.get(target, (target,))
    for candidate in candidates:
        if candidate in normalized_mapping:
            return normalized_mapping[candidate]
    return None


def rows_from_json(data):
    """
    Accept the TracingInsights per-lap format {"tel": {"time": [...], ...}},
    a direct column-oriented object, or a list of row objects.
    """
    if isinstance(data, dict) and isinstance(data.get("tel"), dict):
        data = data["tel"]

    if isinstance(data, dict):
        # A wrapped object may expose arrays under one of these keys.
        for key in ("data", "telemetry", "rows"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]

    if isinstance(data, dict):
        array_columns = {key: value for key, value in data.items() if isinstance(value, list)}
        if not array_columns:
            raise ValueError("JSON has no telemetry arrays.")

        row_count = max(len(values) for values in array_columns.values())
        rows = []
        for index in range(row_count):
            rows.append({
                key: values[index] if index < len(values) else None
                for key, values in array_columns.items()
            })
        return rows

    raise ValueError("Unsupported telemetry JSON structure.")


def raw_file_url(repo_path, branch):
    # Quote each path segment but preserve folder separators.
    encoded_path = "/".join(quote(part, safe="") for part in repo_path.split("/"))
    return f"https://raw.githubusercontent.com/TracingInsights/2026/{quote(branch, safe='')}/{encoded_path}"


def download_json(repo_path, branch):
    """Download one telemetry JSON with chunked progress, timeouts, and retries."""
    url = raw_file_url(repo_path, branch)
    filename = repo_path.rsplit("/", 1)[-1]
    last_error = None
    max_attempts = 4
    socket_timeout = 20
    overall_timeout = 180
    chunk_size = 64 * 1024

    for attempt in range(max_attempts):
        request = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Connection": "close"},
        )
        started = time.monotonic()
        payload = bytearray()
        last_report = started
        try:
            with urlopen(request, timeout=socket_timeout) as response:
                expected = response.headers.get("Content-Length")
                expected_bytes = int(expected) if expected and expected.isdigit() else None
                while True:
                    if time.monotonic() - started > overall_timeout:
                        raise TimeoutError(
                            f"download exceeded {overall_timeout}s overall timeout"
                        )
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    payload.extend(chunk)
                    now = time.monotonic()
                    if now - last_report >= 5 or (expected_bytes and len(payload) >= expected_bytes):
                        if expected_bytes:
                            pct = min(100, len(payload) * 100 / expected_bytes)
                            print(
                                f"  [DOWNLOAD] {filename}: {len(payload):,}/{expected_bytes:,} bytes ({pct:.0f}%)",
                                flush=True,
                            )
                        else:
                            print(
                                f"  [DOWNLOAD] {filename}: {len(payload):,} bytes received",
                                flush=True,
                            )
                        last_report = now

            if expected_bytes is not None and len(payload) != expected_bytes:
                raise http.client.IncompleteRead(bytes(payload), expected_bytes - len(payload))

            data = json.loads(payload.decode("utf-8"))
            print(f"  [DOWNLOAD] {filename}: complete ({len(payload):,} bytes).", flush=True)
            return data

        except HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                raise RuntimeError(f"Telemetry file not found on GitHub: {repo_path}") from exc
            retryable = exc.code in (403, 429, 500, 502, 503, 504)
            if not retryable or attempt >= max_attempts - 1:
                raise RuntimeError(f"HTTP {exc.code} downloading {repo_path}") from exc
            wait = min(2 ** attempt, 15)
            print(
                f"  [RETRY {attempt + 1}/{max_attempts - 1}] HTTP {exc.code} for {filename}; retrying in {wait}s...",
                flush=True,
            )
            time.sleep(wait)

        except (URLError, TimeoutError, socket.timeout, json.JSONDecodeError,
                http.client.HTTPException, OSError) as exc:
            last_error = exc
            if attempt >= max_attempts - 1:
                raise RuntimeError(
                    f"Could not download {repo_path}: {type(exc).__name__}: {exc}"
                ) from exc
            wait = min(2 ** attempt, 15)
            print(
                f"  [RETRY {attempt + 1}/{max_attempts - 1}] {filename} failed after "
                f"{len(payload):,} bytes ({type(exc).__name__}: {exc}); retrying in {wait}s...",
                flush=True,
            )
            time.sleep(wait)

    raise RuntimeError(f"Could not download {repo_path}: {last_error}")


def convert_session(lap_files, branch):
    """Download laps in numeric order and build rows with cumulative session time."""
    output_rows = []
    time_offset = 0.0

    total_laps = len(lap_files)
    for lap_index, (lap_number, repo_path) in enumerate(lap_files, start=1):
        print(f"  [LAP {lap_index}/{total_laps}] Downloading {repo_path.rsplit('/', 1)[-1]}...", flush=True)
        try:
            data = download_json(repo_path, branch)
            lap_rows = rows_from_json(data)
            print(f"  [LAP {lap_index}/{total_laps}] Parsed {len(lap_rows)} telemetry rows.", flush=True)
        except Exception as exc:
            print(f"[ERROR] Lap {lap_number}: {exc}")
            continue

        if not lap_rows:
            print(f"[WARN] Empty telemetry: {repo_path}")
            continue

        normalized_rows = []
        lap_times = []
        for row in lap_rows:
            normalized_row = {}
            for column in COLUMNS:
                value = find_field(row, column)
                normalized_row[column] = value
            try:
                seconds = time_to_seconds(normalized_row["time"])
            except ValueError as exc:
                print(f"[ERROR] {repo_path}: {exc}")
                seconds = None
            lap_times.append(seconds)
            normalized_rows.append(normalized_row)

        valid_times = [value for value in lap_times if value is not None]
        if not valid_times:
            print(f"[WARN] No valid time values: {repo_path}")
            continue

        # The offset is the previous lap's final timestamp. Thus a new lap's
        # original t=0 sample shares the previous lap's final adjusted time.
        last_time = lap_times[-1] if lap_times[-1] is not None else valid_times[-1]

        for row, lap_time in zip(normalized_rows, lap_times):
            out = {}
            for column in COLUMNS:
                value = row.get(column)
                if column == "time":
                    out[column] = "" if lap_time is None else round(lap_time + time_offset, 9)
                else:
                    out[column] = "" if value is None else value
            output_rows.append(out)

        time_offset += last_time

    return output_rows


def main():
    print("Connecting to TracingInsights/2026...")
    try:
        branch, tree = get_repo_tree()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    tree_paths = [
        item["path"] for item in tree
        if item.get("type") == "blob" and item.get("path")
    ]
    groups = find_telemetry_groups(tree_paths)

    if not groups:
        print(
            "[ERROR] No Kimi Antonelli telemetry files were discovered.\n"
            "The repository may use a different driver-folder name or path structure."
        )
        sys.exit(1)

    # Skip existing CSVs before downloading any telemetry for that session.
    jobs = []
    for (event_name, session), lap_files in groups.items():
        filename = f"{event_prefix(event_name)}{session}.csv"
        output_path = ROOT / filename
        if output_path.exists():
            print(f"[SKIP] Already exists: {filename}")
            continue
        jobs.append((event_name, session, lap_files, output_path))

    jobs.sort(key=lambda job: (job[0].casefold(), SESSION_ORDER.get(job[1], 99)))

    if not jobs:
        print("All discovered event/session CSVs already exist. Nothing to download.")
        return

    print(f"Found {len(jobs)} event/session CSV(s) to create.")
    for event_name, session, lap_files, output_path in jobs:
        print(f"\n[{event_name} | {session.upper()}] {len(lap_files)} lap file(s)", flush=True)
        rows = convert_session(lap_files, branch)
        if not rows:
            print(f"[WARN] No CSV written for {event_name} / {session.upper()}.")
            continue

        try:
            with output_path.open("x", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except FileExistsError:
            # Protect an existing file if it appeared after the initial check.
            print(f"[SKIP] Already exists: {output_path.name}")
            continue

        print(f"[OK] {output_path.name}: {len(rows)} telemetry rows")

    print(f"\nFinished. Output folder: {ROOT}")


if __name__ == "__main__":
    main()
