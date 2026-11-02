# Processing report reconciliation

The supplied reports/process_tracks_report.json describes a 31 October 2026 run in a different checkout (<original-checkout>/trackData). It reports 103 warnings, zero processing errors, 20 catalogued events, 14 events with geometry, 70 unverified session labels, and zero verified Straight Mode zone exports. The candidate CSV contains 49 unverified image annotations. The review sheet was inspected visually; colored regions and boxes are not telemetry-aligned activation measurements.

## Changes applied

- Restored 36 SVG/WebP graphics from the existing local archives into the processor's expected raw/images/svg and raw/images/webp paths. Existing differing files are preserved by refusing overwrite. Archive traversal is rejected. Australian image_assets now returns assets_found instead of mapping_exists_but_assets_missing.
- Added backend/track_quality.py and GET /api/track-report to preserve every report warning with a unique ID, category, required evidence and disposition. GET /api/track-report/review-sheet serves only the fixed local review PNG.
- Added dashboard processing-evidence details showing Australian warnings, source-version conflict, and access to the supplied review sheet. The report remains explicitly a historical snapshot, not a fresh local rebuild.
- Attached report evidence to GET /api/track-reference. Imported Australian metadata selects a Practice 1 fallback; the historical report selects Race. Neither source selection is silently rewritten.
- Removed unverified corner distances from the normalized usable source_distance field. Original values remain available separately as reported_source_distance with explicit unverified status. Recorded race selection continues to use paired telemetry, not these anchors.
- Consecutive duplicate static geometry points are removed only from the display adapter; original source files and their original counts remain preserved. Mismatched raw arrays are not paired. Independently parsed percent-section references remain separate from source distances.
- All 49 image candidates are marked usable_in_model=false. No pixels, review boxes or Overtake markings become Straight Mode zones or activation distances.
- Strengthened fetchTracks.py to apply explicit excluded-event filtering even if the upstream mapping later changes.
- Added scripts/reconcile_tracks.py. It restores/verifies the local graphics and writes results/track_reconciliation.json without modifying the historical report or imported source files. It is safe to rerun when restored files match their archives.

## Warning accounting

| Category | Count | Treatment |
|---|---:|---|
| Conflicting reference distances | 56 | Source distances remain unverified; blocked from race alignment |
| Historical layout metadata | 14 | Require current-layout compatibility evidence |
| Missing source geometry/corners | 12 | Require original event session source files; no substituted layout |
| Array-length mismatch | 11 | Preserve raw; do not pair by index |
| Missing image mappings | 7 | Keep event mapping unavailable rather than guess |
| Consecutive geometry duplicates | 2 | Display adapter deduplicates only; source retained |
| Other source warning | 1 | Preserved with required source-level review |
| Total | 103 | Every original warning has a unique ledger entry |

These warnings are accounted for and guarded; they have not all been scientifically resolved. The original report is deliberately unchanged. Imported older static exports do not contain the newer source comparisons referenced by this report.

## Evidence still required

The report's six events without geometry are Abu Dhabi, Emilia Romagna, Mexico City, Qatar, Saudi Arabian and São Paulo GP. Original source files are still needed for those events. The application only analyzes the supplied Australian race; absent circuits are not substituted.

The local original circuitMap.json and raw session JSONs are still absent. Report paths and counts are not copies of those files, so a faithful local rebuild of that historical run remains blocked. Likewise, the report does not supply the 70 weather/race-control datasets or verify their session identities. They are not imported into race physics.

Historical layout years, inconsistent distance anchors and image annotations need independent source/reference evidence. The reports cannot establish true ERS state, regulatory limits or calibrated model parameters. The earlier model limitations therefore remain.

## Commands

    .\.venv\Scripts\python -m scripts.reconcile_tracks
    .\.venv\Scripts\python -m pytest -q

From frontend/:

    npm test
    npm run lint
    npm run build

The standard startup command remains `.\.venv\Scripts\python -m scripts.dev` from the repository root. Dashboard: http://127.0.0.1:5173. Expand Track processing evidence on Overview. Keep reports/ and frontend_unzipped/ available locally to inspect these references.
