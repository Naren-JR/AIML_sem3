# Report intake and drafting status

Status: the user explicitly authorized writing. A complete report draft has been generated in Class_report; see DELIVERY_NOTES.md for verification and limitations. The complete attached request has now been read and supersedes the initially truncated message.

## Agreed requirements

- Title: Mathematics-Guided ERS State Estimation and Energy Deployment Optimization for Formula 1.
- Deliver the academic report from Abstract through the final section and Appendices, following the supplied academic template once available.
- Keep every generated output and intermediate file inside Class_report.
- Use concise engineering research language and verified references. Do not invent implementation details, results, metrics, or findings.
- Driver: Kimi Antonelli. Intended scope: all available 2026 race/session telemetry up to an evidence-supported data cutoff, across circuits. Actual processed and evaluated coverage must be established separately.
- Data source specified by the user: TracingInsights/2026 GitHub telemetry.
- Battery current, voltage, temperature and ground-truth battery SoC are unavailable. Distinguish observed telemetry, derived quantities, imposed assumptions, conditional energy estimates, and hypothetical deployment policies.
- Literature table columns: S.No.; Author & Year; Paper Title; Objective / Problem Addressed; Methodology / Technique; Dataset / Sample; Key Findings; Limitations / Research Gap; Relevance to Our Work.

## Materials located and preliminary inspection

- Local Git origin: https://github.com/Naren-JR/AIML_sem3.git. The public web fetch failed; remote contents and local/remote equivalence have not been verified.
- F1_2026_ERS_Team_Handbook.pdf and Project_AIML_F1_v2.pdf are present at the repository root. Their existing extracted text in docs was read for preliminary scope. Direct PDF extraction and visual verification remain pending.
- Class_report/F1_ERS_2026_Literature_Survey.docx: inspected opening text and document structure. Source claims have not yet been independently verified.
- Class_report/F1_ERS_2026_Literature_Survey_12_Papers.xlsx: inspected worksheet names, header and sample entries. Existing columns differ from the requested report table. Bibliographic and substantive verification remains pending.
- Class_report/send2AI.zip: 544 archive entries, including backend, frontend, configuration, preprocessing, documentation, scripts, tests and track-data samples. Inventory only; no extraction or execution performed. No PDF, DOCX or filename containing template was found inside the archive.
- The local checkout also contains implementation, preprocessing, tests and results directories. Their presence alone does not establish successful experiments or complete season coverage.

## Reconciliation points for later review

- The handbook proposes a physics envelope and conditional ML/hybrid extension; the v2 proposal describes gradient-based estimation/optimization. Describe only the final implementation supported by source code and reproducible evidence.
- The v2 proposal imposes an initial state at the top of a modeled usable-energy window and requires cross-lap continuity. This is an assumption, not a measured battery initial condition. Independent sessions require separately justified initialization.
- The user's TracingInsights source and multi-circuit scope take precedence over older handbook examples mentioning FastF1 or an initial single-lap study.
- Regulatory numbers and reference claims in planning documents are not independently verified facts. Pin event-applicable sources before citing them in the report.

## Awaited materials or clarification

- Institutional academic report template, required chapter order, formatting and citation requirements; none identified in the inspected Class_report inventory/archive.
- Progressive materials identified by the user: final code, preprocessing, mathematical formulation, processed data, actual results/figures, frontend details and additional references.
- Exact data cutoff and a manifest identifying available, processed, excluded and evaluated sessions.
- Explicit START WRITING instruction after all materials have been shared.

## Additional requirements from the complete attached request

Extraction update: the user-provided extracted archive is present at Class_report/send2AI/tempt. Its directory inventory includes backend, frontend, config, dataPreprocess, docs, scripts, tests and trackData(samples). Use this supplied snapshot as report evidence, keeping it distinct from the evolving repository root. Report drafting remains on hold.

- Frame the task as model-based state estimation, not direct battery SoC measurement. Detailed proprietary power-unit reconstruction is outside scope.
- Initialize Lap 1 at timestamp 0.00 at 100% of the modeled usable-energy window; propagate continuously without lap resets. Label this initial condition as imposed.
- Mathematical modeling, physics-based estimation, machine learning and optimization are central; their completed roles must be supported by actual implementation evidence.
- Prefer relevant research from 2021 onward; retain older foundational papers only where necessary. Cover racing/hybrid energy management, recovery/deployment, SoC estimation, physics-informed modeling, ML energy estimation and gradient-based optimization.
- Incorporate the existing literature survey, preliminary comparison table and additional supplied papers. Prefer IEEE citations; verify bibliographic metadata, DOI/URL and exact applicable FIA issue, date and clauses.
- Follow the institutional template exactly. The user's illustrative section list is not a replacement template. Include an AI Tool Usage Report if required.
- The user will handle title pages, personal information and administrative pages.
- Use equations, figures, tables and diagrams where useful; define variables and assumptions. Keep the literature review comparative and analytical.
- After authorization, reconcile supplied evidence and outdated assumptions, identify material gaps, then produce one coherent report. Keep planned work distinct from completed work.
- The user requests technical context from the prior chat titled F1 ERS Data Preprocessing. Retrieval is pending; do not assume its contents from other chats.
