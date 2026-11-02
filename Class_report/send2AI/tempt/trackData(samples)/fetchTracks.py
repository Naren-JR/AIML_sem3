"""Fetch mapped circuit sections and session JSONs without GitHub REST API calls.

Uses public GitHub HTML directory pages for discovery and raw.githubusercontent.com
for file downloads, avoiding REST API rate limits. It fetches only mapped Grand Prix
folders; unmapped events are excluded and no substitute circuit is ever used.

Run from trackData: python fetchTracks_v5.py
Optional: python fetchTracks_v5.py --root "<project-root>/trackData"
"""
from __future__ import annotations
import argparse, ast, json, re, sys, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

OWNER, REPO, BRANCH = "TracingInsights", "2026", "main"
BASE = f"https://github.com/{OWNER}/{REPO}"
RAW = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}"
USER_AGENT = "Mozilla/5.0 (compatible; Project-AIML-F1-fetcher/5.0)"
SESSION_FILES = {"cor.json", "corners.json", "rcm.json", "weather.json"}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs=[]
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href: self.hrefs.append(href)

def get_bytes(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"})
            with urlopen(req, timeout=45) as r: return r.read()
        except HTTPError as e:
            last=e
            if e.code not in (429,500,502,503,504) or attempt == retries:
                raise RuntimeError(f"HTTP {e.code} fetching {url}. {('GitHub may be rate-limiting or blocking requests.' if e.code in (403,429) else '')}") from e
        except (URLError, TimeoutError) as e:
            last=e
            if attempt == retries: raise RuntimeError(f"Network failure fetching {url}: {e}") from e
        delay = 2 ** (attempt + 1)
        print(f"  Temporary fetch error; retrying in {delay}s: {url}", file=sys.stderr)
        time.sleep(delay)
    raise RuntimeError(f"Failed fetching {url}: {last}")

def parse_mapping(text: str) -> dict[str,str]:
    m = re.search(r"(?ms)^EVENT_SECTIONS_FILE\s*=\s*(\{.*?^\})", text)
    if not m: raise ValueError("Could not find EVENT_SECTIONS_FILE dictionary in SQ.py")
    obj=ast.literal_eval(m.group(1))
    if not isinstance(obj,dict): raise ValueError("EVENT_SECTIONS_FILE is not a dictionary")
    return {k.strip():v.strip() for k,v in obj.items() if isinstance(k,str) and isinstance(v,str)}

def list_html_dir(path: str) -> list[tuple[str,str]]:
    """Return (name, type) for immediate children on a public GitHub HTML tree page."""
    url = f"{BASE}/tree/{BRANCH}" + ("/" + quote(path, safe="/") if path else "")
    raw = get_bytes(url).decode("utf-8", errors="replace")
    parser=LinkParser(); parser.feed(raw)
    prefix=f"/{OWNER}/{REPO}/tree/{BRANCH}/"
    fileprefix=f"/{OWNER}/{REPO}/blob/{BRANCH}/"
    found={}
    for href in parser.hrefs:
        if href.startswith(prefix):
            rel=unquote(href[len(prefix):].split("?",1)[0].split("#",1)[0]).strip("/")
            if not rel or (path and not rel.startswith(path + "/")): continue
            rest=rel[len(path)+1:] if path else rel
            if not rest or "/" in rest: continue
            found[rest]="dir"
        elif href.startswith(fileprefix):
            rel=unquote(href[len(fileprefix):].split("?",1)[0].split("#",1)[0]).strip("/")
            if not rel or (path and not rel.startswith(path + "/")): continue
            rest=rel[len(path)+1:] if path else rel
            if not rest or "/" in rest: continue
            found[rest]="file"
    if not found:
        # HTML structure can change; fail loudly rather than silently claiming no files.
        raise RuntimeError(f"Could not discover directory entries from {url}. Check connectivity or GitHub's page response.")
    return sorted(found.items())

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args=ap.parse_args(); root=args.root.resolve()
    sections_dir=root/"raw"/"sections"; sessions_root=root/"raw"/"sessions"; reports=root/"reports"
    sections_dir.mkdir(parents=True,exist_ok=True); sessions_root.mkdir(parents=True,exist_ok=True); reports.mkdir(parents=True,exist_ok=True)
    print(f"Repository: {OWNER}/{REPO} ({BRANCH})")
    print(f"Output root: {root}")
    print("Reading event-to-section mapping from SQ.py...")
    mapping=parse_mapping(get_bytes(f"{RAW}/SQ.py").decode("utf-8"))
    # Use the mapping as the allow-list. Do not infer substitutions for unmapped events.
    excluded_events = {"Bahrain Grand Prix", "Chinese Grand Prix", "Japanese Grand Prix", "Spanish Grand Prix"}
    events=sorted(e for e in mapping if e.endswith("Grand Prix") and e not in excluded_events)
    print("Discovering mapped event folders and section files via public HTML pages...")
    try:
        section_entries=dict(list_html_dir("sections"))
    except Exception as e:
        print(f"ERROR listing sections: {e}",file=sys.stderr); return 2
    available={Path(n).stem for n,t in section_entries.items() if t=="file" and n.lower().endswith(".json")}
    rows=[]; session_rows=[]; failures=[]; n_sections=0; n_sessions=0
    for event in events:
        stem=mapping[event]; exists=stem in available
        status="no_mapping"; local=None
        if exists:
            try:
                payload=get_bytes(f"{RAW}/sections/{quote(stem)}.json")
                obj=json.loads(payload.decode("utf-8"))
                if not isinstance(obj,list): raise ValueError("Section JSON should contain a list")
                dest=sections_dir/f"{stem}.json"; dest.write_bytes(payload)
                local=str(dest.relative_to(root)); status="downloaded"; n_sections+=1
            except Exception as e:
                status="download_failed"; failures.append({"event":event,"file":f"{stem}.json","error":str(e)})
        elif stem:
            status="mapped_file_missing"
        rows.append({"event_name":event,"section_file_stem":stem,"section_file":f"{stem}.json" if stem else None,
                     "local_path":f"raw/sections/{stem}.json" if exists and status=="downloaded" else None,
                     "repository_file_available":exists,"status":status,
                     "source_url":f"{RAW}/sections/{quote(stem)}.json" if exists else None})
        print(f"  {event}: {stem}.json [{status}]" if stem else f"  {event}: no section mapping [no_mapping]")
        # Only mapped Grand Prix events are inspected for session files.
        try:
            event_children=list_html_dir(event)
            pending=[(event,name,kind) for name,kind in event_children]
            while pending:
                parent,name,kind=pending.pop()
                rel=f"{parent}/{name}"
                if kind=="dir":
                    try:
                        children=list_html_dir(rel)
                        pending.extend((rel,cn,ct) for cn,ct in children)
                    except Exception as e:
                        failures.append({"event":event,"path":rel,"error":str(e)})
                        print(f"    WARNING: could not inspect {rel}: {e}",file=sys.stderr)
                    continue
                if name not in SESSION_FILES: continue
                try:
                    payload=get_bytes(f"{RAW}/{quote(rel,safe='/')}")
                    obj=json.loads(payload.decode("utf-8"))
                    if not isinstance(obj,(dict,list)): raise ValueError("Expected JSON object or array")
                    parts=PurePosixPath(rel).parts
                    session=parts[1] if len(parts)>=3 else "unknown-session"
                    dest=sessions_root/event/session/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(payload)
                    session_rows.append({"event_name":event,"session_name":session,"file_name":name,"repository_path":rel,
                                         "local_path":str(dest.relative_to(root)),"source_url":f"{RAW}/{quote(rel,safe='/')}","status":"downloaded"})
                    n_sessions+=1; print(f"    {session}/{name} [downloaded]")
                except Exception as e:
                    failures.append({"event":event,"file":rel,"error":str(e)})
                    session_rows.append({"event_name":event,"repository_path":rel,"file_name":name,"status":"download_failed","error":str(e)})
        except Exception as e:
            failures.append({"event":event,"path":event,"error":str(e)})
            print(f"    WARNING: could not discover session files for {event}: {e}",file=sys.stderr)
        time.sleep(0.15)
    # Record excluded unmapped events explicitly based on prior requested exclusion rule.
    excluded=["Bahrain Grand Prix","Chinese Grand Prix","Japanese Grand Prix","Spanish Grand Prix"]
    for event in excluded:
        if event not in mapping:
            rows.append({"event_name":event,"section_file_stem":None,"section_file":None,"local_path":None,
                         "repository_file_available":False,"status":"no_mapping_excluded","source_url":None})
    outmap={"source_repository":f"https://github.com/{OWNER}/{REPO}","source_branch":BRANCH,
            "mapping_source":f"{RAW}/SQ.py (EVENT_SECTIONS_FILE)","sections_source":f"{RAW}/sections/",
            "fetched_at_utc":datetime.now(timezone.utc).isoformat(),
            "scope_note":"Fetch-only. Session files fetched only under mapped Grand Prix folders. Bahrain, China, Japan, Spain remain excluded when unmapped; no substitute circuits used.",
            "events":rows,"session_files":session_rows}
    map_path=root/"circuitMap.json"; map_path.write_text(json.dumps(outmap,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    report={"event_folders_discovered":len(events),"event_section_mapping_entries":len(mapping),"section_json_files_available":len(available),
            "section_files_downloaded":n_sections,"session_json_files_downloaded":n_sessions,"session_file_names_requested":sorted(SESSION_FILES),
            "session_file_results":session_rows,"events_without_mapping":sum(r["status"].startswith("no_mapping") for r in rows),
            "mapped_files_missing_from_sections":sum(r["status"]=="mapped_file_missing" for r in rows),"download_failures":failures,
            "output_map":str(map_path),"download_directory":str(sections_dir),"completed_at_utc":datetime.now(timezone.utc).isoformat()}
    rp=reports/"fetch_tracks_report.json"; rp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("\nDone."); print(f"Section files downloaded: {n_sections}"); print(f"Session JSON files downloaded: {n_sessions}")
    print(f"Failures/warnings: {len(failures)}"); print(f"Map: {map_path}"); print(f"Report: {rp}")
    return 1 if failures else 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr); raise SystemExit(2)
