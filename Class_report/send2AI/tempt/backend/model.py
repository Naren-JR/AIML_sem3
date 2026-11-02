"""Conditional road-load ERS estimate at the motor-side power interface."""
from dataclasses import dataclass, asdict, replace
import json
from .data import ROOT


@dataclass(frozen=True)
class Parameters:
    energy_window_mj: float = 4
    max_deployment_kw: float = 350
    max_recovery_kw: float = 350
    recovery_budget_mj_per_lap: float | None = None
    deployment_budget_mj_per_lap: float | None = None
    eta_discharge: float = .95
    eta_recovery: float = .8
    mass_kg: float = 800
    air_density_kg_m3: float = 1.2
    drag_area_m2: float = 1
    rolling_coefficient: float = .015
    electric_share: float = .3
    regen_fraction: float = .35
    max_gap_s: float = .5
    reserve_fraction: float = .2
    deployment_taper_fraction: float = .4
    regulation_status: str = 'provisional_research_scenario_not_event_compliance'
    regulation_source: str = ''
    parameter_provenance: str = ''

    def __post_init__(self):
        import math
        for key, value in asdict(self).items():
            if isinstance(value, (float, int)) and (not math.isfinite(value) or value < 0):
                raise ValueError(f'{key} must be finite and nonnegative')
        for key in ('energy_window_mj', 'mass_kg', 'max_gap_s'):
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} must be positive')
        for key in ('eta_discharge', 'eta_recovery'):
            if not 0 < getattr(self, key) <= 1:
                raise ValueError(f'{key} must be in (0,1]')
        for key in ('electric_share', 'regen_fraction', 'reserve_fraction', 'deployment_taper_fraction'):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f'{key} must be in [0,1]')

    @classmethod
    def load(cls):
        return cls(**json.loads((ROOT / 'config/model.json').read_text()))


def opportunities(sample, p):
    r, c = sample['recorded'], sample['calculated']
    v, a = c['speed_mps'], c['acceleration_mps2']
    if v is None or a is None or r.get('throttle') is None or r.get('brake') is None:
        return None
    wheel_kw = v * (p.mass_kg * a + .5 * p.air_density_kg_m3 * p.drag_area_m2 * v*v
                    + p.rolling_coefficient * p.mass_kg * 9.80665) / 1000
    # Brake is only a gate. Regen requires signed braking demand AND a scenario fraction.
    brake = r['brake'] > .5
    dep_cap = min(p.max_deployment_kw, max(0, wheel_kw)) if not brake and r['throttle'] > 0 else 0
    rec = min(p.max_recovery_kw, max(0, -wheel_kw) * p.regen_fraction) if brake else 0
    return wheel_kw, dep_cap, rec


def estimate(samples, p):
    energy = p.energy_window_mj
    deployed = recovered = losses = 0.
    lap_dep = lap_rec = 0.
    lap = None
    previous = None
    result = []
    unknown_duration = 0.
    for s in samples:
        if s['lap'] != lap:
            lap, lap_dep, lap_rec = s['lap'], 0., 0.
        t = s['recorded']['time']
        dt = 0 if previous is None else t - previous['recorded']['time']
        if dt < 0:
            raise ValueError('Samples must be chronological')
        # Interval-ending convention; causal acceleration uses data through this endpoint.
        opp = opportunities(s, p)
        valid = opp is not None and dt <= p.max_gap_s
        dep = rec = cap = 0.
        wheel = None if opp is None else opp[0]
        if valid and dt > 0:
            _, cap, rec = opp
            reserve = p.energy_window_mj * p.reserve_fraction
            spendable = max(0., energy - reserve)
            window = p.energy_window_mj * p.deployment_taper_fraction
            taper = min(1., spendable / window) if window > 0 else 1.
            dep = cap * p.electric_share * taper
            dep = min(dep, spendable * 1000 * p.eta_discharge / dt)
            rec = min(rec, (p.energy_window_mj - energy) * 1000 / (p.eta_recovery * dt))
            if p.recovery_budget_mj_per_lap is not None:
                rec = min(rec, max(0, p.recovery_budget_mj_per_lap - lap_rec) * 1000 / dt)
            if p.deployment_budget_mj_per_lap is not None:
                dep = min(dep, max(0, p.deployment_budget_mj_per_lap - lap_dep) * 1000 / dt)
        if not valid and dt > 0:
            unknown_duration += dt
        d, r = dep * dt / 1000, rec * dt / 1000
        energy = energy - d / p.eta_discharge + r * p.eta_recovery
        deployed += d
        recovered += r
        lap_dep += d
        lap_rec += r
        losses += d * (1 / p.eta_discharge - 1) + r * (1 - p.eta_recovery)
        residual = energy - (p.energy_window_mj - deployed + recovered - losses)
        result.append({'sample_id': s['sample_id'], 'lap': lap, 'time_s': t,
                       'distance_m': s['recorded']['distance'], 'dt_s': dt,
                       'soc_pct': 100 * energy / p.energy_window_mj,
                       'remaining_energy_mj': energy, 'deployment_kw': dep if valid else None,
                       'recovery_kw': rec if valid else None, 'deployment_cap_kw': cap if valid else 0,
                       'wheel_power_kw': wheel, 'cumulative_deployed_mj': deployed,
                       'cumulative_recovered_mj': recovered, 'cumulative_losses_mj': losses,
                       'lap_deployed_mj': lap_dep, 'lap_recovered_mj': lap_rec,
                       'conservation_residual_mj': residual, 'valid_interval': valid,
                       'unknown_duration_s': unknown_duration,
                       'state_status': 'conditional_hold_across_missing_intervals' if unknown_duration else 'conditional_estimate'})
        previous = s
    return result


class Model:
    def __init__(self, dataset, parameters=None):
        self.parameters = parameters or Parameters.load()
        self.rows = estimate(dataset.samples, self.parameters)
        # Scenario spread, not confidence bounds or a complete feasible envelope.
        low = estimate(dataset.samples, replace(self.parameters, electric_share=.15, regen_fraction=.5))
        high = estimate(dataset.samples, replace(self.parameters, electric_share=.5, regen_fraction=.15))
        for row, a, b in zip(self.rows, low, high):
            row['scenario_soc_min_pct'] = min(row['soc_pct'], a['soc_pct'], b['soc_pct'])
            row['scenario_soc_max_pct'] = max(row['soc_pct'], a['soc_pct'], b['soc_pct'])
        self.by_id = {s['sample_id']: s for s in self.rows}
        self.status = {'status': 'ready', 'kind': 'conditional_physics_estimation', 'trained_ml': False,
                       'parameters': asdict(self.parameters), 'samples': len(self.rows),
                       'initial_soc_pct': self.rows[0]['soc_pct'], 'final_soc_pct': self.rows[-1]['soc_pct'],
                       'max_conservation_residual_mj': max(abs(r['conservation_residual_mj']) for r in self.rows),
                       'unknown_duration_s': self.rows[-1]['unknown_duration_s'],
                       'validation': 'constraint-only; no independent electrical reference',
                       'uncertainty': 'Three illustrative parameter scenarios, not statistical confidence bounds',
                       'regulatory_compliance': 'unverified; speed/mode/event restrictions unavailable'}
