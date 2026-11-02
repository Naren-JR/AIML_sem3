# FastAPI contract

ML experiment endpoints: GET /api/ml/validation returns saved results or not_run/stale; POST /api/ml/validation/run trains a fixed operating-state classifier on earlier laps and evaluates later held-out laps, returning metrics and predictions. It runs synchronously in FastAPI's worker thread and persists JSON; it does not trigger on lap selection. See ML_VALIDATION.md for label definitions, leakage safeguards and limitations.

Additional source-evidence endpoints: GET /api/track-reference returns the imported static Australian geometry and attached quality metadata; GET /api/track-report returns all historical processing warnings and unverified image candidates; GET /api/track-report/review-sheet serves the supplied PNG. These endpoints do not certify telemetry alignment or mode activation. See REPORT_RECONCILIATION.md for evidence boundaries.

Start with `.venv\Scripts\python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000` from the repository root. Interactive OpenAPI: http://127.0.0.1:8000/docs. JSON spec: /openapi.json.

| Method | Path | Response / request |
|---|---|---|
| GET | /api/health | ok/degraded and load error |
| GET | /api/dataset | provenance, hash, units, availability, quality, exclusions |
| GET | /api/laps | inferred lap summaries with distance and time extent |
| GET | /api/telemetry/lap/{lap_number} | normalized samples, raw source_fields, calculated, quality_flags |
| GET | /api/telemetry/point?lap=2&distance=1000 | nearest telemetry + exact estimated state |
| GET | /api/ers/lap/{lap_number} | all state rows for lap |
| GET | /api/ers/point?lap=2&distance=1000 | same point contract as telemetry/point |
| GET | /api/model/status | parameters, validation metrics, limitations |
| GET | /api/track/{lap_number} | recorded x/y trace, sample pairing, mapping checks |
| GET | /api/methodology | mathematical specification Markdown and parameters |
| POST | /api/optimization/run | 202; JSON {lap:2,max_iterations:150,tolerance:1e-8,regularization:0.02,bins:40} |
| GET | /api/optimization/status | idle/running/completed/failed, run_id or error |
| GET | /api/optimization/results | saved run summaries, newest first |
| GET | /api/optimization/results/{run_id} | full metadata, history, strategy and feasibility |

Point lookup rejects negative/out-of-range distance, nonfinite input, and invalid laps. Unknown laps/runs return 404; invalid request bodies return 422; concurrent optimizer requests return 409; dataset/model load failure returns 503 for dependent endpoints. A degraded health response allows inspection of startup errors. Raw numeric missing data return JSON null. No NaN/Infinity serialization is used.

One in-memory Dataset and Model are created per process at startup and reused by every point/lap request. Results persist atomically to AIML_RESULTS_DIR (default results/optimization). Optimization is dispatched to a background thread, never triggered by data selection. A single lock protects job status. This local research service assumes one worker/process; multi-worker jobs require a shared task queue and durable job registry. API endpoints run in a thread pool so model-ready telemetry requests remain usable during optimization. Do not expose unprotected experiment endpoints on a public deployment without authentication/rate limits.

CORS defaults to localhost:5173 and 127.0.0.1:5173; configure AIML_CORS_ORIGINS as a comma-separated allowlist. Vite proxies /api to 127.0.0.1:8000. For separated deployment set VITE_API_BASE_URL to the HTTPS Python service origin, with no trailing slash. Zod validates frontend response contracts before rendering. Numeric units and the recorded/calculated/estimated split are explicit.
