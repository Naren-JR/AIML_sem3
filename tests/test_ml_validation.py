import numpy as np
from backend.ml_validation import target, run_validation, saved_validation


def test_labels_and_ambiguity():
    assert target({'brake':1,'throttle':100}) == 0
    assert target({'brake':0,'throttle':5}) == 1
    assert target({'brake':0,'throttle':94}) == 2
    assert target({'brake':0,'throttle':95}) == 3
    assert target({'brake':None,'throttle':40}) is None


def test_actual_race_holdout_metrics(dataset,tmp_path,monkeypatch):
    monkeypatch.setattr('backend.ml_validation.RESULT',tmp_path/'ml.json')
    r=run_validation(dataset)
    split=r['split']
    assert max(split['train_laps']) < min(split['purged_laps']) < min(split['test_laps'])
    assert len(r['predictions'])==split['test_samples']
    assert not {'throttle','brake'} & set(r['features'])
    matrix=np.array(r['metrics']['confusion_matrix'])
    assert matrix.sum()==split['test_samples']
    assert abs(matrix.trace()/matrix.sum()-r['metrics']['accuracy'])<1e-12
    assert 0<=r['metrics']['macro_f1']<=1
    assert saved_validation(dataset)['status']=='ready'
