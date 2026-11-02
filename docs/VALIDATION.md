# Verification record

Date: 2026-11-02. Local Windows / Python 3.11.9 / Node 24.14.0. Reproduction dependencies are pinned in requirements.txt, with installed transitive versions in requirements-lock.txt and frontend/package-lock.json.

Succeeded:

- `.venv\Scripts\python -m pytest -q`: 15 backend tests pass. Includes actual race accounting and boundaries, synthetic edge cases, gradient checks, reproducibility and API response/error assertions. Starlette emits one third-party AnyIO deprecation warning.
- `npm test` in frontend: 5 tests pass, including shared selection, null preservation, API errors, map-disabled behavior and unavailable geometry.
- `npm run lint` in frontend: passes.
- `npm run build` in frontend: TypeScript and Vite production bundle pass.
- `.venv\Scripts\python -m scripts.audit`: inventories all 5 CSVs, 22 JSONs, 3 archives, 4 original Python scripts and 2 supplied PDFs.
- `.venv\Scripts\python -m scripts.reproduce --lap 2`: writes the complete 37,569-sample state trace, summary, optimized strategy, run JSON and reproduction manifest from actual supplied data.
- Local FastAPI and Vite startup. Frontend /api/health proxy returns {status:ok,error:null}.

Manual browser checks against actual Python backend:

- Overview renders recorded vehicle channels, lap position trace, scenario SoC, energy ledger and Plotly charts.
- Switching from inferred lap 1 to lap 2 loads matching data. Lap 2 starts at approximately 4.2% conditional usable-window SoC, demonstrating that UI does not reset to 100%.
- Slider Home/End selects the recorded extent, updates sample identity and readouts; selected nearest distance can differ slightly from requested distance.
- Clicking the recorded map selects a paired telemetry sample and updates the slider/readouts. Plotly hover changes the shared selected position and every chart cursor.
- Separate throttle and binary brake charts retain readable units. Missing initial derived acceleration renders a dash.
- Deployment Optimization POST via the button completed on lap 2 in 56 iterations, returned a feasible strategy and populated objective/constraint histories, deployment/energy comparison charts, saved result selector and export link.
- Methodology page displays the real dataset hash, parameters, missing context and conservation diagnostics.
- Full-page screenshot saved as results/dashboard.png.

Research checks:

58 inferred laps; 57 equal-time lap boundaries; no later-lap state reset. Maximum baseline conservation residual approximately 2.214e-12 MJ. Final baseline SoC is 0%, a consequence of illustrative split assumptions, not measured battery exhaustion. Missing/unsupported interval duration is 3.436 s. The lap-2 objective proxy changes from approximately 1.18715 to 1.21245 at the same 2.09103 MJ delivered energy budget. No lap-time gain is inferred.

These are software/constraint checks. They do not establish true ERS reconstruction accuracy, event regulatory compliance, calibrated uncertainty, or predictive performance. Original source lap IDs, physical battery capacity, electrical labels, event-specific context and independent processed track geometry remain unavailable. No deployed environment was tested.

Windows asyncio local sockets were blocked in the execution sandbox; API tests and browser-accessible servers were run with approved local access. This was an environment constraint rather than a model or API defect. Local preview servers were stopped after verification; use README startup commands to reopen the dashboard.
