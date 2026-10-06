# Surface coast drop v1

## Scope and API

An explicit, constant-width, straight, increasing-z engineered strip connecting an
actually saved prepared river cross-section to a separately declared synthetic sea patch.
`surface-coast-drop-v1` is geometry only: not free-fall dynamics, rapids, momentum,
tides, Saint-Venant, a real DEM coastline, or natural-outlet certification.
Mode: `engineering-synthetic-straight-strip-not-free-fall`.
No default generation, implicit extrapolation, recovery, routing, or modification of old data.

- `RiverAttachment(prepared, domain_id, cross_section_xz_m, center_index, datum)` snapshots a saved prepared product and explicit full-width attachment.
- `EngineeringSource(...)` explicitly supplies corridor/sea H0, H2, water, metric grid, valid/unknown/protected/wet/ocean masks, datum and source identity.
- `DropBudget(max_cut_depth_m, max_cut_volume_m3)` is the original explicit budget; never relaxed on failure.
- `DropResources(...)` can tighten, not enlarge, hard resource ceilings.
- `prepare_coast_drop(attachment, corridor, sea, stations_z_m, budget, resources=...)` is the only construction entry.
- `validate_coast_drop`, `save_coast_drop`, `load_coast_drop`, `query_coast_drop` are static-only.
- Rejections raise `CoastDropError`, a `ValueError`, with a non-published diagnostic.

Inputs and results are immutable bytes-backed arrays/mappings. Caller inputs remain unchanged.
The source kind must be `engineering_synthetic`; arbitrary source strings never certify a
natural outlet. No legacy DEM is silently extended beyond its coverage.

## Actual river endpoint and source binding

The fixed source is the existing `two-domain-prepared.npz` in
`verification/surface-domain-prepare/run-20260930T103111870204Z/`.
Its actual file SHA256 is
`dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af`.
No fixed test or verifier regenerates this source. Missing or changed source is a failure.
Domain1's terminal fine row60 has world z=70, wet x=38..41:

```text
H2:    4.041177288138214, 3.626589853601033, 3.5, 3.661091270347399
water: 4.275,             4.2375,            4.2, 4.2
actual terminal cut Q: 0.200049 m3/s
```

The center index is 2 (x=40). Only its water level is 4.2 m; the actual transverse
water profile is preserved, never overwritten with a uniform 4.2 m stage.
Q is taken from one unique active terminal cut, not summed over accumulated river nodes.
World output columns are X,Y,Z, with Y as bed or water elevation in the common datum.

Construction first invokes existing prepared-domain validation and `_proof_gate` for the
selected accepted recovery. It saves the complete selected fine payload plus full H0
coarse contributor indices/weights. Static validation does not call those entry points.
Instead it checks saved candidate routing semantically via `_validate_plan`, then directly
binds candidate bounds to original recovery H0, Q, receiver/order/outlets, domain/protection,
source identity, physical recipes and world metric coordinates. Other domains are not resampled.
Recovery/surface/valley/ledger identities, original budgets, cut chains and the complete
saved H0/H1 contributor equations are checked without generating a surface.

Actual graph stage must satisfy original preferred-bed/nominal-depth, receiver stage slope,
depth and lift equations, actual wet/bed matching, and terminal boundary stage.
**Accepted static dependency:** the frozen `surface_fine_mosaic._static_water_support`
checks saved channel seeds and actual wet water against nearest-edge interpolated graph
stage/radius/reach and original inundation recipes. This is algebra on saved geometry,
not inundation replay. The coast module does not modify mosaic or invoke its constructor.
The verifier binds this dependency's actual source file SHA256 as well as other reused
static proof modules. Hashes alone are not treated as semantic acceptance.

## Complete source coverage and geometry model

The finite first version deliberately rejects curved strips, subsampling, skipped source
cells, unsupported refinements, unaligned nodes and partial attachment sampling.
Every river cross-section node must be a contiguous aligned fine node. Corridor x spacing
and sea x spacing must equal the river fine x spacing. Every station interval must equal
corridor z spacing. River, corridor and sea attachment nodes must align to their source grids.

Source surface model is explicitly
`nodal-piecewise-linear-triangles-topright-to-bottomleft`, **not bilinear raster interpolation**.
Each source grid cell consists of the same two triangles as the output strip. H0/H2/water
are affine within each triangle. The complete full-width strip therefore covers every
source node/cell at its own precision; no interior ridge, protected/unknown node or negative
depth can hide between mesh vertices. Full source node indices, per-vertex four-slot support,
weights and every source triangle mapping are saved and algebraically checked on load.
The positive case covers 84 corridor nodes and 120 nondegenerate triangles over 60 m2.

Bed and actual transverse water profiles vary linearly along each longitudinal line from
the saved river to the explicit sea source. The corridor must independently supply exactly
these H2/water values; unsupported geometry is rejected. The fixed sea attachment at z=90
has H2=-0.5 m, stage=0 m, positive water depth, valid wet ocean support and the same datum.
Centerline XYZ is `[40, 4.2*(1-f), 70+20*f]`, not a dynamically calculated fall trajectory.

Every vertex is unique in XZ, every triangle is nondegenerate and the saved rectangular
topology is checked for full connectivity. Unknown/protected/invalid/nonwet support, missing
sea/corridor, high sea level, inconsistent datum, source mismatch and resource excess reject.

## Cut ledger and resources

New cut is actual explicit corridor H0 minus H2 at every covered source node.
Depth cannot be negative. Cut volume is the exact integral for the declared source-triangle
affine model: sum of each triangle's planar area times mean of its three vertex cuts.
This is not a vertex-only approximation to an unspecified bilinear or higher-resolution source.
The original river is attached without recutting it; upstream budgets are rechecked separately.
Original max cut depth and volume are never increased to make a rejection pass.

Hard ceilings: 250,000 source cells, 20,000 mesh vertices, 40,000 triangles,
500,000 mesh work units, 64 MiB retained bound. Dimension preflight precedes output allocation
and full-result freezing; source dataclasses enforce shape caps before copying.
The retained estimate includes saved prepared proof, full fine support and output bounds.
It is not a bound on all transient Python/NumPy RSS. Static proof cost also depends on the
bounded saved candidate/fine source and active edge count; this is not a general unbounded solver.

## Static persistence and tampering

NPY v1 in ZIP_STORED, no pickle, no compression/encryption. Caps: 64 MiB file and aggregate
payload, 2 MiB metadata, 2048 members, 2 KiB NPY headers, bounded dimensions/dtypes/nesting.
Unique JSON keys/member names, exact header+payload lengths, expected tree references,
array content hashes and all headers are checked before array payload allocation.
Original saved output/source resource ceilings are checked before reading array payloads.

Save validates first, writes to a same-directory temporary file, fsyncs, closes the fd,
and atomically hardlinks to a previously nonexistent target. It never overwrites and cleans
temporary files/fds on failures. The filesystem must support hardlinks; no overwriting fallback.
Load/query do not call prepare, recover, `_stencil`, `_triangles`, `_corridor_cells`,
`_source_triangles`, `_attachment`, `_sample`, `_proof_gate`, domain evaluation validation,
or consumer `_fine_source`. They verify saved mappings and geometry equations directly.
Semantic SHA256 is not an authenticity signature. Rehashing a false transverse water profile
through surface, ledger, recovery, prepared product, new corridor and final result must still
fail original graph-stage support. Coherent source Q/H0/grid substitutions fail candidate binding.

## Validation and evidence

```text
python -m unittest tests.test_surface_coast_drop -v
python tools/verify_surface_coast_drop.py
```

The UTC verifier saves new runs under `verification/surface-coast-drop/run-<UTC>/`;
`--output-root` and `--skip-tests` are supported. It keeps positive NPZ/JSON, full attachments,
centerline XYZ, Q/cut ledger, rejection reasons, test logs and report.json. Failure retains
started.json, prior artifacts and traceback, returning 1. No GPU/game/Java is started.
Source code/tests/verifier/docs, reused static dependencies, the old prepared source and
every output bundle/evidence file receive actual **file SHA256**, distinct from semantic identity.
The final report does not hash itself; seal it externally if needed.

Focused tests include actual nonuniform river profile, terminal Q, sea attachment, all covered
source triangles, exact cut integral, hidden interior ridge/negative depth/unknown/protection,
skipped source cells, high/missing sea, budgets/resources, rehashed geometry/mappings/ledger,
complete coherent false transverse water and original Q/H0/grid source chains, immutable arrays,
atomic cleanup, malformed archives and default load with mapping/generation functions disabled.
Passing this slice does not close task26, full surface engineering, or natural-outlet gates.
