# Surface dynamic prepare v1

## Bounded source adapter

This four-file slice adapts an actually accepted recovery, a selected actually prepared
domain evaluation, or a saved statically validated single-proof mosaic into the already
accepted fixed-area storage/conductance graph. It is not a new hydraulic solver.
`full_dynamic_wave_prepared=False` and `natural_outlets_certified=False` remain mandatory.
No old modules, frozen mosaic files, original evidence or TODO are modified.

`bind_surface_dynamic_source(source, vertical_datum=..., domain_id=None)` explicitly fixes
geometry and node order but does not advance time. For a multi-domain prepared evaluation
select exactly one domain. The original two-domain gap remains uncovered; adapting domain1
does not close it. Recovery inputs use the existing actual `surface-network-recovery-v1`
version and `_payload`/`_proof_gate` through explicit mosaic preparation, never recovery replay.
For an existing saved mosaic, reuse its retained static proof and original coarse H0 support.
Mosaics with multiple proofs or partial active graphs are outside this first adapter scope.

`prepare_surface_dynamic(binding_or_source, conductance_m2_s=K[E],
local_q_m3_s=Q[T,N], tailwater_m=eta[T+1,B], dt_s=..., max_depth_m=...)`
is the only time-advancing adapter call. Without a binding supply its vertical datum and
optional domain selection. K in m2/s is explicit caller conductance, not calibrated Manning
or a value inferred from source reach Q. Signed caller local Q in m3/s is independent of
the source static graph Q; source accumulated discharge is not reused as dynamic input.
Tailwater columns follow actual outlet order within saved node order. Time-zero tailwater
must equal actual saved outlet water. Boundary local Q must be exactly zero.

## Actual source graph and lumped area

Nodes are all and only actual active coarse flat ids in increasing order, unique coordinates;
edges are actual active receiver edges, in donor order, without new channels or cross-domain
links. Boundary nodes are precisely actual active outlets. Node coordinates must fall
exactly on the fine grid; fractional positions are rejected, never rounded into different
support. Node bed comes from actual delivered fine H2, not H0, with graph bed-match gate.
Initial stage comes from actual fine water and equals saved graph node stage. Active nodes
must have actual positive wet depth and legal source domain/protection support.

Every actual wet fine cell of the single-source mosaic is assigned once to the nearest
active graph node by squared center-to-node world distance. Exact ties use the first node
in increasing flat-id order. This is deterministic Euclidean Voronoi lumping, not a
river-catchment assignment or a derived cross-section curve. Each cell contributes its
plan area dx*dz once. `A[node] = cell_count[node]*dx*dz`; any active node with A=0 rejects.
No minimum artificial area, mesh-water fitting or cell duplication is permitted.

A is constant as stage changes: `S=A*(eta-bed)` for internal nodes. It is **not real section
V(h)**. Initial lumped storage generally differs from the source bilinear/triangle water
volume; no source wet-water volume conservation is claimed. Cells assigned to fixed-stage
outlets remain explicitly counted in the area mapping, but are open-boundary cells and
excluded from internal storage. Their dynamics are represented by signed boundary flux,
not a simulated boundary reservoir or the whole source wet water body.

The saved old domain1 case has 338 wet cells, 8 nodes, 7 edges,
flat ids `[9,11,16,17,23,30,37,45]`, areas `[22,40,48,84,55,40,33,16]` m2.
Internal area is 322m2 and initial internal lumped storage is 161m3. The fixed outlet's
16m2 is not included in that storage. Five steps use caller K=.01m2/s, dt=.1s,
first-node localQ=.1m3/s and the actual saved outlet stage.

## Existing dynamic approximation

The accepted `dynamic_surface_hydraulics` module supplies synchronous explicit updates:
`Qij=Kij*(eta_i-eta_j)`, `Snew=S+dt*(localQ+netQ)` with actual fixed tailwater histories.
Negative edge flux is reverse flow. Stability is `dt*sumK/A<=1` on internal nodes,
not shallow-water CFL. Original steps fail for negative/too-deep/nonfinite states;
no clamping, hidden dt reduction or physical budget loosening. Cancellation/failure retain
only the committed prefix and, for failures, the algebraically checkable rejected step.
Stage/flow/ledger is not inertia, full river dynamics, tides, free-fall/coast drop,
natural-source certification, wetting/drying or completed 3D prerequisites.

## Self-contained saved semantic proof

NPZ contains the source mosaic including accepted recovery/coarse H0 support, graph/fine
node mapping, original actual wet cell ids, nearest-node ownership, A, bed/stage, full caller
K/Q/tailwater histories and the dynamic result with committed prefix and failure details.
Arrays and mappings load immutable.

Default load/query validate saved source using frozen mosaic's static validator, source
H0/H2/wet/water/protection and actual graph constraints; directly check saved node/edge/fine
mapping, nearest/tie ownership, exact wet cell set, A and unique area. Dynamic inputs must
equal these bindings, and saved state/flux/QV ledgers satisfy the existing static equations.
Hash identities alone do not suffice. No evaluate/recover/mosaic prepare, coarse-support
generation, stencil, mesh/ownership generation or resampler runs on load/query. No complete
mapping/geometry result is regenerated for comparison; saved ownership is checked by distance.

Resource ceilings cover wet cell count, cell*node assignment work, retained/working bytes
and existing dynamic node/edge/step/work limits. Load uses one retained file handle, file
and uncompressed byte caps, unique JSON/ZIP names, raw NPY header cap and exact payload
sizes. Resource schemas and actual headers are checked before `np.load`. Invalid duplicates,
unused arrays or hash/shape/dtype differences reject. Save closes fd, fsyncs and atomically
hard-links without overwrite; failures remove only its temporary file.

## Fixed evidence entrypoint

`python -m unittest tests.test_surface_dynamic_prepare -v`

`python tools/verify_surface_dynamic_prepare.py`

Fixed cases use existing saved evidence (not a reconstruction substituted for old evidence):

- `verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz`,
  SHA256 `dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af`.
- `verification/surface-fine-mosaic/run-20260930T123659.258177Z/single-proof-terminal.npz`,
  SHA256 `8d4e26492f2b6314e2d6139717855870e3cdf296b1b814d7dde0e27347983617`.

Unique output `verification/surface-dynamic-prepare/run-<actual UTC microseconds>Z/`
records source/bundle/implementation and frozen dependency SHA256, actual start/finish,
static no-generation reload, independent per-step QV recomputation and focused test counts.
Failure also writes report and traceback. Cases include saved old domain1, steady state,
inflow pulse with delayed downstream response, raised tailwater and reverse/upstream
feedback, cancellation and rejected excessive-tailwater prefix. Tests exercise coherent
rehash A/ownership/source unknown/protection/stage and dynamic equations, resource gates,
readonly results and atomic/nooverwrite/archive safety.
