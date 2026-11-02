"""python -m scripts.reproduce --lap 2"""
import argparse
from dataclasses import asdict
import csv
import importlib.metadata
import json
from pathlib import Path
import platform
from backend.data import Dataset, ROOT
from backend.model import Model
from backend.optimizer import optimize


def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lap',type=int,default=2)
    args=parser.parse_args()
    dataset=Dataset();model=Model(dataset);result=optimize(dataset,model,args.lap)
    out=ROOT/'results';(out/'optimization').mkdir(parents=True,exist_ok=True)
    write_csv(out/'model.csv',model.rows)
    write_csv(out/'optimized_strategy.csv',result['strategy'])
    (out/'model_summary.json').write_text(json.dumps({'dataset':dataset.metadata(),'model':model.status},indent=2),encoding='utf-8')
    (out/'optimization'/f"{result['run_id']}.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    metadata={'dataset_sha256':dataset.sha256,'parameters':asdict(model.parameters),'optimizer_run_id':result['run_id'],
              'python':platform.python_version(),'dependencies':{name:importlib.metadata.version(name) for name in ['numpy','scipy','fastapi','pandas']},
              'model_samples':len(model.rows),'inferred_laps':len(dataset.laps),
              'optimizer_status':result['status'],'validation':'constraint-only; not ground-truth SoC accuracy'}
    (out/'reproduction.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
