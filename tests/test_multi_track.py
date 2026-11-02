import numpy as np
import pytest
from backend.races import available_races, load_race
from backend.ml_experiments import experiment, experiment_status
from backend.model import Model
from fastapi.testclient import TestClient
from backend.api import create_app


def test_five_complete_original_races():
    races=available_races()
    assert len(races)==5
    for r in races:
        d=load_race(r['id'])
        assert len(d.laps)==len(d.manifest['laps'])
        assert [l['lap'] for l in d.laps]==d.manifest['laps']
        assert d.metadata()['event']==r['event']
        assert d.samples[0]['recorded']['time']==0
        assert d.manifest['commit']=='e8cf4fe5121447409fa0cb3728255f261cfc8d62'
        assert all(a['recorded']['time']<=b['recorded']['time'] for a,b in zip(d.samples,d.samples[1:]))
    italy=load_race('italian-grand-prix')
    assert italy.quality['large_gaps']>0
    model=Model(italy)
    assert max(r['dt_s'] for r in model.rows)>1000
    assert model.rows[-1]['unknown_duration_s']>1000


def test_cross_track_is_disjoint_and_temporal_split_is_purged(tmp_path,monkeypatch):
    # Redirect result storage through module ROOT; source fingerprints still use module source paths.
    monkeypatch.setattr('backend.ml_experiments.ROOT',tmp_path)
    a,b='australian-grand-prix','austrian-grand-prix'
    r=experiment('cross_track',a,b)['result']
    assert r['train_event']!=r['test_event']
    assert r['configuration']['train_sha256']!=r['configuration']['test_sha256']
    assert r['split']['purged_laps']==[]
    assert len(r['predictions'])==r['split']['test_samples']
    assert sum(map(sum,r['metrics']['confusion_matrix']))==r['split']['test_samples']
    assert experiment_status('cross_track',a,b)['status']=='ready'
    r=experiment('within_track',b,b)['result']
    assert max(r['split']['train_laps'])<min(r['split']['purged_laps'])<min(r['split']['test_laps'])
    with pytest.raises(ValueError):experiment('cross_track',a,a)
    with pytest.raises(ValueError):experiment('within_track',a,b)


def test_selected_track_api_and_validation_errors(dataset):
    with TestClient(create_app(dataset)) as client:
        assert len(client.get('/api/ml/tracks').json()['tracks'])==5
        q={'circuit_id':'italian-grand-prix'}
        info=client.get('/api/dataset',params=q).json()
        assert info['event']=='Italian Grand Prix'
        assert len(client.get('/api/laps',params=q).json())==53
        point=client.get('/api/telemetry/point',params={**q,'lap':2,'distance':1000}).json()
        assert point['telemetry']['lap']==2
        assert point['estimated']['sample_id']==point['telemetry']['sample_id']
        assert client.get('/api/dataset?circuit_id=nonexistent').status_code==404
        assert client.post('/api/ml/experiments/run',json={'mode':'cross_track','train_track':'italian-grand-prix','test_track':'italian-grand-prix'}).status_code==422
        assert client.get('/api/ml/experiments?mode=bad&train_track=italian-grand-prix&test_track=austrian-grand-prix').status_code==422
