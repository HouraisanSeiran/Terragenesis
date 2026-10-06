# Surface domain mosaic v1: original H0 dry extension

`prepare_domain_mosaic(evaluation, resources=..., cancel=...)` accepts a complete prepared
`surface_domain_prepare` evaluation. It prepares one full-window, accepted-proof fine mosaic
per domain with the existing proof-only API, then fills uncovered cells in their common
rectangular node envelope from bilinear original candidate H0. Source kinds are
`accepted_domain_proof` and `original_candidate_h0_dry_bilinear`; the second is not an
accepted recovery, measured fine DEM, or hydrologic solver output. Version 1 requires equal,
integer-aligned fine spacing for all domains. All full source bounds, not a caller bbox,
define the envelope.

Every positive-weight original contributor of an extension node must be valid, known land
with a positive candidate domain label. Candidate protection is retained; it may not be
changed or made wet. Extension H2 equals H0, wet is false, water stage is zero, and cut is
zero. At shared nodes, each source's H0, H2, wet, stage, and protection agree within the
fixed 1e-8 m gate; a wet or cut domain boundary cannot join a dry extension. Each cell has
one geometry source owner and one hydrologic domain owner. The latter uses the cell center's
nearest original coarse node, with ties assigned to the larger row/column index. It does
not create a third hydrologic domain or cross-domain active graph edge. For the fixed gap,
the candidate labels assign 300 dry cells to each original domain.

The bundle keeps the original candidate/evaluation, both accepted recovery proofs, both
complete old fine mosaics, unique global nodes/cells/triangles, and per-corner contributor
indices and weights. It preserves each old proof's bed, water stage, Q cut, and budget.
Global Q sums each original domain proof once. The dry extension adds no new independent
discharge record; original coarse runoff/Q near the gap remains in the original domain
graphs. `unique_cell_area_m2` is total geometry area, not the old per-domain modified-area
budget. Cut and water volumes are integrals of the unique triangle mesh. They are not exact
bilinear-quad volumes or new hydraulic storage claims.

`declared_node_envelope_complete=True` means the saved rectangular node envelope is fully
covered. `physical_footprint_complete=False`, `natural_outlets_certified=False`, and
`full_domain_mosaic_prepared=False` remain explicit. Perimeter half-pixel footprints,
natural coast and outlet certification, real-world mountain data, and arbitrary wet gap
connections remain outside this result.

`save_domain_mosaic` atomically publishes a no-overwrite ZIP/NPY bundle. `load_domain_mosaic`
preflights ZIP/NPY headers, dtype, shape and resource limits, checks canonical identities,
then validates saved topology, full source bounds, contributor coordinates/weights, original
H0 and domain values, seams, ownership, and unique integrals algebraically. It does not
prepare a new mosaic, resample a source, or recover a proof. Loaded mappings and arrays are
read-only.

Run `D:/anaconda/python.exe -X utf8 -m unittest tests.test_surface_domain_mosaic -v`, then
`D:/anaconda/python.exe -X utf8 tools/verify_surface_domain_mosaic.py`. The verifier uses
the unchanged saved two-domain prepared source, retains the old 600-cell gap diagnostic,
and writes a fresh UTC run under `verification/surface-domain-mosaic/`. Failed runs retain
their report and traceback; old evidence is never overwritten.
