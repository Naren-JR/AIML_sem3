# AIML–F1 Energy Research Workstation

On circuit_add, the TRACK selector offers 20 locally referenced circuits with official Kimi race-participation sources. Only Albert Park has local driver race telemetry; other selections open clearly labelled static references and section tables without reusing Australian model readings. See [circuit catalogue and availability](docs/CIRCUIT_SELECTION.md).

On the readings branch, **ML validation & predictions** adds a trained operating-state classifier with held-out accuracy, precision/recall/F1, a confusion matrix, baseline comparison and per-lap predictions. Install updated requirements, restart the API, then open `/ml-validation`. Click Train & evaluate or run `.\.venv\Scripts\python -m scripts.validate_ml`. See [evaluation protocol and external sources](docs/ML_VALIDATION.md). These scores do not validate hidden ERS state.

GitHub privacy: supplied datasets, imported references, internal PDFs, reports and results are intentionally ignored and remain local. A fresh clone needs the race CSV restored before running. Run `.\.venv\Scripts\python -m scripts.check_publication` before committing, and read [GitHub privacy/setup notes](docs/GITHUB_PRIVACY.md).

Working local pipeline for Kimi Antonelli's supplied 2026 Australian GP Race telemetry: continuous conditional ERS estimation, constrained gradient-based deployment experiments, FastAPI and a React engineering dashboard.

**Research scenario, not measured battery SoC.** Initial state is imposed at 100% of a configurable usable window at Lap 1, t=0. Energy never resets between laps. The original ERS/optimizer remains physics-based; the separate hybrid experiment adds trained dynamics. No lap-time improvement is claimed. Regulatory event compliance and physical battery capacity remain unverified. Read [model equations and limitations](docs/MODEL.md).

## Hybrid ML experiment on readings

The **Hybrid ERS research** tab (`/hybrid`) trains an acceleration regressor using TracingInsights Australia, Austria, Italy and Britain telemetry and tests on an entirely held-out Belgium dataset (278 recorded laps across five circuits). Predicted dynamics feed a conditional physics energy calculation. These are real learned motion predictions, not measured battery SoC predictions. The test-track selector lets you rotate which of the five tracks is held out. Restore datasets with `.\.venv\Scripts\python -m scripts.fetch_hybrid_data`; train with `.\.venv\Scripts\python -m scripts.train_hybrid`. See [exact training target, split, assumptions and commands](docs/HYBRID_TRAINING.md).

## Run locally (Windows PowerShell)

With the installed dependencies in this workspace, start both services from the root:

```powershell
.\.venv\Scripts\python -m scripts.dev
```

Wait for READY, then open http://127.0.0.1:5173. Keep the terminal open; Ctrl+C stops both services. This launcher requires free ports 8000 and 5173. The separate-terminal commands below are an alternative.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The Python API must be running. Vite proxies /api to port 8000. Interactive API docs: http://127.0.0.1:8000/docs. On POSIX, substitute `.venv/bin/python` for the Python path. See [.env.example](.env.example) for deployment variables; set backend variables in the shell/service, and frontend Vite variables in frontend/.env.local or its build environment. Backend does not implicitly load .env files.

## Use the workstation

- Select an inferred lap. Move the distance slider, click a verified recorded map trace, or hover/click any telemetry chart. The same recorded sample drives every cursor, marker and readout.
- Overview combines map, vehicle channels, conditional SoC, power and race energy ledger. Telemetry Explorer exposes original source fields. ERS State Estimation shows scenario spread and accounting.
- Deployment Optimization runs only when requested. Select lap, iterations and smoothness, then Run optimization. Inspect convergence, constraints, baseline comparison, saved runs and JSON export.
- Methodology & Validation exposes parameters, provenance, missing context, equations and constraint-only validation.

58 laps are inferred from relative-distance wraps because original lap IDs were discarded upstream. Only the race enters the runtime. Source fields are preserved; numeric gaps remain null. The map is the recorded lap trajectory in unverified source coordinate units, not an invented circuit layout.

## Tests, production build, and experiments

```powershell
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python -m scripts.audit
.\.venv\Scripts\python -m scripts.reproduce --lap 2
cd frontend
npm test
npm run lint
npm run build
```

`scripts.reproduce` writes results/model.csv, results/model_summary.json, results/optimization/<run_id>.json, results/optimized_strategy.csv and results/reproduction.json. Inputs, parameters, source-code fingerprints, algorithm and dependency versions are recorded. Identical inputs/config/code produce the same run ID. Edit config/model.json and restart the API to change physical assumptions. Do not overwrite raw CSVs. The pre-existing preprocessing scripts remain unchanged; the new race adapter normalizes automatically at startup without network access or an external preprocessing step. Full model results are cached in memory once per process. See the [verification record](docs/VALIDATION.md) for passed checks and browser observations. requirements-lock.txt captures installed transitive Python dependencies for stricter reproduction.

## Project layout

| Path | Purpose |
|---|---|
| backend/ | Dataset adapter, continuous model, optimizer, API |
| frontend/ | React, Vite, TypeScript, Router, Plotly, SVG, Zod, Vitest |
| config/model.json | Configurable physical/scenario assumptions |
| tests/ | Real-data and synthetic-edge backend tests |
| scripts/ | Source inventory and reproducible runs |
| results/ | Real-data model/optimizer exports and audit |
| dataPreprocess/, trackData/ | Original supplied scripts/data, preserved |
| docs/ | [API](docs/API.md), [model](docs/MODEL.md), [source ledger](docs/SOURCES.md), [initial inspection](docs/INSPECTION.md) |

## Deployment

Frontend on Vercel: set root directory to frontend, framework Vite, build command `npm run build`, output directory dist; set VITE_API_BASE_URL to the HTTPS Python origin before building. vercel.json provides SPA route fallback. Set the Python service AIML_CORS_ORIGINS to the exact frontend origin. Never bundle raw race data into frontend components.

Backend: deploy Python 3.11+ with `pip install -r requirements.txt` and `uvicorn backend.api:app --host 0.0.0.0 --port 8000`. Include backend/, config/, docs/MODEL.md and dataPreprocess/rawData/australiar.csv. Use a persistent volume for AIML_RESULTS_DIR. One worker is supported for job status; scale with a durable queue/job store before multiple workers. Terminate TLS at the platform proxy. Add authentication and request limits before opening experiment submission to untrusted clients. Vercel serves the frontend; this Python model belongs on a separate long-running service. No deployment has been performed by this implementation.

## Known limits

The supplied data omit electrical ground truth, physical battery capacity, original lap IDs, event-specific regulatory context and verified mode flags. The model uses explicit, illustrative mass/aero/efficiency/split assumptions. Gaps hold state conditionally. Scenario spread is not a complete feasible envelope or confidence interval. The optimizer reallocates on the baseline's nonzero support and optimizes a disclosed proxy over one lap, with fixed recorded speed and recovery. It does not validate performance or recover a unique true ERS state.

Update: frontend_unzipped now supplies the handoff and static processed track references. The dashboard exposes the Australian reference in a collapsible panel, backed by GET /api/track-reference. Its 618-point geometry, corner references, sections and manifest are read from the supplied folder. That source uses a Practice 1 fallback with unverified layout/year, units and telemetry alignment; it is not used to place the selected race marker or determine aero activation. Keep frontend_unzipped in the repository root. No Claude-related files are needed. See [integration notes](docs/FRONTEND_IMPORT.md).

The supplied reports/ evidence is also integrated. Run `python -m scripts.reconcile_tracks` using the virtual environment to restore archived graphics and generate the complete warning ledger. Overview exposes processing warnings and the review sheet. Conflicting source distances and image candidates remain excluded from race alignment/model inputs. See [report reconciliation and remaining evidence gaps](docs/REPORT_RECONCILIATION.md).
