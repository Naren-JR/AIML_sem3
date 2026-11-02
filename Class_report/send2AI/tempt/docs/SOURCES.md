# Source and uncertainty ledger

Audit date: 2026-11-02. Supplied local documents are research drafts, not regulatory or empirical ground truth.

| Source | Use | Status |
|---|---|---|
| Project_AIML_F1_v2.pdf, 25 Oct 2026 | Continuous usable-window state, identifiability, optimization separation, telemetry units | Read all extracted text; authoritative project intent |
| F1_2026_ERS_Team_Handbook.pdf, 14 Oct 2026 | Force/energy equations, uncertainty and validation requirements | Read all extracted text; earlier scope superseded by v2/user brief |
| dataPreprocess/fetchKimi.py | CSV lineage and cumulative-time export semantics | Does not retain original lap IDs or source commit |
| dataPreprocess/preprocess.py | Existing diagnostic QC and derived acceleration | Preserved; does not supply lap IDs or a complete ERS model |
| trackData/processTracks.py | Track provenance policy, exclusions | Requires missing circuitMap.json and session geometry |
| trackData/raw/sections/*.json and sections.zip | Event section categories and percentages | Static reference, never proof of Straight Mode activation; not linked to race distance |
| trackData/raw/images/{svg,webp}.zip and eventMap.json | Existing graphics | Inventoried; no image-to-telemetry alignment asserted |
| FIA regulation index | Lists Section C issues 16 and 21 | Verified official index; latest does not imply race-applicable |
| FIA Section C issue 16, 27 Feb 2026 | C5.2.7 power, C5.2.9 swing, context-dependent C5.2.8/C5.2.10/C5.2.12 | Clauses inspected directly; event applicability/interface unresolved |

Official links:

- https://www.fia.com/regulation/category/2182
- https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_16_-_2026-02-27.pdf

The official issue 16 distinguishes an electrical DC limit and a usable-state swing; speed/mode propulsion limits and per-lap harvesting adjustments also apply. The code's motor-side scenario power caps are NOT a compliance implementation. Event date, race appendix, mode flags, and a validated bus conversion are missing. Optional lap budgets remain unspecified. Do not cite the experiment as regulatory compliance.

The supplied v2 bibliography cites arXiv:2603.01290 and a 2021 hybrid energy-management review. No standalone research-paper files or empirical labels were supplied, and their performance results are not used to calibrate or validate this implementation. There is no supervised training dataset.

Missing requested artifacts: frontend.zip, frontend handoff, dashboard screenshots, circuitMap.json, session corners/cor geometry, master_track.json, track_geometry.csv, corners.csv, sections.csv, active_aero_zones.csv, source_manifest.json. Their absence does not block the race adapter, recorded-position map, conditional physics scenarios, API or optimizer. It blocks an independent circuit/landmark alignment and confirmed mode/regulatory reconstruction.

Exclusions preserved from processTracks.py: Bahrain, Chinese, Japanese and Spanish Grand Prix. The runtime loads only the supplied Australian race. Archived graphics and section files are not substituted for absent events or geometry.
