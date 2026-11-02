from dataclasses import replace
import math
import numpy as np
import pytest
from backend.data import Dataset
from backend.model import Parameters, estimate
from backend.optimizer import objective, optimize


def sample(i, time, lap=1, speed=180, acceleration=1, brake=0):
    return {'sample_id': i, 'lap': lap, 'recorded': {'time':time,'distance':i*10,'speed':speed,'throttle':100,'brake':brake},
            'calculated':{'speed_mps':None if speed is None else speed/3.6,'acceleration_mps2':acceleration}}


def test_initial_and_all_lap_boundaries(dataset, model):
    assert model.rows[0]['soc_pct'] == 100
    boundaries = 0
    for prev, row in zip(model.rows,model.rows[1:]):
        if prev['lap'] != row['lap']:
            boundaries += 1
            assert row['dt_s'] == 0
            assert row['remaining_energy_mj'] == prev['remaining_energy_mj']
    assert boundaries == 57
    assert model.rows[746]['soc_pct'] < 100


def test_conservation_and_bounds(model):
    p = model.parameters
    for row in model.rows:
        assert -1e-12 <= row['remaining_energy_mj'] <= p.energy_window_mj + 1e-12
        assert abs(row['conservation_residual_mj']) < 1e-9
        assert (row['deployment_kw'] or 0) <= p.max_deployment_kw + 1e-10
        assert (row['recovery_kw'] or 0) <= p.max_recovery_kw + 1e-10
        assert (row['deployment_kw'] or 0) * (row['recovery_kw'] or 0) == 0


def test_missing_does_not_become_zero_and_gap_is_held():
    samples=[sample(0,0),sample(1,.2,speed=None),sample(2,2),sample(3,2.2)]
    rows=estimate(samples,Parameters())
    assert rows[1]['deployment_kw'] is None
    assert rows[2]['deployment_kw'] is None
    assert rows[0]['remaining_energy_mj'] == rows[2]['remaining_energy_mj']
    assert rows[3]['unknown_duration_s'] == 2


def test_zero_power_and_brake_not_automatic_regen():
    p=Parameters(electric_share=0,regen_fraction=0)
    rows=estimate([sample(0,0),sample(1,.2),sample(2,.4,brake=1,acceleration=-10)],p)
    assert all(r['soc_pct']==100 for r in rows)
    rows=estimate([sample(0,0),sample(1,.2,brake=1,acceleration=3)],Parameters())
    assert rows[1]['recovery_kw']==0


def test_lap_budgets_and_recovery_headroom():
    samples=[sample(0,0)]+[sample(i,i*.2,lap=1 if i<15 else 2,acceleration=10 if i<10 else -20,brake=0 if i<10 else 1) for i in range(1,30)]
    p=Parameters(energy_window_mj=.1,deployment_budget_mj_per_lap=.01,recovery_budget_mj_per_lap=.005)
    rows=estimate(samples,p)
    assert all(r['lap_deployed_mj'] <= .01+1e-12 and r['lap_recovered_mj']<=.005+1e-12 for r in rows)
    assert min(r['remaining_energy_mj'] for r in rows)>=-1e-12
    assert max(r['remaining_energy_mj'] for r in rows)<=.1+1e-12


@pytest.mark.parametrize('kwargs',[{'energy_window_mj':0},{'eta_discharge':1.1},{'electric_share':-1},{'mass_kg':math.nan}])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        Parameters(**kwargs)


def test_position_lookup_matches_recorded_sample(dataset,model):
    s=dataset.point(4,2000)
    assert s in dataset.lap(4)
    assert model.by_id[s['sample_id']]['distance_m']==s['recorded']['distance']
    assert s['source_fields']['speed']==str(s['source_fields']['speed'])
    with pytest.raises(ValueError):dataset.point(1,999999)
    with pytest.raises(KeyError):dataset.point(999,10)


def test_analytic_gradient():
    x=np.array([.3,1,.8,1.1]);weights=np.array([1,.5,.7,1.2]);eps=1e-6
    analytic=objective(x,weights,.02)[1]
    numeric=np.array([(objective(x+np.eye(4)[i]*eps,weights,.02)[0]-objective(x-np.eye(4)[i]*eps,weights,.02)[0])/(2*eps) for i in range(4)])
    np.testing.assert_allclose(analytic,numeric,atol=1e-8)


def test_optimizer_convergence_feasibility_and_determinism(dataset,model):
    result=optimize(dataset,model,2)
    repeat=optimize(dataset,model,2)
    assert result['run_id']==repeat['run_id']
    assert result['status']=='converged'
    assert result['feasible'] and result['objective_not_worse']
    assert result['optimized_deployed_mj']<=result['baseline_deployed_mj']+1e-8
    assert result['optimized_objective']>=result['baseline_objective']
    assert result['max_constraint_violation']<1e-7
    assert len(result['history'])>2
    for row in result['strategy']:
        assert -1e-8<=row['optimized_energy_mj']<=model.parameters.energy_window_mj+1e-8
        assert -1e-8<=row['optimized_kw']<=model.parameters.max_deployment_kw+1e-7
    np.testing.assert_allclose([r['optimized_kw'] for r in result['strategy']],[r['optimized_kw'] for r in repeat['strategy']])


def test_invalid_source(tmp_path):
    path=tmp_path/'bad.csv'
    path.write_text('time,distance,rel_distance,speed\n0,0,0,10\n1,2,.1,\n.5,3,.2,20\n')
    with pytest.raises(ValueError,match='Time reversal'):Dataset(path)
    path.write_text('time,distance,rel_distance,speed\n0,0,0,10\n.2,2,.1,\n')
    d=Dataset(path)
    assert d.samples[1]['recorded']['speed'] is None
    assert d.samples[1]['calculated']['acceleration_mps2'] is None


def test_reserve_policy():
    p=Parameters(reserve_fraction=.2,deployment_taper_fraction=.4)
    rows=estimate([sample(i,i*.2,acceleration=10) for i in range(1000)],p)
    assert min(r['remaining_energy_mj'] for r in rows)>=.8-1e-10
    assert rows[-1]['deployment_kw']<rows[10]['deployment_kw']
    assert rows[-1]['cumulative_recovered_mj']==0
    assert max(abs(r['conservation_residual_mj']) for r in rows)<1e-9
