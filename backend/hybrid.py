"""Learned one-step dynamics feeding a conditional physics energy model."""
import copy
import hashlib
import json
from pathlib import Path
from threading import Lock
import numpy as np
from .data import ROOT, Dataset
from .model import Parameters, estimate

TRACKS={'australian-grand-prix':'Australia','austrian-grand-prix':'Austria','italian-grand-prix':'Italy',
        'british-grand-prix':'Britain','belgian-grand-prix':'Belgium'}
DEFAULT_TEST='belgian-grand-prix'
OUT=ROOT/'results/hybrid_dynamics.json'
LOCK=Lock()
FEATURES=['previous_speed_mps','previous_rpm','previous_gear','previous_throttle_pct','previous_brake','previous_causal_acceleration_mps2','interval_s']


def catalog():
    entries=[]
    for key,label in TRACKS.items():
        folder=ROOT/'dataPreprocess/rawData/2026'/key
        present=(folder/'manifest.json').exists() and (folder/'telemetry.csv').exists()
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8')) if present else {}
        entries.append({'id':key,'label':label,'available':present,'laps':len(manifest.get('laps',[])),
                        'samples':manifest.get('samples',0)})
    return entries


def load(track):
    if track not in TRACKS:raise ValueError('Unknown track')
    folder=ROOT/f'dataPreprocess/rawData/2026/{track}'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    dataset=Dataset(folder/'telemetry.csv')
    if dataset.sha256!=manifest['telemetry_sha256']:raise ValueError('Source checksum mismatch')
    for sample in dataset.samples:
        sample['lap']=int(sample['recorded']['lap_number'])
    return dataset,manifest


def examples(dataset):
    x,y,index=[],[],[]
    for i in range(1,len(dataset.samples)):
        previous,current=dataset.samples[i-1:i+1]
        a,b=previous['recorded'],current['recorded']
        dt=b['time']-a['time']
        if current['lap']!=previous['lap'] or not .05<=dt<=.5:continue
        features=[a.get('speed'),a.get('rpm'),a.get('gear'),a.get('throttle'),a.get('brake'),previous['calculated']['acceleration_mps2'],dt]
        if b.get('speed') is None or any(v is None or not np.isfinite(v) for v in features):continue
        features[0]/=3.6
        x.append(features);y.append((b['speed']/3.6-features[0])/dt);index.append(i)
    return np.array(x),np.array(y),index


def run(train_tracks, test_track):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from threadpoolctl import threadpool_limits
    import sklearn
    if not train_tracks or len(set(train_tracks))!=len(train_tracks) or test_track in train_tracks:
        raise ValueError('Choose unique training tracks and a completely separate test track')
    datasets={key:load(key) for key in train_tracks+[test_track]}
    prepared={key:examples(d) for key,(d,_) in datasets.items()}
    x=np.concatenate([prepared[t][0] for t in train_tracks]);y=np.concatenate([prepared[t][1] for t in train_tracks])
    xt,yt,indices=prepared[test_track]
    model=HistGradientBoostingRegressor(max_iter=150,max_leaf_nodes=15,learning_rate=.08,early_stopping=False,random_state=42)
    with threadpool_limits(limits=2):
        model.fit(x,y);pred=model.predict(xt)
    def scores(actual,predicted):
        return {'mae':float(mean_absolute_error(actual,predicted)),'rmse':float(mean_squared_error(actual,predicted)**.5),'r2':float(r2_score(actual,predicted))}
    speed_actual=xt[:,0]+yt*xt[:,-1];speed_pred=xt[:,0]+pred*xt[:,-1]
    d,manifest=datasets[test_track];parameters=Parameters.load()
    samples=copy.deepcopy(d.samples)
    for s in samples:s['calculated']['acceleration_mps2']=None
    for i,a,v in zip(indices,pred,speed_pred):
        samples[i]['calculated']['acceleration_mps2']=float(a)
        samples[i]['calculated']['speed_mps']=max(0.,float(v))
    hybrid=estimate(samples,parameters)
    baseline=estimate(d.samples,parameters)
    details=[]
    for j,i in enumerate(indices):
        s=d.samples[i]
        details.append({'sample_id':s['sample_id'],'lap':s['lap'],'distance_m':s['recorded']['distance'],
                        'observed_acceleration_mps2':float(yt[j]),'predicted_acceleration_mps2':float(pred[j]),
                        'observed_speed_mps':float(speed_actual[j]),'predicted_speed_mps':float(speed_pred[j]),
                        'hybrid_soc_pct':hybrid[i]['soc_pct'],'physics_soc_pct':baseline[i]['soc_pct']})
    result={'task':'One-step longitudinal acceleration regression integrated into conditional ERS demand estimation',
            'trained_quantity':'Next-sample longitudinal acceleration derived from recorded speed/time, NOT battery SoC or electrical power',
            'integration':'Predicted acceleration and predicted nonnegative endpoint speed replace the road-load inputs; existing assumed electric split/recovery and energy accounting then produce a conditional energy trace.',
            'features':FEATURES,'train_tracks':train_tracks,'test_track':test_track,'train_samples':len(y),'test_samples':len(yt),
            'acceleration_metrics':scores(yt,pred),'zero_acceleration_baseline':scores(yt,np.zeros_like(yt)),
            'persistence_acceleration_baseline':scores(yt,xt[:,5]),
            'speed_metrics':scores(speed_actual,speed_pred),'constant_speed_baseline':scores(speed_actual,xt[:,0]),
            'model_parameters':model.get_params(),'sklearn_version':sklearn.__version__,
            'energy_parameters':json.loads((ROOT/'config/model.json').read_text()),
            'provenance':{key:{'sha256':data.sha256,'commit':m['commit'],'samples':len(data.samples),'laps':len(m['laps'])} for key,(data,m) in datasets.items()},
            'source_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['hybrid.py','model.py','data.py']},
            'label_audit':'Inspected per-lap TracingInsights telemetry fields: speed/RPM/gear/throttle/brake/position available; no independent battery SoC, voltage/current, or electrical power label.',
            'limitations':['Observed previous samples initialize every one-step prediction; this is not an autonomous multi-lap speed rollout.',
                           'The interval is supplied when evaluating the next recorded sample; this is offline irregular-sampling evaluation.',
                           'Derivative targets amplify speed noise. No tuning or fitting occurs on the held-out track.',
                           'Recorded endpoint throttle/brake still gate energy demand. This energy trace is an offline reconstruction, not a future ERS forecast.',
                           'The electric split, braking-only regeneration, reserve and physical parameters remain assumptions. ML dynamics cannot identify their true values.',
                           'Hybrid SoC versus physics SoC compares two estimates, not prediction against ground truth. No SoC accuracy, F1 or recall is claimed.'],
            'predictions':details,'hybrid_energy':hybrid,'heldout_manifest':manifest}
    OUT.parent.mkdir(exist_ok=True);temp=OUT.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');temp.replace(OUT)
    return result


def saved():
    if not OUT.exists():return {'status':'not_run'}
    result=json.loads(OUT.read_text(encoding='utf-8'))
    if result.get('energy_parameters')!=json.loads((ROOT/'config/model.json').read_text()):return {'status':'stale'}
    for name,sha in result['source_sha256'].items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=sha:return {'status':'stale'}
    for key,meta in result['provenance'].items():
        if load(key)[0].sha256!=meta['sha256']:return {'status':'stale'}
    return {'status':'ready','result':result}
