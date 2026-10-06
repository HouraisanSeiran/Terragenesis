# Surface Variable Storage V1

Status: implementation evidence available after running the fixed verifier;
independent coordinator acceptance is pending. This module does not replace
accepted constant-area modules or their evidence.

## Geometry And Scope

Source: `verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/pulse.npz`.
Its SHA256 is `c85e8ef84b896df2f2f3e48d2c062bc9b9c0ddd66d4cf0b56320ef6cc6ea16cd`.
All 16 nodes, 14 edges, two prescribed boundaries and 676 uniquely assigned
wet cells remain bound to the original two-domain forest and saved mosaics.

For each owned cell's two saved triangles, each bed vertex receives horizontal
triangle area / 3 (cell area / 6). The node storage law is
`V(h) = sum(weight_m2 * max(h - bed_vertex_m, 0))`.
This is a lumped vertex-prism approximation: piecewise linear, strictly
increasing above the minimum bed, zero at its canonical dry stage. It is NOT
the exact continuous partially submerged triangle integral. A uniform node
stage is not the spatially varying saved fine-grid water surface.

At the unchanged source initial node stages, internal storage is
224.5721879136545 m3, 112.28609395682724 m3 per domain, not the constant-area
322 m3 or static fine-surface integral 236.01507098278893 m3. Boundary nodes
have zero accounted storage even though their support curves are retained.
No cumulative source river Q is reused as a local inflow.

There is no expanded flood footprint, inertia/momentum, measured cross section,
natural outlet certification, continuous dynamic mesh, complete physical-land
coverage or frontend acceptance. The existing bounded node envelope does not
become the complete original pixel footprint through this storage model.

## Stable Interface For Optional B32 Binding

`prepare_surface_variable_storage(source, *, conductance_m2_s, local_q_m3_s,
tailwater_m, dt_s, max_depth_m, resources=StorageResources(), cancel=None)`
explicitly constructs curves and advances the saved forest. `source` is the
validated immutable forest record, not a path or a new generation request.
The immutable returned mapping embeds the full source and its identity.

- K: `(edges,)`, finite positive m2/s, constant throughout the run.
- Local Q: `(requested_steps, nodes)`, finite m3/s, zero on boundary nodes;
  signed extraction is allowed, but negative resulting storage is rejected.
- Tailwater: `(requested_steps + 1, boundary_count)`, m, boundary-mask order;
  row zero exactly equals source initial boundary stages.
- `dt_s` and `max_depth_m`: positive finite Python int/float, never booleans;
  the saved scalars are float. Depth is stage minus saved node bed, in m.
- Cancel callback: checked before each step; cancellation retains a valid
  committed prefix. Numerical failure similarly retains no partial step.

The conservative stability bound is
`dt_s * sum(incident K) / minimum_positive_support_area <= 1` for internal
nodes. Minimum areas on this fixture are 0.5 and 0.8333333333333333 m2.
The evidence uses K=1, dt=0.1, 80 steps: **8 physical seconds**, not 80 seconds
and not Minecraft ticks. A pulse injects 1 and 2 m3/s for the first step at
nodes 0 and 8; the raised case sets domain 2 tailwater to 5.1 m after row zero
(baseline tailwater is 4.2 m). Both domains retain their own accounting.

`validate_surface_variable_storage(record)`, `load_surface_variable_storage(path)`
and `query_surface_variable_storage(record, *, state_index=None)` validate saved
algebra only: never `_geometry`, `_knots`, `_advance`, prepare, bind, sampling or
recovery. Validation proves support against saved triangles, every knot, each
node V(h), K times stage difference, Euler storage, per-domain/global ledger,
stage bounds, canonical dry stage, and failed-step reason. Query returns frozen
node keys, stages, storage, time and status; state index must be a Python int
inside the committed prefix. Full forcing remains saved even for short prefixes.

Consumers can bind the optional record using `record['source']['identity_sha256']`
to their exact forest identity and domain/node/edge layouts. Do not equate the
new dynamic storage ledger to static geometry budgets or constant-area storage.
The record includes `support_*`, `knot_*`, `stage_m`, `storage_m3`,
`qedges_m3_s`, `time_s`, `ledger_m3`, `domain_ledger_m3`, `status`,
`committed_steps`, `failed_step`, `identity_sha256` and explicit false
natural/full-wave certification flags. Ledger columns are before storage,
local volume, boundary inward volume, after storage, storage change, residual;
Q is positive from edge endpoint 0 to endpoint 1.

## Resources And Publication

Resource preflight precedes source validation and geometry allocation; node,
edge, step, wet-cell, work, retained and working byte caps are enforced.
Saved records enforce float64 state/support arrays and int64 ownership/offsets.
Strict ZIP member sets, bounded raw NPY v1 headers, literal shape integers
(not floats/booleans), actual boolean Fortran flags, canonical numeric dtypes,
payload sizes, array hashes and identities are checked before accepting data.
Rehashing a corrupted record does not bypass mathematical validation.

`save_surface_variable_storage(record, path)` writes and fsyncs a temporary in
the destination directory, publishes via an atomic no-overwrite hard link,
and removes the temporary on failure/success. Unsupported hard links fail
closed; an existing or racing destination is never overwritten. It does not
promise directory-fsync durability after power failure.

## Verification

Run `python -m unittest tests.test_surface_variable_storage -v` and
`python tools/verify_surface_variable_storage.py` from the workspace root.
The fixed verifier creates only a fresh
`verification/surface-variable-storage/run-<UTC>/` containing baseline, pulse,
domain2-tailwater-rise, failed-prefix (one committed step), cancelled-prefix
(zero steps), focused test log and report.json. The report records source,
implementation and archive hashes, identities, forcing outcomes, propagation,
reverse flux and independently recomputed source-triangle storage and ledgers.
This implementation-local audit is not a substitute for coordinator review.
