# Lake-river connector v1

## Scope and interface

This is an independent **engineering quasi-steady geometry** slice. It does
not modify the lake rating curve, inject discharge again, account additional
lake/river storage, simulate propagation, solve dynamic/backwater hydraulics,
or certify free-fall velocities. Tailwater at or above the actual spill is
rejected under the existing engineering contract. No external official text
was verified for this slice; no external method claim or weir formula is used.
The embedded joint remains `diagnostic_not_publishable`, even when the
connector geometry is feasible. Nothing is wired into default consumers.

`evaluate_lake_river_connector(source_joint, ConnectorCorridor, ConnectorRecipe)`
is explicit preparation. It preflights retained bytes, fully validates the
complete transfer-feasible source joint, then builds each committed positive-Q
step independently. Invalid or incomplete inputs raise `ValueError`; a
computable geometry failure returns a diagnostic with its retained prefix.
Zero discharge produces `closed_dry` with no water mesh. Q is exactly the
same implicit step-end lake outflow as the source step, never a new discharge.

`query_lake_river_connector(result, step_index)` only returns an immutable
prepared step. It performs no validation, preparation, recovery or generation.
`validate_lake_river_connector(result)` and default
`load_lake_river_connector(path)` perform a **static semantic audit** of saved
source, ledger, river acceptance proof, facets, splice, geometry and budgets.
They do not call upstream evaluators/recovery or the geometry constructor.
They still traverse saved arrays and can be costly: static validation is not
lazy loading. `replay_lake_river_connector(result)` or
`load_lake_river_connector(path, replay=True)` explicitly opts into full source
and connector algorithm replay. Static failure loading validates structure
and the actual saved successful prefix; it does not regenerate a failed step
or independently certify the failed reason. Use explicit replay for that.

## Source representation and wet attachment

Coordinates are `(x,z)` in metres; stored water vertices are `(x,z,water_m)`.
Corridor heights are nodal terrain on an explicitly declared regular metric
grid, with valid/domain/protected masks, datum and source identity. Each source
quad uses the fixed NW-SE diagonal, producing piecewise-linear triangular
facets. **This is not the old bilinear interpolation contract.** Source-river
H0 is still checked against the original bilinear prepared-source proof; the
connector attachment interprets its actual H2/water nodes using the declared
fixed-diagonal facet representation. No old consumer representation changes.
The lake's full-cell V(h) accounting is retained unchanged: facet rendering
does not imply that the lake solver resolved a subcell shoreline or slope.

The initial full-width cross-section must be supported entirely by actual
positive-depth lake wet node facets and match the actual lake bed and stage.
The final cross-section terminates exactly at the actual injection and matches
the actual river wet/H2/water facet line. Both lines are split at every source
grid edge and diagonal and checked at breakpoints and interval interiors.
The left/centre/right ribbon cross-section must equal the full source line,
not just three unrelated point samples. This establishes shared positive-depth
wet cross-sections, not proximity of endpoints. Every chosen source facet's
three vertices are checked, including zero-weight vertices: this is deliberately
more conservative than positive-weight sampling. No snapping across dry,
unknown, protected or out-of-domain support is permitted.

## Geometry, construction and gates

The bounded recipe supplies the path, per-vertex widths and an interior legal
spill vertex. It does not search for or invent an outlet. Lake-to-spill water
is at actual lake stage; the terrain-following lake bed may rise toward the
crest. Post-spill bed and water cannot rise downstream. The only implemented
geometry type is `terrain_following_excavated_water_ribbon`: connected indexed
water triangles and a corresponding bed mesh, not a centreline. Explicit drop
geometry is not implemented and is not claimed.

Bed construction samples the real corridor source. After spill it subtracts
a linear station-distance taper of the **actual current step's river terminal
cut**. It never linearly interpolates a fictional bed between lake and river.
This bounded engineering construction can fail; it is not a hydraulic solver.
Terminal water/bed values are assigned directly from actual current-step river
nodes/facets. The same source path is evaluated separately for each Q.

Every ribbon triangle is clipped against all intersected actual source facets.
Linear extrema at every clipped polygon vertex bound depth, clearance, cut and
bed raising. Positive cut is clipped again at zero; volume integrates the
linear positive function exactly and changed area is its actual positive
support, not a whole-triangle approximation. Floating-point certification uses
1e-9 metre/integral comparison tolerance, not a relaxed physical budget.
Width must resolve at least two corridor intervals. Longitudinal spacing,
stations, triangles, source tests, self-intersections, expanded ZIP payload,
metadata and retained bytes are bounded. No failed budget is expanded.
Triangle orientation and overlapping interiors reject folded/crossing ribbons.

Static audits use the same input, resolution, ribbon, splice and triangle gates.
They also bind joint physical recipes, masks, actual outlet stages and bounded
recovery calls to their saved recovery inputs, apply the existing static river
acceptance proof, recompute lake V(h)/Q(stage) and source conservation using
original tolerances, and recompute aggregate source ledger summaries. Rehashing
geometry, Q, source H0, budgets, masks, stages, identities, metadata or summaries
alone cannot establish semantic acceptance. Hashes are not issuer signatures;
coherently replacing an entire valid source scenario is a different input.

## Persistence and verification

All returned nested mappings/sequences and arrays are immutable. Array storage
is backed by immutable bytes: writeability cannot be re-enabled. Bundles embed
the source joint, corridor input, recipe, actual geometry, attachments and step
ledger/identity proofs. ZIP member names, duplicates, encryption/compression,
expanded size and NPY shape/dtype/payload length are checked before allocation.
Saving validates statically, fsyncs a temporary file and hard-links to the final
name without overwrite; only the winning writer publishes, and each writer
cleans its own temporary. No old sample or terrain data is overwritten.

Run with the existing Python and dependencies only:

```
D:/anaconda/python.exe -X utf8 -m unittest tests.test_lake_river_connector -v
D:/anaconda/python.exe -X utf8 tools/verify_lake_river_connector.py
```

The fixed verifier writes a unique UTC directory under
`verification/lake-river-connector/run-<UTC>/`, test log, self-contained bundles
and `report.json` with source-file/bundle hashes and geometry summaries.
Two positive-flow scenarios use a **new independent common-source engineering
sample**. Original `joint_case` inputs and archived results are unchanged.
The overlapping lake/downstream coarse H0 nodes agree; the refined explicit
corridor is derived from that common source, and actual whole-width lake/H0
attachments are proven rather than inferred from source names. The path starts
at `(-2.2,1)`, passes actual spill `(-1,1)`, and ends at injection `(0,1)`.
The 0.04-metre width on a 0.02-metre corridor is deliberately small: wider
cross-sections hitting real river dry support remain failures. Default inflows
are `(2,2)` m3/s, giving actual Q approximately `(0.2,0.38)` m3/s, **not** the
old 0.58 m3/s sample. Each step has 333 vertices, 440 triangles and projected
area 0.088 m2. Stronger inflow is not substituted to hide a failed cut budget.

Fixed failures include high-tailwater source rejection, shore ridge, unknown,
protection/domain, unresolved width/spacing, dry full-width splice, cut depth,
volume/area and station/triangle/support/retained resources. Rehashed geometry,
summary, Q and source proof failures remain explicit. Successful synthetic
geometry does not certify natural terrain, the unresolved real-domain unknowns,
free-fall/drop behavior, bidirectional feedback, game/Java water consumption or
full-system publication. Final counts and the exact UTC directory are in the
generated report, not accumulated across intermediate test runs.
