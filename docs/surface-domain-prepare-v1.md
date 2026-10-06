# Surface-domain prepare v1

## Scope and states

This slice schedules hydrology for every declared coarse land node and explicitly prepares each domain's fine river bed and static water surface. It does not deliver a continuous full-region fine mosaic, certify natural drainage, accept real mountain terrain, or simulate full hydraulics.

- `candidate`: successful complete coarse routing, not fine completion; also successful fine domains with unverified external boundaries or subdomain scope.
- `diagnostic`: declaration, routing, resource, protection, actual fine gate, or cancellation failure. Completed domain prefixes remain evidence, never a publishable whole product.
- `prepared`: all declared coarse land routed, all domain fine river networks actually accepted under original physical budgets, shared resources respected, caller-declared complete-grid boundary. This means per-land-domain river fine + Q scheduling only.

`outlet_evidence` distinguishes `engineering_declared` from `independently_observed`. Both are caller declarations, not automatically authenticated observations. Hashes bind source and payload integrity, not publishers, natural river mouths, or independent geographic evidence.

## Interfaces

- `plan_surface_domains`: explicit H0, valid/land/ocean/protected masks, labels, coast triples, runoff/external Q, metric coordinates, sea level, vertical datum, source identity/kind, complete boundary declaration, scope, outlet evidence and shared resources.
- `bind_surface_domain_fine`: derives fine masks bound to the full coarse domain declaration; no physical generation.
- `evaluate_surface_domains`: requires `DomainFineConfiguration` for every land domain; explicitly chains existing `plan_channel` and `recover_surface_network`. Fine grid, fixed stages and channel/section/stage/inundation/bed/network/valley/reroute/recovery recipes are caller inputs, not relaxed defaults.
- `save_surface_domains` / `load_surface_domains`: self-contained NPZ, atomic no-overwrite creation and bounded headers/member/JSON checks. Default load rejects candidates and diagnostics; explicit `allow_unprepared=True` is diagnostic inspection only.
- `validate_surface_domains` / `query_surface_domain`: static saved graph, geometry and budget checks. No flood, channel planning, rerouting, recovery or semantic recovery replay occurs on load/query. Arrays and nested metadata are immutable.

## Complete coarse declaration

Arrays are Z by X; flat indices are row-major. Labels: -1 unknown/unassigned, 0 exactly declared ocean, positive exactly one land domain. Every land node must be valid and positive. Unknown, unassigned and invalid coverage remains diagnostic, not silently excluded. Valid H0 must be finite; declared ocean must be finite-valid and H0 <= explicit sea level.

Coast triples are `(domain_id, last_land_flat, neighboring_ocean_flat)`. Ocean must connect through declared ocean to the full grid boundary. All diagonal land, ocean and land-to-ocean edges require both orthogonal support cells legal; no domain/protection/unknown corner crossing. Land terminals use receiver -1; ocean and unrouted nodes use -2. `coastal_transfers` explicitly records both endpoints and transferred Q. Other land cells cannot become arbitrary sinks.

The bounded priority flood orders heap items by `(working_height, flat_index)` and assigns first-discovered parents. This is a deterministic supported flood tree, not steepest-descent D8, an optimal river network or a natural river-line claim. Separate working fill never replaces H0; existing channel/valley physical planning starts from original H0.

Local Q = runoff_m_s * coarse spacing_x_m * spacing_z_m + external_q_m3_s, using full coarse cell area. Reverse downstream-first order accumulates conservative per-domain Q. Fine volume integration retains existing endpoint half-weights. `unrouted_local_discharge_m3_s` preserves water from all unprocessed sources. Protection means impassable: currently any protected land, including zero-Q land, conservatively blocks complete coarse planning; nonzero protected runoff is never dropped to manufacture conservation.

## Fine binding and evidence

Each fine grid exactly covers its domain's coarse-node bounding rectangle at integer refinement. Fine masks use nearest coarse-label support, `floor(coarse_coordinate + .5)`; coarse samples match exactly. Domain/protection/coastal supports are bound over the entire grid, not only active channel nodes. Fine legal outlet support is the nearest-label area of each explicit last-land node.

Stored proofs bind original complete coarse graph/Q/H0, source identity/coordinates/sea level, caller physical recipes, actual bed/water/wet connectivity, and charged coarse/fine grid sizes. Original recovery caps remain binding; effective caps may only shrink under shared remaining resources. Rehashing does not bypass physical or resource validation. Static validation checks graph legality and minimal supported fill rather than rerunning deterministic routing history. Diagnostic proofs are evidence of failure, not accepted physical products.

## Resources and cancellation

`SurfaceDomainResources` bounds full-input coarse cells, summed domain bounding coarse work, summed fine grids, cumulative attempts/fine work and retained evidence bytes. Joint preflight checks all domains before any recovery; per-domain existing recovery caps also remain unchanged. Remaining work reserves one minimum attempt/fine evaluation for each later domain.

`max_retained_bytes` measures logical retained arrays and JSON evidence, NOT process peak RSS. `count*200`, coarse/fine estimate coefficients and freeze-copy margins are conservative preflight heuristics, not measured OS allocation guarantees. Existing per-recovery working-byte caps separately apply. Evidence too large is rejected, not returned as an oversized diagnostic bundle; verifier records bounded error summaries. Storage additionally enforces 256 MiB, 8192 members and bounded NPY/JSON headers. No file overwrite or partial accepted publication.

Cancellation is an explicit callback, checked each coarse heap pop and between complete fine-domain recovery calls. Current scheduler cannot interrupt one bounded old recovery invocation internally. Completed domain prefix is retained, overall status diagnostic and query forbidden.

## Fixed verification and limitations

Run `python -X utf8 tools/verify_surface_domain_prepare.py`; artifacts go to `verification/surface-domain-prepare/run-<UTC>/`. Both success and failure keep reports, with traceback on failure. Focused tests: `python -X utf8 -m unittest tests.test_surface_domain_prepare -v`. CPU only: no dependencies, GPU, game or Java changes, no raw data edits.

Synthetic positive: 9x16 full declaration, 98 land nodes in two adjacent land domains. Each routes all 49 coarse land nodes; two independent external Q sources actually merge to an explicit coast endpoint. Each fine grid is 61x61; actual beds and static water pass existing unchanged gates and survive self-contained save/reload/read-only consumption. Per-node runoff is 1e-6 m3/s, external sources .1 + .1 per domain, total coastal Q .400098 m3/s.

Fine bounding rectangles are world X=10..70 and X=80..140: a 10 m interval is not covered. Nearest-label support does not fill this bbox gap. Continuous full-land fine mosaic, shared-domain boundary/seam completion remain unaccepted. Last-land H0=4 m, river outlet stage=4.2 m, ocean H0=sea level=0 m. The triple proves discharge transfer across an open ocean boundary but DOES NOT construct a continuous 4.2-to-0 m wet/drop connector. No river-mouth geometry or coast dynamics claim; no source/sea-level alteration to hide this gap.

Negative evidence covers unknown/unassigned land, false/peak/disconnected ocean exits, no outlet, unsupported D8 corners, protection, coarse/fine/attempt/fine-work/retained caps, missing domain or fine mask binding, actual fine budget failure, cancellation prefix and rehashed graph/Q/fill/charged-grid/original-recovery-cap/fine-geometry rejection.

Original generated-model probe retains the complete 1025x1025 source declaration: all 402641 H0>0 land nodes assigned domain 1, versus only 7993 in the old catchment, leaving 394648 land nodes outside it. Default coarse cap 250000 diagnoses before flood. External closure and legal natural outlets are unverified. No crop, reduced precision or old 4441x2221 (~9.86 million node) fine rerun is used to fabricate success.

Raw source SHA256: `408aae491bf11868c11f1fea343703acb725f23cf97ee574cfd4d317261a934b`. Archived source and candidate-domain are read-only with before/after hashes. Archived metadata spacing is 30 m; native origin is copied as declared, not independently georeferenced. Relative-sea H0 approximately -17.0729..19.1478 m is generated lowland, not observed mountain terrain. True mountain unknowns/datum/natural outlets, cross-resolution, inland lakes/backwater, continuous coast/shared boundaries and Java/game acceptance remain open.
