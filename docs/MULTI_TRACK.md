# Three-track recorded-race workflow

Branch: circuit_add. Ready races: 2026 Australian GP (58 laps, 37,569 samples), Austrian GP (71 laps, 39,416 samples), Italian GP (53 laps, 36,453 samples). All are Kimi Antonelli / ANT / GP Race. This is recorded analysis, not a live timing feed.

## Install and run

From the root (dependencies already installed in this workspace):

    .\.venv\Scripts\python -m scripts.dev

Open http://127.0.0.1:5173. Choose one of the three races in RECORDED GP RACE. Lap options, map, readouts, plots, state estimates and optimization context use that race. The source JSON mode channels are retained only in raw archives, never used to infer active aero. Static Australian reference panels appear only on Australia; other races use their own recorded x/y trace for position selection.

In ML validation & predictions, choose:

1. Earlier laps → later laps: select a training track. The first floor(70% of original lap IDs) train the classifier, one full lap is purged, and remaining laps are tested. No random sample splitting or test-set tuning occurs.
2. Cross-track generalization: choose different source and target tracks. All eligible source-track samples train the classifier; all eligible target-track samples are test-only. No target-track fitting, calibration or normalization occurs. Baseline predictions always use the most frequent source-training label.

All nine combinations were computed and are stored locally. Selecting a mode/pair loads its matching result immediately; Train & evaluate computes it again. Results include accuracy, balanced accuracy, macro precision/recall/F1, weighted F1, per-class counts, confusion matrices, source/target dataset fingerprints and every held-out prediction. The chart/table lap selector refers to the test dataset, independent of the main dashboard's lap control. Scores evaluate operational labels from throttle/brake, not electrical ERS truth. Those two label channels are excluded from classifier features. No real-world generalization claim follows from only three circuits and one driver.

## Reproduce from a fresh clone

    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
    .\.venv\Scripts\python -m scripts.import_races
    .\.venv\Scripts\python -m scripts.prepare_experiments

Run npm ci inside frontend/, then start scripts.dev from the root. Downloads require network access; analysis works offline afterward. Raw data, manifests and results stay ignored by Git. Do not force-add them for deployment; provision these files privately or run the importer on the backend host.

## Provenance and timing

Upstream: https://github.com/TracingInsights/2026, pinned commit e8cf4fe5121447409fa0cb3728255f261cfc8d62. Files are selected from <event>/Race/ANT/<lap>_tel.json, ANT/laptimes.json and Race/session_info.json. The original source JSON bytes are retained under dataPreprocess/rawData/2026/<circuit-id>/source/. Manifests record every source URL and SHA-256 plus the normalized CSV checksum. The source repository advertises Apache-2.0; retain upstream attribution and review upstream notices before redistributing downloaded files.

The importer fails on missing lap files, missing original lap starts, mismatched channel lengths, non-contiguous lap IDs or reversed timestamps. It downloads by original laptimes lap IDs, never silently skipping a failed lap. It preserves all original JSON channels and exports selected numeric channels plus lap_number, lap_time and session_time. CSV time is original lST + lap-local telemetry time minus the first lap's lST. It does not sum retained lap durations. This preserves Italy's long red-flag interruption. The ERS model holds its conditional representative state during unsupported gaps and records unknown duration; it does not invent electrical flows through the interruption.

The previous top-level Australian CSV remains untouched for historical reproduction/tests. Runtime prefers the newly pinned Australian import when installed. Registry caches at most five datasets; API caches each race's model once. No dataset is relabelled as another event, and every race initializes its own state at original lap 1/time 0. Reimporting/changing input files requires restarting the API to clear caches.

## API

- GET /api/ml/tracks: available imported race identities.
- GET /api/circuits: broader static reference catalogue, with three race-analysis entries.
- GET /api/dataset?circuit_id=italian-grand-prix
- GET /api/laps?circuit_id=italian-grand-prix
- GET /api/telemetry/lap/2?circuit_id=italian-grand-prix
- GET /api/telemetry/point?lap=2&distance=1000&circuit_id=italian-grand-prix
- GET /api/ers/lap/2?circuit_id=italian-grand-prix (and /api/ers/point).
- GET /api/track/2?circuit_id=italian-grand-prix
- GET /api/model/status?circuit_id=italian-grand-prix
- POST /api/optimization/run: existing body plus circuit_id; results list can be filtered by circuit_id. Starting energy comes from that race's continuous model, never a different race.
- GET /api/ml/experiments?mode=cross_track&train_track=australian-grand-prix&test_track=italian-grand-prix
- POST /api/ml/experiments/run with JSON {"mode":"cross_track","train_track":"australian-grand-prix","test_track":"italian-grand-prix"}.
- Within-track mode uses identical train_track/test_track. Cross-track mode rejects identical IDs. Unknown mode, unavailable tracks and invalid pairings return 422. Concurrent ML experiment submissions return 409.

Experiment IDs incorporate mode/pair, both dataset hashes and data/ML source fingerprints; results are separate per experiment and written atomically. There is no automatic retraining on selector interaction. Training runs in a FastAPI worker thread with a bounded numerical thread pool. Existing single-process deployment/job-status limits remain. Previous single-track endpoints remain for compatibility; the new UI uses the pair-specific experiment API.

## Observed results

| Training | Test | Mode | Accuracy | Macro-F1 |
|---|---|---|---:|---:|
| Australia | Australia | Temporal | 87.98% | 74.59% |
| Austria | Austria | Temporal | 90.72% | 79.73% |
| Italy | Italy | Temporal | 90.65% | 70.91% |
| Australia | Austria | Cross-track | 85.91% | 66.71% |
| Australia | Italy | Cross-track | 82.76% | 62.07% |
| Austria | Australia | Cross-track | 81.92% | 65.79% |
| Austria | Italy | Cross-track | 83.17% | 63.99% |
| Italy | Australia | Cross-track | 80.04% | 62.92% |
| Italy | Austria | Cross-track | 85.22% | 67.88% |

These are measured outputs of this fixed protocol, not promised scores. Coasting is difficult and class imbalance makes accuracy alone insufficient. Full per-class results are available in the UI/JSON. No independent battery-state accuracy, performance improvement or regulatory compliance has been established.
