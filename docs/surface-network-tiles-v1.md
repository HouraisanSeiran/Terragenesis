# Surface network tiles v1

This is a bounded storage slice for already accepted `surface-network-consumer-v1`
deliveries, not a new river planner, hydrology solver, resampler or game adapter.
Implementation verification and coordinator independent acceptance are separate.

## Public interface

`prepare_surface_network_tiles(source_path, destination_path, *, tile_cells=64,
max_tiles=None, cancel=None, resume=False)` explicitly validates and copies an
accepted delivery. It returns the destination `Path` on completion or `False` on
cancellation/work-budget pause. The destination parent must exist, the destination
must not exist or be inside the immutable source. No overwrite, branch, commit,
generation or dependency installation occurs.

`tile_cells` is an integer square cell span, 1–255, not a node count. Rectangular
tile spans such as `(13, 17)` are **not supported**. Tiles are row-major, cover
half-open node bounds `[z0,z1,x0,x1]`, and share one node row/column. A 61×61 node
grid with span 13 has 25 tiles; the final tile is `[52,61,52,61]` (9×9 nodes).
Partial final tiles are required, not padding or clipping of the source.

`load_surface_network_tiles(path)` reads the bounded manifest and coarse graph
only. It refuses unfinished staging. `allow_staging=True` is reserved for the
prepare publication audit and does not make an incomplete index valid.

`slice_surface_network_tiles(store, z_slice, x_slice)` accepts explicit bounded
unit-step integer slices. Exact rectangular **query windows** are supported.
`sample_surface_network_tiles(store, world_x_m, world_z_m)` returns one node using
the existing same-grid nearest-index coordinate contract, not interpolation.
`slice_surface_network_tiles_world(store, (xmin,zmin,xmax,zmax))` includes both
endpoint indices. Results contain metre coordinates, declared vertical datum,
content identity, geometry arrays and derived `water_depth_m` (zero on dry nodes).
Arrays have immutable bytes backing: enabling `flags.writeable` fails. All nested
manifest dictionaries and lists are frozen into mappings and tuples.

## Lifecycle and ownership

`destination.staging/progress.json` binds source manifest/content identity, grid,
square span, exact ranges and completed array/file hashes. Only the exclusive
`.prepare.lock` owner cleans its token-matching lock, including after directory
publication. A failed contender cannot erase the owner's lock or admit a third
call. A stale lock after a process crash requires operator investigation; there
is no automatic stale-lock takeover.

`max_tiles` counts newly written tiles, not already completed tiles. Resume is
explicit and revalidates source, copied evidence, graph, completed tile payloads
and window proofs before checking cancellation or continuing. Source/recipe
changes and completed tile damage are rejected, never silently repaired.
Uncommitted leftovers may be overwritten on explicit resume. Cancellation is
cooperative between tiles and publication phases, not interruption of a file
write. Callback exceptions propagate and leave unpublished staging.

The manifest is written atomically last; preparation performs full audit before
renaming staging to the absent final destination. A final lock temporarily rejects
readers until the owner finishes cleanup. Filesystem writes are not a transactional
database or a full power-loss durability guarantee.

## Evidence and lazy gates

Each accessed tile reads its NPZ **and** a bounded corresponding `proof/NNNNNN.npz`
source window, without loading full `source/hydro.npz`. Window records are bound
to the preparation recipe and source identity. Exact comparison rejects rehashed
tile-only changes to bed, actual stage, masks, newly added wet nodes or disconnected
wet islands. Additional local semantic gates check H0/H1/H2 cuts, original maximum
cut depth, wet minimum depth, dry stage zero, domain/protection/outlets, wet-stage
transitions, active-node actual stage and channel-edge clearance/depth/slope.
Cross-window overlap values must match exactly. Unvisited tiles are not certified
by a successful lazy query.

Hash identity is **not publisher authentication**. If an adversary rehashes both
a tile and its source-window proof, locally plausible changes can pass a lazy
query. Full audit against the retained consumer evidence then rejects mismatch;
rewriting that entire evidence chain is outside an unsigned content hash trust
model. Pin a trusted content ID and use full audit at an external trust boundary.

Only the six fixed declared consumer files are copied under `source/`, never
undeclared files or recursive extra directories. Links in used paths are refused.
The existing consumer loader also rejects extra top-level source layout entries;
preparation does not loosen that input protocol.
The original external source may disappear; queries and full audit use only the
final package. Removing its *embedded* evidence is not supported for full audit.

## Hard bounds and audit

- Manifest: 4 MiB; grid: at most 1,000,000 nodes; tiles: at most 100,000.
- Tile: at most 65,536 nodes; NPZ file and aggregate uncompressed members: 64 MiB.
- Query window: at most 65,536 nodes, checked before allocation or tile reads.
- Cached tile array payloads: at most 64 MiB; oversize tile refused before load.
- Embedded source: six fixed files, at most 512 MiB in total.
- Coarse graph: at most 250,000 nodes, integer receiver/order and outlet-first
  topological order; Q is reach discharge, never an additive fine-grid raster.

Cached tile and proof files are size-bounded and hashed on **every** access;
immutable cache payloads cannot hide a changed file. Cache overflow evicts the
whole cache, and a single oversize tile is rejected. The cache limit measures
retained ndarray payload bytes, not total Python/ZIP/temporary proof/window memory.
Header preflight rejects compressed members, objects, wrong dtype/shape, excess
aggregate uncompressed bytes, duplicate members and inconsistent payload hashes.
The reader is not synchronized for concurrent queries; callers must serialize
access to one store instance. It does not protect against hostile concurrent
filesystem replacement between preflight/hash/read operations.

`verify_all_tiles(store)` is an explicit full, generation-free audit. It replays
the retained accepted consumer semantics and original budgets, compares every
tile and graph to that source, checks all seams and full coverage, and returns a
deeply immutable report, not merely `True`. `unique_nodes` counts each global
node once. `integrals` applies half weights only on the global outer boundary,
quarter weights at corners. `tile_weighted_integrals` independently sums each
tile's own half-edge/quarter-corner weights; shared nodes split those weights.
Both include valley/bed/total cut volume (m³) and changed area (m², cut > 1e-9).
This additivity is valid only for exact tiling, not arbitrary overlapping queries.

## Fixed verification

Run from the workspace:

```powershell
D:/anaconda/python.exe -X utf8 -m unittest tests.test_surface_network_tiles -v
D:/anaconda/python.exe -X utf8 tools/verify_surface_network_tiles.py
```

The verifier uses the final accepted consumer directory
`verification/surface-network-consumer/run-20260930T080544.956105Z/`, never edits it,
and creates a new UTC directory `verification/surface-network-tiles/run-UTC/`.
It saves baseline/valley/reroute, resumed and standalone success packages, fixed
failure packages/staging, a focused test log and `report.json`. It never writes
`independent-review.json` or claims coordinator acceptance.

The specified total-cut volume/area references are baseline
169.508735962729/518.5, valley 1051.594182146892/2930, and reroute
29.111269224638/89.5. Remaining system gaps include cross-resolution scheduling,
natural outlet certification, hydraulic dynamics and game consumption; this
storage slice does not close them.
