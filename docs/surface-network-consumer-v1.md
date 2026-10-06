# Surface Network Consumer v1

## Scope

An explicit, non-game terrain and hydrology delivery. It does not publish lake water
or connect to a default world. Export accepts only an actually accepted result from
`validate_surface_network_recovery`, which semantically replays recovery at export.
Loading, sampling and slicing never call recovery, prepare, reroute, models or GPU.
Loading checks stored geometry, Q, budgets and provenance rather than searching again.

Legal outlets and outlet stages are caller constraints, not certification of natural
coasts or real downstream destinations. A synthetic two-source mountain/coast network
does not establish a closed rainfall catchment over all land, steep-gorge acceptance,
or real Fuxi geography. Hashes ensure content integrity, not signatures or source truth.
A malicious issuer rebuilding every source, recipe and hash is not authenticated.
The package retains full recovery inputs, recipes, attempts and selected plan/surface/
valley/ledger. Default load checks their actual stored consistency, not algorithm replay.

## API

```python
export_surface_network(recovery, vertical_datum, path,
    source_declaration="Engineered synthetic source; local metre datum; not real geography")
delivery = load_surface_network_delivery(path)
window = slice_surface_network_delivery(delivery, slice(10, 41), slice(20, 51))
world_window = slice_surface_network_world(delivery, (20., 10., 50., 40.))
sample = sample_surface_network(delivery, 30., 20.)
```

Both `vertical_datum` and keyword `source_declaration` are explicit, nonempty strings.
Unknown placeholders are rejected. When recovery has no real datum evidence, name a
local/synthetic datum, rather than claiming a real geodetic elevation system.
Heights, origins, spacings, stages and depths are metres; discharge is cubic metres/second.
Fine arrays use `[z,x]`; world positions use `[x,z]`; coarse ids are row-major `z*cols+x`.
Queries address existing aligned fine nodes: no implicit interpolation or grid expansion.
World bounds are inclusive `(xmin,zmin,xmax,zmax)`; index slices are Python half-open.
Returned mappings and byte-backed arrays are immutable. Loading/window order does not
change values. Windows use the same full-domain grid; depth uses stored stage/H2 subtraction.

## Directory and Identity Chain

```text
delivery/
  manifest.json
  base/manifest.json
  base/arrays.npz
  derived/manifest.json
  derived/arrays.npz
  hydro.npz
```

The two terrain directories use existing generic `TerrainArtifact` storage:

- Base contains original fine H0. Baseline/reroute take surface source; valley takes
  fine-ledger source. Post-valley H1 must never masquerade as original H0.
- Derived references the same H0, with vertical displacement H2-H0 and zero horizontal
  displacement. Its source content id points to base.
- H1 is recorded separately in the hydrology geometry.
- Neither package attaches `TerrainArtifact.water`: reach Q samples are not wet-cell Q.

The root manifest binds algorithm version, both content ids, declaration, datum/grid,
recovery identity, full proof, array dtype/shape/hash, five file hashes and hydrology
semantics. Proof arrays are in hydro.npz; legitimate repeated references are permitted.
Export builds and validates a sibling temporary directory, then publishes with
`os.rename`. Existing files/directories cannot be overwritten. Windows final rename
also refuses a target created after the explicit existence check. Cleanup checks its
resolved staging path before deleting. Symlinks/junctions in the path chain are rejected.
All three NPZ uncompressed declarations total at most 256 MiB; each JSON is at most
4 MiB. Object arrays, duplicate members, unsupported dtypes and excessive/false shape
headers are rejected. JSON duplicate keys and nonfinite constants are rejected.

## Hydrology Sidecar

Fine geometry fields: `source_surface_m` (H0), `valley_surface_m` (H1),
`final_surface_m` (H2), `valley_cut_m` (H0-H1), `bed_cut_m` (H1-H2),
`total_cut_m` (H0-H2), `water_surface_m`, `wet_mask`, `domain_mask`,
`protected_mask`, `legal_outlet_mask`.

Wet `water_surface_m` is actual stage. Dry cells store finite **zero as a placeholder,
not sea level**. Always consult wet_mask first. Samples/windows include read-only
`water_depth_m = where(wet, stage-H2, 0)`. Original surface proof retains original dry
NaNs; delivery stages map exactly through wet_mask.

The separate coarse centerline table includes every original coarse node:

| Field | Meaning |
| --- | --- |
| world_xz_m | World `[x,z]`, shape `[N,2]` |
| receiver | D8 downstream id; -1 denotes outlet |
| order | Receiver-first topological order |
| discharge_m3_s | Node reach Q sample, not additive across nodes |
| active_mask | Active channel; inactive nodes are not published water |
| outlet_mask | Plan outlets; active ones must map to explicit fine legal outlets |
| local_discharge_m3_s | Q(node)-sum(Q(donors)), for source conservation |
| node_stage_m | Actual fine stage at active coarse nodes; inactive placeholder zero |

No wet-Q raster, outlet copying, or nearest-reach Q assignment is inferred. Sum Q only
at an explicitly chosen outlet set, not all repeated reach samples along tributaries
and trunk. Inactive nodes can retain local source Q; their outlets are not certified.

## Load Gates

Load rejects broken hashes/source chains, negative cuts, H0 substitution, H1 inconsistent
with final coarse source, bed/cumulative fine-budget failure, protected/out-of-domain
cuts or water, full coarse/fine constraint mismatch, nonconservative Q or changed local
sources/outlets, wet water not four-connected to a legal outlet, undeclared boundary
contact, and actual fine channel lines that are dry, reverse-sloped or outside depth limits.
Adjacent wet stage differences use the original `max(0.5, min_water_depth_m*10)` gate;
the consumer never raises it to force acceptance. Prepared disconnected/boundary/reach
masks and corresponding diagnostics must be empty. Rehashed joint labels cannot bypass
actual stage jumps, fine masks, H0/H2 consistency or water geometry checks.

Cut budgets integrate a **fine node grid**, with half weights at edges and quarter
weights at corners. This differs from lake full-cell storage-area integration.

## Verification

Run `python tools/verify_surface_network_consumer.py`.
Outputs are under `verification/surface-network-consumer/run-<UTC>/`: report, three
deliveries and rejected forged packages. Verification covers baseline/valley/reroute,
dual-package provenance, Q, persistence, overlapping windows, immutability and forbidden
generation during reads. Lake mixing, complete real catchment scheduling, game adapters
and terrain naturalness remain outside this module.
