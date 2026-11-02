# Learned dynamics and conditional energy

Implemented on `readings`. Open `/hybrid` (Hybrid ERS research).

## Data and fitted target

Source: [TracingInsights/2026](https://github.com/TracingInsights/2026), pinned commit `e8cf4fe5121447409fa0cb3728255f261cfc8d62`. Local data are Kimi Antonelli (`ANT`), Race sessions:

| Circuit | Recorded laps | Raw samples | Default role |
|---|---:|---:|---|
| Australia | 58 | 37,569 | Training |
| Austria | 71 | 39,416 | Training |
| Italy | 53 | 36,453 | Training |
| Britain | 52 | 39,370 | Training |
| Belgium | 44 | 38,283 | Entirely held-out test |

Files: `dataPreprocess/rawData/2026/<circuit>/telemetry.csv`, `manifest.json`, and original per-lap JSON under `source/`. Manifests retain the commit, source files and checksums. This pipeline uses recorded lap IDs, unlike the legacy single-race adapter's inferred lap numbering. Large data/results remain Git-ignored; a fresh clone needs these datasets restored.

This is **longitudinal acceleration regression**, using scikit-learn HistGradientBoostingRegressor: 150 iterations, learning rate 0.08, 15 leaf nodes, seed 42, no early stopping. The target is the observed speed change divided by elapsed time, in m/s². It is not battery charge, electrical power, an energy deployment mode, or an optimal control label.

Inputs are previous speed, RPM, gear, throttle, brake, a causal acceleration estimate using only earlier/current history through that previous sample, and the next recorded interval duration. Neither track identity nor the current target speed is an input. Only same-lap intervals from 0.05 to 0.5 seconds with complete inputs are included. Gaps and lap-boundary intervals are excluded. Targets derived from speed contain measurement noise.

The collection totals **278 laps and 191,091 raw samples**. Default fit: **121,389 eligible intervals** from Australia, Austria, Italy and Britain. Evaluation: **30,201 eligible intervals** from Belgium. The test circuit is excluded from fitting and tuning. The API lists downloaded circuits at `GET /api/hybrid/tracks`; the UI uses this catalogue rather than a fixed three-track list.

We compared two fixed training sets on the same Belgian holdout. Model settings were unchanged and were not selected using the test scores:

| Held-out Belgium score | Australia + Austria | Australia + Austria + Italy + Britain |
|---|---:|---:|
| Training intervals | 61,361 | 121,389 |
| Acceleration MAE (m/s²) | 2.5694 | 2.4283 |
| Acceleration RMSE (m/s²) | 4.3739 | 4.2709 |
| Acceleration R² | 0.7293 | 0.7420 |
| Next-speed MAE (m/s) | 0.3980 | 0.3764 |

The additional circuits reduced acceleration MAE by about 5.5% on this holdout. This is one comparison, not evidence that adding any dataset always helps. The previous-acceleration baseline has RMSE 5.4315 m/s² on Belgium. R² is not percentage accuracy. Small one-step speed errors benefit from restarting from observed speed every interval.

The earlier three-circuit experiment (Australia + Austria training, Italy holdout) achieved acceleration MAE 2.1163, RMSE 3.4290 and R² 0.8235. These scores use a different test circuit and cannot be directly compared with Belgium scores. Italy now enters the default expanded training set; it is still excluded when selected as the test circuit.

Repeatedly selecting models using these displayed test scores would require another untouched final test set. The track selector supports exploratory leave-one-circuit-out evaluation, not five independent final tests after model selection.

## Connection to energy

Previous observed speed + predicted acceleration × interval gives predicted endpoint speed. Predicted acceleration and endpoint speed replace the road-load inputs in the existing physics estimator. Recorded endpoint brake/throttle still gate deployment/recovery. Existing mass, drag, rolling resistance, electric split, regeneration fraction, losses and reserve rules calculate a conditional energy trace. State remains continuous, including across laps; missing intervals hold energy conditionally.

The original Overview/ERS/optimizer remains the original physics experiment. The new `/hybrid` page runs and plots the learned-dynamics pipeline separately. Its energy chart compares two estimates, not measured battery charge. ML influences this new energy experiment, but does not learn electrical split or optimal deployment.

Each one-step prediction starts from observed previous telemetry; this is **not an autonomous race rollout** or a prediction of a track without any telemetry. The selected track is unseen during training, but its earlier observations and next sampling interval are available during evaluation.

The imported telemetry has no independent SoC, voltage/current or electrical-power labels. Therefore true battery prediction cannot be trained or validated here. Classification accuracy/F1/precision/recall do not measure this regression task or validate energy estimates. The existing operating-state classifier remains separate.

## Run and inspect

From the repository root in PowerShell, restore/download datasets first if needed (existing checksummed CSVs are retained):

```powershell
.\.venv\Scripts\python -m scripts.fetch_hybrid_data
.\.venv\Scripts\python -m scripts.train_hybrid
.\.venv\Scripts\python -m scripts.dev
```

Open `http://127.0.0.1:5173/hybrid`. Select the unseen test circuit, then click **Train on other circuits & test unseen track**. All other downloaded circuits are training data (four with the complete collection). Inspect acceleration MAE/RMSE/R², next-speed errors, baselines and lap charts. The circuit selector on this page is independent of the legacy static circuit catalogue.

Choose a different holdout or explicit training subset from the CLI:

```powershell
.\.venv\Scripts\python -m scripts.train_hybrid --test-track british-grand-prix
.\.venv\Scripts\python -m scripts.train_hybrid --test-track belgian-grand-prix --train-tracks australian-grand-prix austrian-grand-prix
.\.venv\Scripts\python -m scripts.compare_hybrid_data
```

The comparison command saves `results/hybrid_small_training.json` and `results/hybrid_dataset_comparison.json`, then leaves the expanded Belgian evaluation in the normal output. Source downloads use four concurrent requests, bounded retries, original lap-start timestamps and preserved JSON bytes with SHA-256 hashes. Both new races include all available driver race laps at the pinned source commit. Practice, qualifying and other seasons are not mixed into this training set.

API: `GET /api/hybrid` reads results; `POST /api/hybrid/train` with `{"test_track":"belgian-grand-prix"}` refits/evaluates. Training is synchronous and protected by a process-local lock. Use one API worker. Full results, predictions and conditional energy rows are saved to `results/hybrid_dynamics.json`; code/data/config changes invalidate saved results. The trained estimator lives during that run; the persisted artifact is the evaluation output, not a reusable estimator file.

Verification: `python -m pytest tests -q`, then frontend `npm test`, `npm run lint`, `npm run build`. Restrict collection to `tests` because `Class_report` contains a copied project with duplicate test names.
