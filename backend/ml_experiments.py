"""Multi-track temporal and cross-track experiments, with isolated result identities."""
import hashlib
import json
from pathlib import Path
from threading import Lock
from .data import ROOT
from .races import load_race, available_races
from .ml_validation import run_validation

GUARD = Lock()


def experiment_key(mode, train_track, test_track):
    if mode not in ('within_track','cross_track'):
        raise ValueError('Unsupported experiment mode')
    if mode=='within_track' and train_track!=test_track:
        raise ValueError('Within-track mode requires identical tracks')
    if mode=='cross_track' and train_track==test_track:
        raise ValueError('Cross-track mode requires different tracks')
    a,b=load_race(train_track),load_race(test_track)
    identity={'mode':mode,'train_track':train_track,'test_track':test_track,'train_sha256':a.sha256,'test_sha256':b.sha256,
              'source_sha256':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['ml_validation.py','ml_experiments.py','data.py']}}
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20],identity


def experiment_status(mode,train_track,test_track):
    key,identity=experiment_key(mode,train_track,test_track)
    path=ROOT/f'results/ml_experiments/{key}.json'
    if not path.exists():return {'status':'not_run','experiment_id':key,'configuration':identity}
    return {'status':'ready','experiment_id':key,'result':json.loads(path.read_text(encoding='utf-8'))}


def experiment(mode,train_track,test_track):
    key,identity=experiment_key(mode,train_track,test_track)
    result=run_validation(load_race(train_track),load_race(test_track) if mode=='cross_track' else None,persist=False)
    result.update(experiment_id=key,configuration=identity)
    path=ROOT/f'results/ml_experiments/{key}.json';path.parent.mkdir(exist_ok=True,parents=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)
    return {'status':'ready','experiment_id':key,'result':result}
