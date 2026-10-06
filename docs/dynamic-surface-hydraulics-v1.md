# Dynamic surface hydraulics v1

## Scope and API

A bounded, constant-bed storage/conductance graph using synchronous explicit Euler.
Algorithm identity: `dynamic-surface-storage-conductance-v1`.
Storage format identity: `dynamic-surface-hydraulics-npy-v1`.
This is not Saint-Venant, momentum/dynamic-wave simulation, calibrated Manning hydraulics,
or a shallow-water CFL certificate.

Geometry mode is explicitly `explicit-storage-graph-not-legacy-integrated`.
There is no legacy river-network integration or validated recovery-to-graph adapter.
There is no coarse/fine/H0/H2 source-graph proof or cross-domain certification.
The `source` string is a caller declaration, not verified source-graph provenance.
These engineered benchmarks do not certify real mountain terrain, natural coastal outlets,
or Minecraft water connectivity. The separate coastal-drop slice is not implemented here.

Public API in `terrain_pipeline.dynamic_surface_hydraulics`:

- `HydraulicsInput(...)`: resource preflight, validation, and immutable input snapshots.
- `ResourceLimits(...)`: caller-tightened limits, never above the hard ceilings.
- `evaluate(inputs, cancel=callable)`: explicit time advancement returning `HydraulicsResult`.
- `validate(result)`: static equations and hash checks using saved previous/next states and fluxes.
- `save(result, path)` / `load(path)`: bounded, self-contained persistence without pickle.
- `fingerprint(result)`: semantic content identity; rehashing cannot bypass equation checks.

Static validation and load do not call `evaluate`, an advance function, or legacy modules.

## Input contract

`N >= 1`, `T >= 1`; `E = 0` is supported. Numeric inputs must be finite real arrays.
Floats are normalized to float64, edges to int64, and masks must have actual boolean dtype.
Units are model metres and physical seconds, not game blocks or ticks.

| Field | Shape and constraints |
| --- | --- |
| `bed_m`, `area_m2`, `initial_stage_m` | `[N]`; area > 0; initial depth in `[0,max_depth_m]` |
| `edges` | `[E,2]` integer node indices, signed-flux reference orientation; no selfloops or undirected duplicates |
| `conductance_m2_s` | `[E]`, strictly positive; caller-provided linear engineering conductance, not Manning calibration |
| `local_q_m3_s` | `[T,N]`, signed; positive source, negative withdrawal; must be zero on fixed-stage boundary nodes |
| `boundary_mask` | `[N]`; at least one internal storage node |
| `boundary_stage_m` | `[T+1,N]`; only boundary columns prescribe stage; initial boundary must match initial stage |
| `valid_mask`, `protected_mask` | `[N]`; all valid and none protected, otherwise reject unsupported geometry |
| `coords_m` | `[N,2]`; planar coordinate axes explicitly described by `coords` |
| `source`, `datum`, `coords` | Nonempty provenance, common bed/stage elevation datum, and coordinate convention; each <= 1024 UTF-8 bytes |
| `dt_s`, `max_depth_m` | Finite positive scalars; no automatic time-step adjustment |

Finite future boundary stages may be below bed or above the depth limit: the first step
that would record such a stage fails without committing, retaining the earlier prefix.
This includes the terminal `boundary_stage_m[T]`. Nonfinite boundary inputs are rejected
before evaluation. Non-boundary columns are unused in equations but remain finite-checked,
saved in full, and bound to the identity hash.

Inputs are copied into immutable bytes-backed ndarrays. Caller arrays are never modified.
Setting the resulting arrays writable with `setflags(write=True)` is rejected.
There is no inferred geometry, protection waiver, or assumed provenance adapter.

## Equations and indexing

For internal nodes, `S_i = area_i * (stage_i - bed_i)` in cubic metres.
Fixed-stage boundary nodes have **zero internal storage** at every saved state.
Their area must be valid but their stage changes are not counted as stored internal volume.
Local Q on fixed boundary nodes is rejected rather than silently discarded.

Each reference edge is evaluated and saved once:
`Q_ij = K_ij * (stage_i - stage_j)` in cubic metres per second.
Negative edge Q is reverse flow. The two endpoint netQ contributions have opposite signs.
All edges in step n use saved `state[n]`, with boundary stage `boundary_stage[n]`.
All internal nodes update synchronously:
`S[n+1] = S[n] + dt * (localQ[n] + netQ[n])`.
Internal stage follows from storage. Saved boundary stage at `state[n+1]` uses
`boundary_stage[n+1]`, never prematurely in step-n flux.
Boundary-to-boundary edge flux is saved, but its net contribution to internal volume cancels.

Every internal node must satisfy `dt * sum(incident K) / area <= 1`.
This is a linear **diffusive stability bound, not shallow-water CFL**.
Different bed elevations and signed withdrawals can still produce negative storage.
Negative depth/storage, excessive depth, or nonfinite arithmetic rejects the original step.
No clamping, hidden dt reduction, edge removal, or source-input changes are permitted.
Inertia, supercritical/mixed flow, tides, free drops, wetting/drying and roughness calibration
remain outside this slice.

## Results, prefixes, and ledger

`result.inputs` contains complete geometry, full local-Q and `[T+1,N]` boundary histories,
provenance, and resource limits. After k committed steps:

- `stage_m`, `storage_m3`: `[k+1,N]`.
- `qedges_m3_s`: `[k,E]`.
- `time_s`: `[k+1]`, physical seconds.
- `ledger_m3`: `[k,6]`.
- `status`: `completed`, `cancelled`, or `failed`; `committed_steps = k`.

Cancellation is checked before each step's flux. Immediate cancellation retains state0.
Cancelled prefixes have no invented failed-step record. Static proof verifies a cancelled
prefix but cannot certify the authenticity of an external cancellation callback.

Ledger columns, in `LEDGER_COLUMNS` order, are storage before, signed local volume,
boundary volume into internal storage, storage after, storage change, and residual.
All ledger values are in cubic metres. Boundary influx is `-dt * sum(netQ[boundary])`;
`storage_change = local_volume + boundary_into_storage`. Internal edges cancel pairwise.
Static equations use `rtol=atol=1e-12`. Conservation residual must be at most
`1e-12 * max(1, abs(before), abs(after), abs(local), abs(boundary))`.

`FailedStep` stores step index, reason, previous stage, candidate next stage/storage,
edge flux, and a separate **uncommitted** ledger. Reasons are `negative_depth`,
`max_depth`, or `arithmetic_nonfinite`. The failed candidate is never appended to
committed arrays. Negative, excessive, and nonfinite failure evidence can be persisted.
Static validation checks the candidate equations, reason, and adjacency to the prefix.

Semantic SHA256 binds metadata, dtype/shape, every input, states, signed edge fluxes,
ledgers, failure candidates, and the complete boundary sequence. It is an identity and
integrity check, not a source authenticity signature.

## Resource and persistence safety

Hard caps: 4096 nodes, 16384 edges, 4096 steps, `T*(N+E) <= 2,000,000`, and
64 MiB retained-array/metadata upper bound. `ResourceLimits` can only tighten these.
Input dimension preflight precedes freezing/copying arrays; evaluate repeats preflight
before allocating full history. Result construction checks shapes/caps before freezing.
The estimate includes full inputs, maximum history, and a failed candidate. It bounds
retained bytes, not all transient Python/NumPy allocations or peak process RSS.

Bundles are unencrypted ZIP_STORED archives with NPY v1 members and one metadata.json.
Caps: 65 MiB file/aggregate payload, 24 members, 16 KiB metadata, 2 KiB per NPY header.
Load rejects duplicate member names, duplicate JSON keys, unexpected/missing members,
compression/encryption, oversized dimensions, object/pickle arrays, wrong dtype/shape/order,
unsupported NPY versions, excessive headers, truncated payloads, and trailing payload bytes.
All array headers are checked before payload arrays are constructed from immutable bytes.
Load then checks the content hash and saved equations without running the solver.

Save statically validates, writes a temporary file in the destination directory,
fsyncs and closes it, then atomically publishes with a no-overwrite hardlink.
Temporary files and descriptors are cleaned up on success/failure; existing targets stay intact.
The destination directory must exist and support hardlinks; there is no overwriting rename
fallback. Directory-entry durability under power loss is not claimed.

## Validation and file-hash evidence

```text
python -m unittest tests.test_dynamic_surface_hydraulics -v
python tools/verify_dynamic_surface_hydraulics.py
```

The verifier defaults to `verification/dynamic-surface-hydraulics/run-<UTC>/`;
`--output-root` and `--skip-tests` are available. It creates started.json before scenarios,
saves each bundle and case JSON before assertions, and always writes report.json on ordinary
success or failure. Unexpected failures preserve traceback, previous cases, and test logs.
Failure exit code is 1. Existing runs are not overwritten; no GPU/game/Java is started.

`source_files` and `source_files_at_finish` bind the actual bytes of the core source,
focused tests, verifier source, and this documentation via `file_sha256` and byte length.
A passing run requires those four files to remain unchanged throughout verification.
Each case binds its NPZ's actual file bytes via `bundle_file_sha256` and byte length,
and checks that reload leaves the file unchanged. This is separate from semantic
`identity_sha256`: a bundle file hash includes the archive container bytes.
The final report's `evidence_files` hashes every previously written evidence file,
including NPZ, case JSON, started.json, input rejection evidence, and available logs.
report.json cannot include its own file hash without circularity; hash it externally
when sealing evidence. Hashes do not authenticate an external terrain source.

Independent three-node benchmark: bed=0, area=10, K=1, dt=1, edges 0->1->2,
fixed node2 stage=0 and node0 localQ=1:

```text
states: [0,0,0] -> [.1,0,0] -> [.19,.01,0] -> [.272,.027,0]
fluxes: [0,0], [.1,0], [.18,.01]
internal total storage: 0, 1, 2, 2.99
```

With localQ=0 and tailwater=1:

```text
states: [0,0,1] -> [0,.1,1] -> [.01,.18,1] -> [.027,.245,1]
fluxes: [0,-1], [-.1,-.9], [-.17,-.82]
internal total storage: 0, 1, 1.9, 2.72
```

Tailwater=2 doubles the internal response. Steady localQ=1 has stage `[2,1,0]`
and both fluxes equal 1. Equal stage with zero localQ is unchanged.

Focused tests cover analytic delay/reverse flow/steady state, terminal boundary failure,
zeroQ, closed-volume conservation and signed sources, unequal-bed negative storage,
max depth, diffusive instability, unknown/protected support, all resource caps,
cancel prefixes, input/result immutability, rehashed state/storage/flux/ledger tampering,
load with evaluate mocked out, successful/failed/cancelled roundtrips, nonfinite failure
evidence, atomic no-overwrite and descriptor cleanup, hostile archives/headers/payloads,
verifier failure evidence, and independent source/bundle file SHA256 checks.
