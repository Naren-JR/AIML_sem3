from fastapi.testclient import TestClient
from backend.api import create_app


def test_api_contract_and_point(dataset,tmp_path,monkeypatch):
    monkeypatch.setattr('backend.api.RESULTS',tmp_path)
    with TestClient(create_app(dataset)) as client:
        assert client.get('/api/health').json()['status']=='ok'
        assert client.get('/api/dataset').json()['session']=='GP Race'
        assert len(client.get('/api/laps').json())==58
        lap=client.get('/api/telemetry/lap/2').json()
        ers=client.get('/api/ers/lap/2').json()
        assert len(lap['samples'])==len(ers['samples'])
        point=client.get('/api/telemetry/point',params={'lap':2,'distance':1000}).json()
        assert point['telemetry']['sample_id']==point['estimated']['sample_id']
        assert client.get('/api/ers/point',params={'lap':2,'distance':1000}).json()==point
        assert client.get('/api/telemetry/lap/999').status_code==404
        assert client.get('/api/telemetry/point?lap=1&distance=999999').status_code==422
        assert client.get('/api/ers/point?lap=1&distance=nan').status_code==422
        assert client.post('/api/optimization/run',json={'lap':2,'bins':0}).status_code==422
        assert client.post('/api/optimization/run',json={'lap':2,'unexpected':1}).status_code==422
        response=client.post('/api/optimization/run',json={'lap':2})
        assert response.status_code==202
        status=client.get('/api/optimization/status').json()
        assert status['status']=='completed',status
        result=client.get('/api/optimization/results/'+status['run_id']).json()
        assert result['feasible']
        assert len(client.get('/api/optimization/results').json())==1
        assert client.get('/api/optimization/results/not-an-id').status_code==422
        track=client.get('/api/track/2').json()
        assert all(p['sample_id'] in {s['sample_id'] for s in lap['samples']} for p in track['points'])
        assert client.get('/api/model/status').json()['trained_ml'] is False
        assert client.get('/api/methodology').status_code==200
        reference = client.get('/api/track-reference').json()
        assert reference['available'] and len(reference['geometry']) == 618
        assert reference['telemetry_aligned'] is False
        assert reference['aero_zone_rows'] == 0
        assert client.get('/api/ers/point?lap=2&distance=0').status_code == 200
        evidence = client.get('/api/track-report').json()
        assert len(evidence['warnings']) == 103
        assert all(c['usable_in_model'] is False for c in evidence['candidates'])
        sheet = client.get('/api/track-report/review-sheet')
        assert sheet.status_code == 200 and sheet.headers['content-type'] == 'image/png'


def test_missing_dataset_service(monkeypatch):
    def fail():raise FileNotFoundError('Race file unavailable')
    monkeypatch.setattr('backend.api.Dataset',fail)
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json()['status']=='degraded'
        assert client.get('/api/dataset').status_code==503
