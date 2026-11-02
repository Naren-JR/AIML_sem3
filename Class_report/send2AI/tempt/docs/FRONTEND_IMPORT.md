# Supplied frontend folder integration

The newly supplied frontend_unzipped directory contains a handoff document and static track-reference exports, rather than React application source. The running dashboard remains frontend/; do not run npm commands inside frontend_unzipped.

backend/track_reference.py reads the Australian Grand Prix export directly, preserving its files and source manifest. GET /api/track-reference exposes geometry, corners, normalized section percentages, source hashes and explicit alignment status. The overview includes a collapsible static reference view and section table. The supplied handoff supports the existing workstation design and recorded/calculated/estimated separation.

The selected Australian export has 618 geometry points and 14 corner/section references. Its metadata identifies a Practice 1 source fallback, a historical layout-year candidate, unknown coordinate units and no verified telemetry alignment. The aero-zone CSV has no data rows. These references therefore do not replace the synchronized recorded race trace or establish Straight Mode activation. Source manifest paths document lineage but do not prove those upstream raw files are locally present. Other circuits in the import are retained but not used for the Australian race; event exclusions remain in place.

Claude-related folders and historical scripts are outside the project workflow and are not required. Earlier PROJECT_REVIEW.md, INSPECTION.md, SOURCES.md, MODEL.md and API.md missing-artifact statements describe the pre-import snapshot; this note supersedes their statements that the handoff and processed static geometry are absent. circuitMap.json and original session raw geometry remain separate unresolved provenance inputs for rebuilding those exports, not requirements for starting the current dashboard.

The point API now accepts the logical lap domain starting at 0 m and snaps to the nearest recorded sample, matching the frontend slider. No telemetry sample is fabricated.

## Run

From the repository root, with dependencies installed:

    .\.venv\Scripts\python -m scripts.dev

Open http://127.0.0.1:5173 after READY. API documentation: http://127.0.0.1:8000/docs. Keep the terminal running. Ctrl+C stops both processes.

For a fresh installation: create a Python virtual environment, install requirements.txt, then run npm ci from frontend/. Return to the root and launch scripts.dev. The launcher checks dependencies, ports and proxied API readiness. It starts only local services and performs no downloads or deployment.

For a production-style frontend build, run npm run build in frontend/. This is a build command, not the local development startup command. Vercel and separate Python hosting instructions remain in README.

Research limitations remain: true electrical state and event regulatory compliance are unverified. Importing track references does not calibrate the energy model.
