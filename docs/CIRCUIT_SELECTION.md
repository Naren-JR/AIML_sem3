# Circuit selection (circuit_add)

The TRACK selector lists the intersection of explicitly identified local reference data and Kimi Antonelli's documented F1 race participation. GET /api/circuits inventories available canonical references and raw trackData section files. GET /api/circuits/{id} returns that circuit's static reference and section percentages. Unknown/excluded IDs return 404. Explicit IDs prevent path traversal and duplicate aliases. The catalogue currently has 20 circuits, 14 with coordinate geometry; six have sections but no supplied coordinate geometry.

After merging `circuit_add` into `readings`, Australia, Austria, Italy, Britain and Belgium have imported 2026 ANT race telemetry with source manifests. Selecting these tracks changes the race dataset, lap controls, model estimates and optimization context. All other catalogue tracks open reference-only views and clear race readings. Switching back to a recorded race loads its own samples. The classification tab supports temporal and cross-track experiments; Hybrid ERS research has an independent held-out-track selector. Copying an arbitrary CSV into a folder does not activate it: imports require an explicit registry entry, driver/year/session provenance and checksum validation. See [multi-track APIs](MULTI_TRACK.md) and [hybrid training](HYBRID_TRAINING.md).

Local sources: trackData/raw/sections and canonical event folders within frontend_unzipped. Circuit aliases such as monza/italian-grand-prix are deduplicated through explicit identities. The report safeguards, historical-layout caveats, unverified corner distances and zero inferred aero activation remain in force. Bahrain, China, Japan and the Spanish Grand Prix remain excluded; the separately named Barcelona-Catalunya event is retained, consistent with the existing processor's policy.

## Participation evidence

Reviewed 2026-11-02:

- https://www.formula1.com/en/results/2026/drivers/ANDANT01/kimi-antonelli
- https://www.formula1.com/en/results/2025/drivers/ANDANT01/andrea-kimi-antonelli

The completed 2026 result entries support Australia, Miami, Canada, Monaco, Barcelona-Catalunya, Austria, Great Britain, Belgium, Hungary, Netherlands, Italy, Azerbaijan, Singapore, United States and Mexico after exclusions. Prior 2025 results support participation at the other local tracks: Abu Dhabi, Imola, Lusail, Jeddah and Interlagos. Historical participation does not establish a 2026 appearance or compatible layout. A DNF still counts as participation. The 2025 Spanish result supports prior participation at the Barcelona circuit, not a distinct 2025 event called Barcelona Grand Prix. No 2025 telemetry is passed through the 2026 model.

This is a dated F1 race-result evidence snapshot, not a complete list of every test, practice or junior-series circuit Kimi has driven. The catalogue intentionally omits raced circuits without local references. Source links and participation years appear in each reference view.

The working tree already contained uncommitted readings-branch ML work when circuit_add was selected; that work was preserved. During implementation the checkout changed to readings and part of the work was committed there. The existing readings commit was fast-forwarded onto circuit_add, with remaining edits preserved through a temporary stash and restored without conflicts. No new commit or push was performed by the assistant.
