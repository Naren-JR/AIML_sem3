from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import json
import os
import re
from threading import Lock
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from .data import Dataset, ROOT
from .model import Model
from .optimizer import optimize
from .track_reference import load_reference
from .track_quality import track_quality
from fastapi.responses import FileResponse
from .ml_validation import saved_validation, run_validation
from .circuits import catalog, definition
from . import hybrid

RESULTS = Path(os.getenv('AIML_RESULTS_DIR', str(ROOT / 'results/optimization')))


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    lap: int = Field(ge=1)
    max_iterations: int = Field(default=150, ge=1, le=1000)
    tolerance: float = Field(default=1e-8, ge=1e-12, le=.01)
    regularization: float = Field(default=.02, ge=0, le=10)
    bins: int = Field(default=40, ge=4, le=100)


class HybridRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    test_track: str = hybrid.DEFAULT_TEST


def create_app(dataset=None):
    state = {'dataset': dataset, 'model': None, 'error': None,
             'optimization': {'status': 'idle', 'run_id': None}}
    lock = Lock()

    @asynccontextmanager
    async def lifespan(app):
        try:
            state['dataset'] = state['dataset'] or Dataset()
            state['model'] = Model(state['dataset'])
        except (ValueError, OSError) as e:
            state['error'] = str(e)
        yield

    app = FastAPI(title='AIML–F1 Research API', version='1.0.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv('AIML_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    def ready():
        if state['error'] or state['model'] is None:
            raise HTTPException(503, state['error'] or 'Model is loading')
        return state['dataset'], state['model']

    def get_lap(lap):
        d, m = ready()
        try:
            return d.lap(lap), m
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    @app.get('/api/health')
    def health():
        return {'status': 'degraded' if state['error'] else 'ok', 'error': state['error']}

    @app.get('/api/dataset')
    def dataset_info():
        return ready()[0].metadata()

    @app.get('/api/circuits')
    def circuits():
        return {'circuits': catalog(), 'scope': 'Local circuit references intersected with verified F1 race participation; not every session Kimi has ever driven.'}

    @app.get('/api/circuits/{circuit_id}')
    def circuit(circuit_id: str):
        if definition(circuit_id) is None:
            raise HTTPException(404, 'Circuit unavailable or excluded')
        entry = next((c for c in catalog() if c['id']==circuit_id), None)
        if entry is None:
            raise HTTPException(404, 'No local reference data')
        reference = load_reference(circuit_id)
        section_file=ROOT / ('trackData/raw/sections/'+definition(circuit_id)[3]+'.json')
        sections=json.loads(section_file.read_text(encoding='utf-8-sig')) if section_file.exists() else []
        return {'circuit':entry,'reference':reference,'section_percentages':sections}

    @app.get('/api/laps')
    def laps():
        return ready()[0].laps

    @app.get('/api/telemetry/lap/{lap_number}')
    def telemetry_lap(lap_number: int):
        rows, _ = get_lap(lap_number)
        return {'lap': lap_number, 'samples': rows}

    @app.get('/api/telemetry/point')
    @app.get('/api/ers/point')
    def point(lap: int = Query(ge=1), distance: float = Query(ge=0, allow_inf_nan=False)):
        d, m = ready()
        try:
            s = d.point(lap, distance)
            return {'telemetry': s, 'estimated': m.by_id[s['sample_id']],
                    'lookup': 'nearest recorded distance; no interpolation', 'requested_distance_m': distance}
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.get('/api/ers/lap/{lap_number}')
    def ers_lap(lap_number: int):
        rows, m = get_lap(lap_number)
        return {'lap': lap_number, 'samples': [m.by_id[s['sample_id']] for s in rows]}

    @app.get('/api/model/status')
    def model_status():
        return ready()[1].status

    @app.get('/api/hybrid/tracks')
    def hybrid_tracks():
        return {'tracks':hybrid.catalog()}

    @app.get('/api/hybrid')
    def hybrid_result():
        try:
            response=hybrid.saved()
            if 'result' in response:
                response['result']={k:v for k,v in response['result'].items() if k not in ('hybrid_energy','heldout_manifest')}
            return response
        except (ValueError, OSError) as e:
            raise HTTPException(503, str(e)) from e

    @app.post('/api/hybrid/train')
    def train_hybrid(request: HybridRequest):
        if request.test_track not in hybrid.TRACKS:
            raise HTTPException(422, 'Choose a supported race from the dataset catalogue')
        available=[t['id'] for t in hybrid.catalog() if t['available']]
        if request.test_track not in available:
            raise HTTPException(422, 'Download the selected test dataset first')
        training=[t for t in available if t!=request.test_track]
        if not training:
            raise HTTPException(422, 'Download at least one separate training circuit first')
        if not hybrid.LOCK.acquire(blocking=False):
            raise HTTPException(409, 'Hybrid training is already running')
        try:
            result=hybrid.run(training,request.test_track)
            return {'status':'ready','result':{k:v for k,v in result.items() if k not in ('hybrid_energy','heldout_manifest')}}
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e)) from e
        finally:
            hybrid.LOCK.release()

    @app.get('/api/ml/validation')
    def ml_validation():
        return saved_validation(ready()[0])

    @app.post('/api/ml/validation/run')
    def ml_run():
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'A model operation is in progress')
        try:
            return {'status': 'ready', 'result': run_validation(ready()[0])}
        except (ValueError, ImportError) as e:
            raise HTTPException(422, str(e)) from e
        finally:
            lock.release()

    @app.get('/api/methodology')
    def methodology():
        return {'markdown': (ROOT / 'docs/MODEL.md').read_text(encoding='utf-8'), 'parameters': asdict(ready()[1].parameters)}

    @app.get('/api/track/{lap_number}')
    def track(lap_number: int):
        rows, _ = get_lap(lap_number)
        points = [{'sample_id': s['sample_id'], 'distance_m': s['recorded']['distance'],
                   'x': s['recorded'].get('x'), 'y': s['recorded'].get('y')} for s in rows
                  if all(s['recorded'].get(k) is not None for k in ('x', 'y', 'distance'))]
        distances = [p['distance_m'] for p in points]
        # These are paired same-row observations, not an alignment with external geometry.
        monotonic = all(b >= a - 1 for a, b in zip(distances, distances[1:]))
        mapping = len(points) >= 20 and monotonic and len(set((p['x'], p['y']) for p in points)) >= 20
        return {'points': points, 'click_selection_enabled': mapping,
                'mapping': 'verified same-row telemetry sample_id to lap distance' if mapping else 'unavailable or nonmonotonic',
                'geometry_source': 'Recorded lap trajectory, not independently surveyed circuit geometry',
                'coordinate_units': 'source units, unverified', 'straight_mode': 'activation unavailable',
                'external_reference_status': 'Supplied static reference available separately at /api/track-reference; not aligned to recorded race distances'}

    @app.get('/api/track-reference')
    def track_reference():
        try:
            return load_reference()
        except (OSError, ValueError, KeyError) as e:
            raise HTTPException(503, f'Static reference could not be read: {e}') from e

    @app.get('/api/optimization/status')
    def optimization_status():
        with lock:
            return dict(state['optimization'])

    @app.get('/api/track-report')
    def track_report():
        return track_quality()

    @app.get('/api/track-report/review-sheet')
    def review_sheet():
        path = ROOT / 'reports/straight_mode_map_review_sheet.png'
        if not path.is_file():
            raise HTTPException(404, 'Review sheet unavailable')
        return FileResponse(path, media_type='image/png')

    def execute(payload):
        try:
            d, m = ready()
            result = optimize(d, m, **payload)
            RESULTS.mkdir(parents=True, exist_ok=True)
            path = RESULTS / (result['run_id'] + '.json')
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
            temporary.replace(path)
            with lock:
                state['optimization'] = {'status': 'completed', 'run_id': result['run_id']}
        except Exception as e:
            with lock:
                state['optimization'] = {'status': 'failed', 'error': str(e), 'run_id': None}

    @app.post('/api/optimization/run', status_code=202)
    def run(request: RunRequest, tasks: BackgroundTasks):
        get_lap(request.lap)
        with lock:
            if state['optimization']['status'] == 'running':
                raise HTTPException(409, 'An optimization is already running')
            state['optimization'] = {'status': 'running', 'run_id': None}
        tasks.add_task(execute, request.model_dump())
        return {'status': 'running'}

    @app.get('/api/optimization/results')
    def results():
        output = []
        for path in sorted(RESULTS.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                r = json.loads(path.read_text(encoding='utf-8'))
                output.append({k: v for k, v in r.items() if k not in ('strategy', 'history')})
            except (OSError, ValueError):
                continue
        return output

    @app.get('/api/optimization/results/{run_id}')
    def result(run_id: str):
        if not re.fullmatch('[a-f0-9]{16}', run_id):
            raise HTTPException(422, 'Invalid run id')
        path = RESULTS / (run_id + '.json')
        if not path.is_file():
            raise HTTPException(404, 'Run not found')
        return json.loads(path.read_text(encoding='utf-8'))

    return app


app = create_app()
