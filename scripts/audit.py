"""Inventory supplied source files without mutating raw data or fetching substitutes."""
import ast
import csv
import hashlib
import json
import zipfile
from backend.data import ROOT, number


def main():
    report={'telemetry':[],'json':[],'archives':[],'scripts':[],'documents':[],
            'missing_requested':['frontend.zip','frontend handoff','screenshots','circuitMap.json','master_track.json','track_geometry.csv','corners.csv','sections.csv','active_aero_zones.csv','source_manifest.json']}
    for path in sorted((ROOT/'dataPreprocess/rawData').glob('*.csv')):
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);rows=list(reader);fields=reader.fieldnames
        statistics={}
        for k in fields:
            values=[number(r[k]) for r in rows];valid=[v for v in values if v is not None]
            statistics[k]={'missing_or_invalid':len(values)-len(valid),'min':min(valid) if valid else None,'max':max(valid) if valid else None}
        report['telemetry'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(rows),'fields':fields,'statistics':statistics})
    for path in sorted((ROOT/'trackData').rglob('*.json')):
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        report['json'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'type':type(value).__name__,'items':len(value),'schema':list(value) if isinstance(value,dict) else 'list of [category,start_percent,end_percent]','valid_sections':all(isinstance(r,list) and len(r)==3 and isinstance(r[0],str) and isinstance(r[1],(int,float)) and isinstance(r[2],(int,float)) and r[1]<=r[2] for r in value) if isinstance(value,list) else None})
    for path in sorted((ROOT/'trackData').rglob('*.zip')):
        with zipfile.ZipFile(path) as archive:
            report['archives'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'entries':[{'name':n.filename,'size':n.file_size,'crc':n.CRC} for n in archive.infolist()],'integrity_error':archive.testzip()})
    for folder in ['dataPreprocess','trackData']:
        for path in sorted((ROOT/folder).glob('*.py')):
            code=path.read_text(encoding='utf-8-sig');tree=ast.parse(code)
            report['scripts'].append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'lines':len(code.splitlines()),'functions':[node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))],'module_documentation':ast.get_docstring(tree)})
    for path in ROOT.glob('*.pdf'):
        report['documents'].append({'path':path.name,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/source_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"Audited {len(report['telemetry'])} telemetry files, {len(report['json'])} JSON files, {len(report['archives'])} archives, {len(report['scripts'])} scripts and {len(report['documents'])} PDFs")


if __name__=='__main__':main()
