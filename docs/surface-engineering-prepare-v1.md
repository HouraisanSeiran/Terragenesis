# Surface engineering prepare v1

`prepare_surface_engineering(evaluation, outlets, conductance_m2_s=..., local_q_m3_s=...,
tailwater_m=..., dt_s=..., max_depth_m=...)` explicitly builds the accepted full-domain
node mosaic, one engineered coast drop for each declared domain, and one constant-area
dynamic forest over all domains. `outlets` is keyed by domain ID and must supply an actual
`RiverAttachment`, independent `EngineeringSource` corridor and sea, stations, and a
`DropBudget` for every domain. `compose_surface_engineering` accepts already prepared
components for reuse and validates the same bindings. Neither entry publishes a partial
artifact on cancellation or failure.

The bundle keeps the full nested evaluation, every recovery proof, candidate identity,
complete declared node envelope, original source contributor maps, separate coast cut
ledgers, static terminal Q, dynamic local Q histories, and per-domain/global forest ledgers.
Validation checks every nested static product, matching evaluation/proof/domain identities,
datum, sea plane, coast terminal coordinates and initial forest boundary stage. `save` uses
a same-directory temporary file and atomic no-overwrite hardlink. `load` preflights ZIP and
NPY v1 headers, exact payload sizes, member uniqueness, dtype and resource ceilings before
allocating arrays; load and query invoke only static validators. Pickle/object arrays and
compressed or encrypted archives are rejected.
NPY header dictionaries are parsed with strict AST/literal types: exactly three unique
keys, a string dtype, a real false boolean for Fortran order and a tuple of real integer
dimensions. Float/bool dimensions, integer Fortran flags and duplicate keys are rejected
for every member before any `np.load` call.

The fixed evaluation is `verification/surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz`,
file SHA256 `dbae847e05df6266ff67ef52c2f759413e75164bec9ea89c7587a6636f9fc9af`.
Both synthetic coast strips run from actual fine river terminals at z=70 to z=90; domain1
uses x=38..41 and domain2 uses x=108..111. Each full-width H2, water, and H0 attachment
is sampled from its own accepted recovery. Center index is 2. The sea plane is 0 m.
The old graph terminal Q is about 0.200049 m3/s per domain; caller local dynamic Q is a
different quantity and does not have to equal it.

`declared_node_envelope_complete=True` covers x=10..140, z=10..70 at 1 m precision.
It does not cover the original candidate land pixel footprint x=5..145, z=5..75:
the original 98 land pixel centers at 10 m spacing represent 9800 m2, while this
node envelope has area 7800 m2. The synthetic strip from z=70 can overlap the
unmodeled physical land footprint to z=75. Accordingly `physical_footprint_complete`,
`natural_outlets_certified`, `full_dynamic_wave_prepared`, and `ready_for_3d` are false.
No combined triangle surface is offered as nonoverlapping full physical land geometry.

The coast drop is fixed reference geometry from static river stage 4.2 m to sea 0 m.
Forest states can use later caller tailwater, including a raised level; no per-step dynamic
coast mesh or stage-consistent drop geometry is claimed. The forest uses constant lumped
node area. Its internal initial storage (322 m3 for the fixed pair) is not the mosaic's
triangle water volume (236 m3), and coast cut budgets are separate from upstream valley
cut budgets. This slice is independent of stage-dependent storage work.

Run `D:/anaconda/python.exe -X utf8 -m unittest tests.test_surface_engineering_prepare -v`
and `D:/anaconda/python.exe -X utf8 tools/verify_surface_engineering_prepare.py`.
The verifier writes a new UTC directory under `verification/surface-engineering-prepare/`
with a saved NPZ, focused test log, hashes, identities, ledgers and report. It never changes
the accepted source or older evidence.

Aggregate generated-resource preflight runs before any mosaic/drop/binding/advance:
it accounts for all domain grids, nested evaluation copies, coast outputs and supports,
global forcing/states and optional variable support/forcing, with a conservative working
copy allowance. A caller cap is not deferred until after component allocation.

`query_surface_engineering(..., state_index=..., variable_state_index=...)` uses independent
committed-prefix selectors and returns immutable saved mosaic nodes/cells/triangles,
both outlet XYZ meshes, node keys/edges/coordinates, stages/storage/time and ledgers.
An omitted selector returns that model's whole saved prefix; an integer selects only
that model. Boolean and floating indices are rejected. Different model time axes are
not silently synchronized. No variable import or preparation occurs for the None case.

The verifier caches one 80-step constant fixture and also publishes `engineering-review.json`
with all saved display arrays and explicit scope/units/source identity. This is an offline
browser-consumable payload, not a claim that the existing webpage already registers it.
It independently integrates static wet triangles (236.01507098278893 m3) and checks
each domain's dynamic ledger; constant initial storage remains 322 m3. Optional discrete
vertex-prism storage (224.5721879136545 m3 for the pair) has a third, separate meaning.

Once a variable archive is frozen, run the same verifier with
`--variable-storage <saved-variable.npz>`. It loads and validates the frozen record,
uses its exact saved forest identity, and composes it with the same-evaluation mosaic
and both drops. It never rebuilds or advances variable storage to manufacture a match.
The resulting aggregate NPZ and display JSON preserve both independent model histories.
