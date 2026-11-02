# Continuous conditional ERS model

This is a physics-based conditional estimator and a mathematical strategy optimizer. No ML training or independent SoC accuracy evaluation exists: electrical labels, battery current/voltage, ICE map, mode activation, and physical battery capacity are unavailable. A single trace is a scenario, not a unique reconstruction. The supplied Project v2 takes precedence over the handbook's earlier single-lap starting scope.

## Source and normalization

The sole active dataset is dataPreprocess/rawData/australiar.csv, attributed by the supplied fetcher to Kimi Antonelli, 2026 Australian GP Race, TracingInsights/2026. The upstream commit and download date were not supplied. SHA-256 identifies the actual local input. The other four CSVs are practice/qualifying and never enter this model. Existing preprocessing and track scripts are preserved unchanged.

Recorded fields remain in recorded and source_fields; the latter preserves original cell text. Numeric missing, nonfinite, and invalid values normalize to null, never zero. Derived speed/acceleration live in calculated. Model outputs and optimizer results are separate structures. Source units are based on Project v2: time in seconds, speed in km/h, distance in metres, throttle in percent. Brake is binary in this CSV, not percentage. Source acc_x/y/z and x/y/z units are unverified. Source acceleration is never treated as a calibrated sensor.

Original lap IDs were discarded by fetchKimi.py. A transition from relative distance >0.75 to <0.25 increments an inferred lap number. The supplied race has 57 such transitions and 58 inferred laps. Completeness of original lap numbering cannot be proven. Duplicate timestamps at lap boundaries contribute zero energy. Reversed timestamps fail explicitly; they are not silently reordered. Invalid timestamps are excluded and counted. Session time must begin at zero. Lap 1 at time zero is imposed at 100% of the usable window. Energy is NEVER reset at a later lap.

## Equations and units

v = speed / 3.6 [m/s]

a = causal least-squares slope of v versus actual t in the previous 0.6 s [m/s^2]. Require at least two valid speed points spanning >0.05 s. Do not fit across gaps >0.5 s. This reduces, but does not eliminate, derivative noise. It is an offline estimate available at the interval endpoint, not a predictive real-time controller.

F_req = m a + 0.5 rho CdA v^2 + Crr m g [N]

P_w = F_req v / 1000 [kW]; g = 9.80665 m/s^2.

Level road, fixed effective aero, no grade, wind, drivetrain loss, fuel burn, or lateral tyre model. These omissions can dominate the inferred split. RPM, gear and unverified source acceleration are context channels; they do not calibrate ICE power. No Straight Mode activation is inferred from a straight or graphic.

Use effective motor-side power variables d >= 0 for deployment and r >= 0 for regeneration [kW]. They are estimated mechanical-equivalent flows. Effective conversion efficiencies include the unresolved motor/inverter/store losses. These are NOT measured DC bus powers.

d_cap = min(P_deploy_scenario_cap, max(P_w, 0)) when brake is off and throttle > 0; otherwise zero.

d_requested = electric_share * d_cap.

r_requested = min(P_recovery_scenario_cap, regen_fraction * max(-P_w,0)) when brake is on; otherwise zero.

Brake is a gate, not a measurement of regeneration. The chosen regen fraction is explicitly hypothetical; friction braking and road-load effects are not separated from observations. Opposing flows cannot occur simultaneously.

For actual interval delta_t = t_k - t_(k-1), powers are associated with its ending sample. With energy E in MJ:

E_k = E_(k-1) - d_k delta_t / (1000 eta_d) + eta_r r_k delta_t / 1000.

Before integration, limit d to available stored energy and r to store headroom. Apply configured per-lap input-side deployment/recovery budgets if present. These budget counters reset at lap changes; E does not. For delta_t=0 no energy transfers. On unavailable inputs or gaps beyond max_gap_s, power is null and the representative state is held. unknown_duration_s accumulates; subsequent states remain conditional on this hold assumption. This is not knowledge that no energy flowed. There is no credible calibrated uncertainty propagation across gaps.

SOC* = 100 E / E_window; E_0 = E_window.

SOC* denotes fraction of the MODELLED usable window, not absolute electrochemical battery SoC. The 4 MJ swing is not physical battery capacity.

## Accounting and physical constraints

0 <= E <= E_window; 0 <= d <= deployment cap; 0 <= r <= recovery cap; d*r=0.

D = cumulative d delta_t / 1000 [MJ, output-side energy].
R = cumulative r delta_t / 1000 [MJ, incoming motor-side energy].
L = cumulative [(1/eta_d - 1)d + (1-eta_r)r] delta_t / 1000 [MJ].

E = E_0 - D + R - L. Conservation residual is checked at every sample. Energy rejected by headroom or unavailable supply is never counted as accepted recovery or delivered deployment. Missing intervals are excluded from known-flow totals and expressly labelled conditional.

## Parameters and provenance

config/model.json controls all physics. Defaults: mass 800 kg; rho 1.2 kg/m^3; CdA 1 m^2; Crr 0.015; eta_d 0.95; eta_r 0.8; electric share 0.30; regen fraction 0.35. These are illustrative scenario assumptions, not claimed car measurements. Mass is constant; the minimum regulated mass is not assumed equal to race mass. Both 350 kW power caps are effective motor-side research caps inspired by the handbook, NOT verified translations of DC electrical constraints. A conservative bus-interface conversion and actual mode/event limits are needed before compliance claims.

Three complete, independently propagated scenarios use (electric_share, regen_fraction) = (0.30,0.35), (0.15,0.50), (0.50,0.15). Min/max at each time show scenario spread, not statistical confidence bounds, exhaustive physical bounds, or ground-truth accuracy. All scenarios impose the same initial state. A complete feasible-envelope estimator and calibrated latent ICE model remain future research work.

## Regulation audit

Verified on 2026-11-02 against the official FIA index and Section C issue 16, 27 February 2026. The index lists issue 21 dated 19 October 2026 as a later issue. This does NOT establish which rules applied to the supplied race; the CSV contains no event date or rule snapshot.

Issue 16 C5.2.7: 350 kW absolute electrical DC ERS-K ceiling. C5.2.9: 4 MJ maximum energy-store state swing. C5.2.8: speed- and Overtake-dependent propulsion restrictions. C5.2.10: harvesting measured at the CU-K HV DC bus, with event/session-dependent adjustments. C5.2.12 also restricts standing-start deployment. These clauses require an interface conversion and context absent from the CSV. The implemented scenario caps do not prove regulatory compliance. No universal lap recharge number is guessed. The optional lap budgets default to null; null means UNENFORCED, not unlimited permitted recovery. See SOURCES.md.

## Gradient-based optimizer

On-demand selected-lap optimization is separate from estimation. The lap starts at the continuous baseline energy immediately BEFORE its first interval. Recovery remains the accepted baseline recovery. The discharge energy budget is no larger than baseline deployment, making the comparison energy-neutral. This is an offline replay experiment, not a lap-time simulation or whole-race optimal controller. Later laps are not recomputed counterfactually.

Divide samples into B sequential bins (default 40), retaining the baseline deployment shape within each bin. Decision x_j scales baseline deployment in bin j. A_ij is baseline delivered MJ at sample i in bin j, zero elsewhere. Thus d_i delta_t/1000 = (Ax)_i. Baseline is x=1, exactly representable. Samples with zero baseline deployment cannot gain new deployment; this restriction keeps the optimizer in the baseline support. Increasing bins improves resolution but does not remove this limitation.

Let w = A^T (v / max(v)), D be adjacent-bin first differences, lambda=0.02.

Maximize J(x) = w^T x - lambda ||D x||^2.

This favors deployment at higher recorded speed with a smooth multiplier schedule. It is an arbitrary, disclosed allocation proxy; it does not establish faster lap times or reduced race duration. The speed trajectory is fixed recorded data, independent of this hypothetical strategy.

Minimize f=-J with analytic gradient grad f = -w + 2 lambda D^T D x.

Constraints: x>=0; each output power <= sample opportunity cap; cumulative E_i=E_initial+eta_r cumulative R_i - cumulative(Ax)_i/eta_d lies in [0,E_window]; total delivered MJ <= baseline MJ; any configured lap deployment cap also applies. Fixed recovery already satisfies the model's configured recovery cap. Each sample is constrained, not only bin endpoints. No simultaneous deployment/recovery. This convex quadratic with linear constraints is solved by SciPy SLSQP using analytic objective and constraint gradients. It uses sequential gradient-based constrained steps; no training is involved. ftol defaults to 1e-8, max iterations 150. Return actual solver status; feasible early stops are not labelled converged.

History stores accepted iteration objective and maximum constraint violation. Final feasibility tolerance is 1e-6. Tiny floating-point energy negatives may appear within that tolerance; exported values are not clipped to conceal residuals. Tests compare analytic and central numerical gradients, feasibility, objective, reproducibility, and budget. A successful solver result establishes only this model's feasible proxy allocation. Each run stores SHA-256, full model/config, algorithm version, history, strategy, and deterministic content-derived ID. Identical config/input reuse the same result ID. A single-process background job supplies running/completed/failed status; per-iteration progress becomes available after completion.

## Lookup, map, and frontend contracts

Selected lap/distance uses nearest recorded distance and returns its exact sample_id and model state; no interpolation and no synthetic samples. Out-of-range distance is rejected. The frontend keeps one distance selection and derives the same nearest sample locally from backend-normalized records. Charts, slider, readouts, and map marker use that sample.

Independent processed geometry/landmarks are absent. The map uses x/y and distance paired by the SAME telemetry row. Click mapping is enabled only for >=20 valid, varied coordinate points with distance progression nondecreasing within 1 m tolerance. It selects the nearest displayed sample in the source coordinate frame. This verifies row correspondence, not physical distance accuracy, a globally invertible circuit alignment, or external survey coordinates. At close/overlapping branches the spatial click may be ambiguous; slider remains authoritative. No corners or aero zones are synthesized.

## Validation and unresolved limitations

Tests cover initial condition, all 57 observed boundaries, no lap resets, conservation, nonnegative energy, caps, lap budgets, missing/null signals, invalid chronology, point identity, optimizer gradient/convergence/feasibility/reproducibility, API errors and response structure, and shared frontend selection. Test fixtures include synthetic edge cases, explicitly distinguished from real-data experiments.

Validation is constraint-only. Without electrical references, MAE/RMSE for true ERS state are undefined and not reported. No uncertainty calibration, ICE-demand fit, manufacturer power map, trained ML, tyre/traffic/weather controller, verified Standing Start/Overtake/Straight Mode state, event regulatory certification, or performance model exists. The estimator can reach empty storage frequently; that is a consequence of assumed splits, not evidence the real driver ran out of electrical energy. Original fetch timing is cumulative sums of per-lap durations; any source alignment error is inherited. Further reference data and physics calibration are required for scientific claims.


## Reserve-aware scenario policy update

The baseline now preserves a configurable reserve_fraction (default 0.20 of the modelled window). This is an illustrative control-policy assumption, NOT a measured state or FIA requirement. Deployment is multiplied by min(1, max(0,E-reserve)/(deployment_taper_fraction * E_window)), with taper width default 0.40. A zero taper width disables gradual taper but retains the reserve floor. Accepted discharge cannot consume the reserve. The optimizer enforces the same reserve at each sample. Neither policy forces recharge or a finishing SoC of 90–100%. No additional harvesting mechanism has been fabricated; recovery remains the disclosed braking-only scenario. This policy addresses depletion behaviour, not latent-state identifiability. Setting both new parameters to zero reproduces the earlier depletion policy. Older exports remain historical runs; the regenerated reproduction manifest identifies the updated run.
