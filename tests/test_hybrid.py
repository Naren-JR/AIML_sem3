import numpy as np
import pytest
from backend.hybrid import load,examples,run,saved,TRACKS


def test_hybrid_inputs_are_previous_sample_and_target_is_observed_derivative():
    d,_=load('italian-grand-prix');x,y,indices=examples(d)
    i=indices[100];a,b=d.samples[i-1:i+1]
    assert x[100,0]==a['recorded']['speed']/3.6
    assert y[100]==pytest.approx((b['recorded']['speed']-a['recorded']['speed'])/3.6/x[100,-1])
    assert a['lap']==b['lap']
    assert np.all((x[:,-1]>=.05)&(x[:,-1]<=.5))


def test_training_is_integrated_and_test_track_is_excluded(tmp_path,monkeypatch):
    monkeypatch.setattr('backend.hybrid.OUT',tmp_path/'hybrid.json')
    result=run(['australian-grand-prix','austrian-grand-prix'],'italian-grand-prix')
    assert result['test_track'] not in result['train_tracks']
    assert result['test_samples']==len(result['predictions'])
    assert result['acceleration_metrics']['mae']<result['zero_acceleration_baseline']['mae']
    assert result['speed_metrics']['mae']<result['constant_speed_baseline']['mae']
    assert all(-1e-9<=r['soc_pct']<=100+1e-9 for r in result['hybrid_energy'])
    assert max(abs(r['conservation_residual_mj']) for r in result['hybrid_energy'])<1e-8
    assert saved()['status']=='ready'
    with pytest.raises(ValueError):run(['italian-grand-prix'],'italian-grand-prix')


def test_hybrid_api_validates_track_and_routes_training(dataset,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api import create_app
    calls=[]
    monkeypatch.setattr('backend.hybrid.saved',lambda:{'status':'not_run'})
    def fit(train,test):
        calls.append((train,test))
        return {'test_track':test}
    monkeypatch.setattr('backend.hybrid.run',fit)
    with TestClient(create_app(dataset)) as client:
        assert client.get('/api/hybrid').json()=={'status':'not_run'}
        assert client.post('/api/hybrid/train',json={'test_track':'missing'}).status_code==422
        assert client.post('/api/hybrid/train',json={'test_track':'italian-grand-prix','extra':1}).status_code==422
        response=client.post('/api/hybrid/train',json={'test_track':'italian-grand-prix'})
        assert response.status_code==200
        assert calls==[([t for t in TRACKS if t!='italian-grand-prix'],'italian-grand-prix')]
        entries=client.get('/api/hybrid/tracks').json()['tracks']
        assert len(entries)==5
        assert all(t['available'] and t['samples']>0 and t['laps']>0 for t in entries)


@pytest.mark.parametrize('track',['british-grand-prix','belgian-grand-prix'])
def test_new_track_provenance_laps_and_chronology(track):
    d,m=load(track)
    assert m['driver_code']=='ANT' and m['commit']=='e8cf4fe5121447409fa0cb3728255f261cfc8d62'
    assert len(d.samples)==m['samples']
    assert set(s['lap'] for s in d.samples)==set(m['laps'])
    assert all(b['recorded']['time']>a['recorded']['time'] for a,b in zip(d.samples,d.samples[1:]))
    x,y,_=examples(d)
    assert len(y)>10000 and x.shape[1]==7
