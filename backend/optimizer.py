"""Analytic-gradient convex deployment allocation on a selected recorded lap."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize, LinearConstraint


def objective(x, weights, regularization):
    diff = np.diff(x)
    value = -weights @ x + regularization * (diff @ diff)
    gradient = -weights.copy()
    gradient[:-1] -= 2 * regularization * diff
    gradient[1:] += 2 * regularization * diff
    return float(value), gradient


def optimize(dataset, model, lap, max_iterations=150, tolerance=1e-8, regularization=.02, bins=40):
    samples = dataset.lap(lap)
    rows = [model.by_id[s['sample_id']] for s in samples]
    p = model.parameters
    n = len(rows)
    # One coefficient per sequential bin; baseline ratios retained within each bin.
    # This gives an exactly representable feasible baseline (x=1).
    group = np.minimum(np.arange(n) * bins // n, bins-1)
    active = sorted(set(int(g) for g, r in zip(group, rows) if (r['deployment_kw'] or 0) > 0))
    if not active:
        raise ValueError('Selected lap has no baseline deployment to allocate')
    col = {g: j for j, g in enumerate(active)}
    a = np.zeros((n, len(active)))
    baseline_kw = np.array([r['deployment_kw'] or 0 for r in rows])
    dt = np.array([r['dt_s'] for r in rows])
    base_energy = baseline_kw * dt / 1000
    for i, g in enumerate(group):
        if int(g) in col:
            a[i, col[int(g)]] = base_energy[i]
    cumulative = np.cumsum(a, axis=0) / p.eta_discharge
    recovery = np.array([(r['recovery_kw'] or 0) * r['dt_s'] / 1000 for r in rows])
    # Recover the state immediately before this lap's first interval, never reset.
    initial = rows[0]['remaining_energy_mj'] + base_energy[0]/p.eta_discharge - recovery[0]*p.eta_recovery
    available = initial + p.eta_recovery * np.cumsum(recovery)
    budget = float(base_energy.sum())
    speeds = np.array([s['recorded']['speed'] or 0 for s in samples])
    weights = (speeds / max(float(speeds.max()), 1)) @ a
    upper = np.full(len(active), 1 / max(p.electric_share, 1e-12))
    for i, g in enumerate(group):
        if baseline_kw[i] > 0:
            upper[col[int(g)]] = min(upper[col[int(g)]], rows[i]['deployment_cap_kw']/baseline_kw[i])
    # Every sample's energy plus total discharge budget; fixed recovery stays within its lap cap.
    matrix = np.vstack([cumulative, a.sum(axis=0)])
    lower = np.r_[available - p.energy_window_mj, 0]
    higher = np.r_[available - p.energy_window_mj * p.reserve_fraction, budget]
    if p.deployment_budget_mj_per_lap is not None:
        higher[-1] = min(higher[-1], p.deployment_budget_mj_per_lap)
    constraints = LinearConstraint(matrix, lower, higher)
    history = []
    def record(x):
        history.append({'iteration': len(history), 'objective': -objective(x, weights, regularization)[0],
                        'max_constraint_violation': float(max(0, np.max(lower-matrix@x), np.max(matrix@x-higher)))})
    x0 = np.ones(len(active))
    record(x0)
    result = minimize(lambda x: objective(x, weights, regularization), x0, jac=True,
                      method='SLSQP', bounds=list(zip(np.zeros(len(active)), upper)),
                      constraints=[constraints], callback=record,
                      options={'maxiter': max_iterations, 'ftol': tolerance})
    x = result.x
    record(x)
    energies = a @ x
    trajectory = available - cumulative @ x
    violation = float(max(0, np.max(lower-matrix@x), np.max(matrix@x-higher), np.max(-x), np.max(x-upper)))
    feasible = violation <= 1e-6
    improved = objective(x, weights, regularization)[0] <= objective(x0, weights, regularization)[0] + 1e-7
    if not feasible:
        raise ValueError(f'Optimizer returned an infeasible strategy ({violation})')
    optimized_kw = np.divide(energies * 1000, dt, out=np.zeros(n), where=dt>0)
    config = {'lap': lap, 'max_iterations': max_iterations, 'tolerance': tolerance,
              'regularization': regularization, 'bins': bins}
    identity = {'dataset_sha256': dataset.sha256, 'model': asdict(p), 'optimizer': config,
                'algorithm_version': 'slsqp-analytic-v1',
                'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                  for name in ('data.py', 'model.py', 'optimizer.py')}}
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return {'run_id': run_id, 'metadata': identity, 'status': 'converged' if result.success else 'iteration_limit_or_solver_stop',
            'solver_message': result.message, 'iterations': int(result.nit), 'history': history,
            'objective': 'Maximize speed-weighted delivered MJ minus squared adjacent-bin multiplier changes; a strategy proxy, not lap time.',
            'gradient': 'Analytic: -w + 2 lambda D^T D x for minimization',
            'horizon': 'Selected lap only, initialized from continuous baseline race. Later laps are not counterfactually recomputed.',
            'baseline_objective': -objective(x0, weights, regularization)[0],
            'optimized_objective': -objective(x, weights, regularization)[0],
            'baseline_deployed_mj': budget, 'optimized_deployed_mj': float(energies.sum()),
            'initial_energy_mj': initial, 'baseline_final_energy_mj': rows[-1]['remaining_energy_mj'],
            'optimized_final_energy_mj': float(trajectory[-1]), 'feasible': feasible,
            'objective_not_worse': bool(improved), 'max_constraint_violation': violation,
            'regulatory_compliance': 'unverified',
            'strategy': [{'sample_id': s['sample_id'], 'distance_m': r['distance_m'],
                          'baseline_kw': float(baseline_kw[i]), 'optimized_kw': float(optimized_kw[i]),
                          'recovery_kw': r['recovery_kw'], 'optimized_energy_mj': float(trajectory[i]),
                          'baseline_energy_mj': r['remaining_energy_mj']} for i, (s, r) in enumerate(zip(samples, rows))]}
