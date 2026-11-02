"""Reproducibly import complete ANT race lap telemetry from public TracingInsights."""
import argparse
import csv
import hashlib
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from backend.data import ROOT
from backend.hybrid import TRACKS
from dataPreprocess.fetchKimi import COLUMNS, find_field, rows_from_json

COMMIT='e8cf4fe5121447409fa0cb3728255f261cfc8d62'
EVENTS={key:' '.join(word.title() for word in key.split('-')) for key in TRACKS}


def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={'User-Agent':'AIML-F1-dataset-importer','Accept':'application/vnd.github+json'}),timeout=30) as response:
                return response.read()
        except OSError:
            if attempt==3:raise
            time.sleep(1+attempt)


def number(value):
    if isinstance(value,bool):return int(value)
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):return None


def download(track):
    event=EVENTS[track]
    folder=ROOT/'dataPreprocess/rawData/2026'/track
    manifest_path=folder/'manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['commit']!=COMMIT:raise ValueError('Existing source uses another commit')
        if hashlib.sha256((folder/'telemetry.csv').read_bytes()).hexdigest()!=manifest['telemetry_sha256']:
            raise ValueError('Existing CSV checksum mismatch; refusing to overwrite')
        return manifest
    prefix=f'{event}/Race'
    entries=json.loads(fetch(f'https://api.github.com/repos/TracingInsights/2026/contents/{quote(prefix+"/ANT",safe="/")}?ref={COMMIT}'))
    laps=sorted(int(e['name'].split('_')[0]) for e in entries if re.fullmatch(r'\d+_tel\.json',e['name']))
    if not laps or laps[0]!=1:raise ValueError('Race has no initial lap; cannot initialize energy')
    paths=[f'{prefix}/ANT/laptimes.json',f'{prefix}/session_info.json']+[f'{prefix}/ANT/{lap}_tel.json' for lap in laps]
    source=folder/'source';source.mkdir(parents=True,exist_ok=True)
    def obtain(path):
        url=f'https://raw.githubusercontent.com/TracingInsights/2026/{COMMIT}/{quote(path,safe="/")}'
        content=fetch(url)
        json.loads(content)  # Validate before preserving the original response bytes.
        (source/path.split('/')[-1]).write_bytes(content)
        return {'path':path,'url':url,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
    with ThreadPoolExecutor(max_workers=4) as pool:files=list(pool.map(obtain,paths))
    timing=json.loads((source/'laptimes.json').read_text(encoding='utf-8'))
    starts={int(lap):number(start) for lap,start in zip(timing['lap'],timing['lST'])}
    if any(starts.get(lap) is None for lap in laps):raise ValueError('Missing original lap start time')
    origin=starts[1];rows=[]
    for lap in laps:
        for row in rows_from_json(json.loads((source/f'{lap}_tel.json').read_text(encoding='utf-8'))):
            local=number(find_field(row,'time'))
            if local is None:continue
            absolute=starts[lap]+local
            record={column:number(find_field(row,column)) for column in COLUMNS}
            record.update(time=round(absolute-origin,9),lap_number=lap,lap_time=local,session_time=absolute)
            rows.append(record)
    # Boundary duplicates/overlaps retain the later lap's record at that timestamp.
    rows=sorted({r['time']:r for r in rows}.values(),key=lambda r:r['time'])
    if not rows or rows[0]['time']!=0:raise ValueError('Source must start at the first race sample')
    csv_path=folder/'telemetry.csv';temp=folder/'telemetry.csv.tmp'
    with temp.open('w',encoding='utf-8',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=COLUMNS+['lap_number','lap_time','session_time'])
        writer.writeheader();writer.writerows(rows)
    temp.replace(csv_path)
    manifest={'schema_version':1,'circuit_id':track,'event':event,'driver':'Kimi Antonelli','driver_code':'ANT',
              'session':'GP Race','year':2026,'repository':'https://github.com/TracingInsights/2026','commit':COMMIT,
              'retrieved_at':datetime.now(timezone.utc).isoformat(),'laps':laps,'samples':len(rows),
              'clock':'original lST + lap-local telemetry time, relative to lap-1 start; no compression of gaps',
              'telemetry_sha256':hashlib.sha256(csv_path.read_bytes()).hexdigest(),'files':files,
              'original_source_fields':'Complete per-lap JSON retained unchanged in source/. No electrical labels inferred.'}
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracks',nargs='+',choices=list(TRACKS),default=list(TRACKS))
    args=parser.parse_args()
    for key in args.tracks:
        m=download(key)
        print(f"{key}: {len(m['laps'])} laps, {m['samples']} samples, {m['telemetry_sha256']}",flush=True)
