# Surface fine mosaic v1.1: bounded accepted-recovery cells

## Acceptance scope

This is an **engineering rectangular cell slice**, not a complete hydrology-domain mosaic,
observed fine DEM, natural outlet certification, coast drop, or new hydraulic solver.
Every artifact keeps `full_domain_mosaic_prepared=False` and `natural_outlets_certified=False`.
`prepared` means all cells of the explicitly declared bbox have valid supplied support.
Original terrain, old modules and TODO remain untouched.

The previous plain-array `DomainFineSource` API is deliberately removed: caller-declared
`prepared`, H0/H2 arrays or source names are not acceptance evidence.
`DomainFineSource(proof, domain_id, window_zx=None, unknown_mask=None,
protected_mask=None, role="domain")` binds an accepted recovery. Windows use
exclusive node-index stops `(top, bottom, left, right)`; their footprint ends at stop minus one.
Restrictions can add unknown/protection, never erase source protection.
Alternatively pass a statically validated prepared `surface_domain_prepare` evaluation;
its recovery proofs are validated by existing `_payload` and `_proof_gate`, without replay.

`prepare_fine_mosaic` requires explicit metric-xz-m grid, caller-declared vertical datum,
source identity and the existing source sea datum. The datum declaration is not independently
certified. An optional `bbox_xz_m=[xmin,xmax,zmin,zmax]` can limit the slice.
`source_extensions` accepts only explicitly supplied accepted-recovery sources with role
`extension`; it is not an interpolation callback. Without such source a bbox gap is rejected.

## Geometry and source semantics

The target grid uses the minimum source spacing on each axis. All ratios and origin offsets
must be integer aligned: no coarsening or arbitrary rational-grid inference. Source interior
cell footprints cannot overlap. Shared boundary coordinates have one node id.
Each target cell records an owner, original source cell index and four corner stencils;
each stencil saves four source node contributors and bilinear weights. Fine H0 retains
separate saved coarse support back to original H0, while H2 comes from the accepted surface
or cumulative ledger. This is geometric refinement, not acquisition of a finer DEM.

Unknown or outside-domain positive-weight support rejects; protected support cannot be wet
or changed. Zero-weight dry/NaN water does not participate. A target node is wet only when
all positive-weight source nodes are actually wet; actual water is interpolated and must
exceed interpolated H2. Sloping stage is allowed. At shared world positions H0, H2,
actual wet/water and protection must agree between sources. Mismatches reject, never blend.
Cells and two nondegenerate triangles per cell form a continuous unique rectangular mesh.
Wet cell publication requires all its corners wet. Cut and water volumes integrate the
unique saved triangles once; these are the triangle mesh's own geometric integrals, not
hydraulic storage simulation or a claim of exact conservation against the original bilinear
source quad volume. For the accepted wet slice the triangle water integral is
220.90766090829788m3, whereas bilinear-quad integration gives 220.8692567466273m3.
Cross-resolution refinement is neither Manning hydraulics nor river topology crossing.

## Q accounting

Graph local Q, accumulated Q and outlets remain bound to recovery proof. Do not sum all
accumulated node Q. Selected graph nodes define a local cut with incoming/outgoing edges:
`outgoing - incoming = local`. The full single-proof bbox reduces to terminal Q.
Exact graph-content identities (coordinates, receiver/order, local/accumulated Q,
active/outlet masks and actual node stages) merge across precision proofs before selecting
the union. Shared graph nodes, including inactive nonzero local Q, count once. Different
graphs at any nonzero Q position reject; no silent half-weighting or cross-domain flow repair.
The engineering bbox Q is a graph cut, not raster runoff interpolation.

## Static persistence

Self-contained ZIP/NPZ stores proofs, masks, coarse H0 support, contributors, nodes,
cells, triangles and Q cuts. Arrays and mappings load immutable. Default load rejects
diagnostic/unprepared artifacts. Gap diagnostics can be retained/reloaded only with explicit
`allow_unprepared=True`; they contain no fabricated mesh.

Load validates saved contributor weights against world/grid, source H0/H1/H2, actual wet
water and seed support, graph topology/masks, original outlet/static stage equations,
bed match and edge constraints, actual bed depth/area/volume and cumulative valley budgets,
saved connectivity, unique integrals and Q cuts. Hashes alone are not semantic acceptance.
It never calls prepare/recovery, `_assemble`, `_mesh`, `_h0_support`, grid ownership generation,
the original resampler or `_proof_gate` (which resamples). Saved source support is checked
algebraically, without reconstructing a full target mapping/geometry result.

Resource preflight bounds retained proofs before source validation and target allocations.
Archive load retains the same open file handle, caps file and total uncompressed sizes,
checks raw NPY header length before parsing, rejects object/Fortran arrays and wrong payload
sizes, duplicate ZIP/JSON keys, duplicate references and unused arrays. JSON resource gates
run before `np.load`. Save owns/closes the temporary fd, fsyncs, and publishes by atomic
no-overwrite hard link; failure removes its temporary file and never replaces an existing file.

## Fixed validation evidence

Run `python -m unittest tests.test_surface_fine_mosaic -v`.
Run `python tools/verify_surface_fine_mosaic.py`; fixed cases/entrypoint write to a unique
actual UTC directory `verification/surface-fine-mosaic/run-YYYYMMDDTHHMMSS.ffffffZ/`.
The report records actual start/finish timestamps, source proof evidence files and their
SHA256, mosaic/diagnostic bundle file SHA256 and all four implementation file SHA256.
Failure also retains a failed report and traceback. Existing evidence is never overwritten.

- Original prepared two-domain result has a real 10m x 60m bbox gap: **600 cells missing**.
  It stays diagnostic, not full-mosaic prepared; no invented ocean or terrain extension.
- Dry 1m/2m seam slice: 720 cells, 793 unique nodes; this alone is not wet-seam acceptance.
- Wet 1m/2m adjacent slices from two actually evaluated accepted engineering recoveries:
  800 cells, 1600 triangles, 861 unique nodes, 706 wet nodes, 645 wet cells and 41 shared
  wet nodes at x=30m; cut 93.59091063900095m3. Their exact shared graph is
  accounted once: local .1, incoming .2, outgoing .3 m3/s; nonzero source cut and water volume.
- A larger upstream wet seam from those same real proofs is incompatible and rejected.
  Cross-precision acceptance is not generalized to nonmatching source beds/stages.
- Full 1m single proof: 3600m2, cut 169.50873596272896m3, terminal/local Q .62m3/s.

Focused tests include source-proof rejection, real old gap retention, wet/dry seams,
unknown/protection, explicit sourced gap fill, Q uniqueness including inactive shared sources,
resources/cancellation, no-generation mocked load, coherent rehash budget/stage/contributor
tampering, readonly data, atomic/nooverwrite/fd cleanup and archive preflight.
