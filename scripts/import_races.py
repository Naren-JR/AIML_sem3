"""Download three pinned TracingInsights ANT races with original lap/session clocks."""
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from backend.data import ROOT

COMMIT = 'e8cf4fe5121447409fa0cb3728255f261cfc8d62'
RACES = {'australian-grand-prix':'Australian Grand Prix', 'austrian-grand-prix':'Austrian Grand Prix', 'italian-grand-prix':'Italian Grand Prix'}
FIELDS = ['time','rpm','speed','gear','throttle','brake','distance','rel_distance','DistanceToDriverAhead','acc_x','acc_y','acc_z','x','y','z','lap_number','lap_time','session_time']


def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={'User-Agent':'AIML-F1-research-import'}),timeout=45) as f:
                return f.read()
        except OSError:
            if attempt==3:raise
            time.sleep(attempt+1)


def import_race(key,event):
    folder=ROOT/f'dataPreprocess/rawData/2026/{key}'
    raw=folder/'source';raw.mkdir(parents=True,exist_ok=True)
    base=f'https://raw.githubusercontent.com/TracingInsights/2026/{COMMIT}/'
    prefix=f'{event}/Race/ANT/'
    def source(path,filename):
        url=base+quote(path,safe='/')
        dest=raw/filename
        payload=dest.read_bytes() if dest.exists() else fetch(url)
        value=json.loads(payload)
        dest.write_bytes(payload)
        return value,{'path':path,'url':url,'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
    times,record=source(prefix+'laptimes.json','laptimes.json')
    session,srecord=source(f'{event}/Race/session_info.json','session_info.json')
    starts=dict(zip(times['lap'],times['lST']))
    laps=sorted(starts)
    if laps!=list(range(1,max(laps)+1)):raise ValueError('Original lap sequence is incomplete')
    origin=float(starts[1])
    def one(lap):
        payload,meta=source(prefix+f'{lap}_tel.json',f'{lap}_tel.json')
        tel=payload['tel']
        n=len(tel['time'])
        if not n or any(len(v)!=n for v in tel.values() if isinstance(v,list)):
            raise ValueError(f'Empty/mismatched lap {lap}')
        if starts[lap] is None:raise ValueError(f'No original session start for lap {lap}')
        rows=[]
        for i,t in enumerate(tel['time']):
            if t is None:raise ValueError('Missing sample clock')
            row={k:tel.get(k,[None]*n)[i] for k in FIELDS[:15]}
            row.update(time=round(float(starts[lap])+float(t)-origin,9),lap_number=lap,lap_time=t,session_time=round(float(starts[lap])+float(t),9))
            rows.append(row)
        return lap,rows,meta
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        downloaded=sorted(pool.map(one,laps))
    rows=[r for _,part,_ in downloaded for r in part]
    if abs(rows[0]['time'])>1e-8 or any(b['time']<a['time'] for a,b in zip(rows,rows[1:])):
        raise ValueError(f'{event}: nonmonotonic original session clock')
    temp=folder/'telemetry.tmp'
    with temp.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    output=folder/'telemetry.csv';temp.replace(output)
    manifest={'schema_version':1,'circuit_id':key,'event':event,'driver':'Kimi Antonelli','driver_code':'ANT','session':'GP Race','year':2026,
              'repository':'https://github.com/TracingInsights/2026','commit':COMMIT,'laps':laps,'samples':len(rows),
              'clock':'original lST + lap-local telemetry time, relative to lap-1 start; no compression of red-flag gaps',
              'telemetry_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'session_total_laps':session.get('total_laps'),'files':[record,srecord]+[m for _,_,m in downloaded],
              'original_source_fields':'Complete per-lap JSON retained unchanged in source/. Selected numeric channels exported for model; no mode activation inferred.'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'{key}: {len(laps)} original laps, {len(rows)} samples imported',flush=True)


if __name__=='__main__':
    for key,event in RACES.items():import_race(key,event)
