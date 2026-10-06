# Mountain rainfall demonstration v1

## Purpose and scope

The mainline target is reality-like **Terrain Diffusion generated mountains**,
not a requirement that every generated basin be a measured real-world basin.
Core development uses physical metres, square metres and seconds independently
of Minecraft ceiling/sea-64 import presets. This CPU-only, offline demonstration
does not change the Sonnet frontend, start a model service, install dependencies,
prepare channel beds or certify Minecraft connectivity.

Run `python tools/verify_mountain_rainfall.py` from the repository root. Only the
new verification is run, not the historical large acceptance suites. Review the
self-contained `review.html` and `report.json` in the printed new
`verification/mountain-rainfall/run-...` directory; images are embedded without
external network dependencies.

## Exact source constraints

The pinned sources are `normal_mountain.npz` and `pressure_mountain.npz` under
`verification/metric-rivers/run-20260929T110135621570Z`. Their provenance sidecars
pin the original TD archives in
`verification/height-budget-v5/run-20260929T103819083596Z/screen-3/`:
`seed20260931-x11520-z15360.npz` and `seed20260931-x0-z0.npz`.
The verifier checks these hashes if the originals exist and records the original
generation configuration. The legacy backend returns upstream `output['elev']`
directly; nevertheless its `geographic_v5` conditioning historically used
`v5_base_knee_m=120` and `v5_base_headroom_m=120`, a soft-knee compressed positive
base, with base/relief factors 0.18. These saved elevations are not evidence of
new unconstrained generation. Undoing that conditioning cannot be justified by
inverting the final terrain values.

For graph compatibility this demonstration deliberately uses complete saved
`input_height` (487 x 487, 30 m spacing), not the river-incised `processed_height`.
The original 513 x 513 TD elevations had already been shifted by +126 m,
processed with `METRIC_30M_RECIPE_V1`, and cropped by a 13-cell halo. Subtracting
126 m here establishes sea-zero coordinates without changing relief, squeezing
the new simulation, or recovering raw generation. Horizontal origins remain
exactly those in provenance. Full height, receiver, legacy planned flowline and
outlet masks are retained. The saved lowest-edge outlet is **artificial**, not a
natural mouth; the previous bed/water geometry had unresolved cells.

## Physical aggregation and dynamics

Land cells above shifted sea zero are assigned to up to 64 equal-height response
bands. Empty bands are omitted. Every cell has an explicit owner (`-1` for
non-land); HRU area is its exact land-cell count times 900 m2. This is a physical
hillslope response grouping, not a claim that disjoint elevation bands are
connected drainage catchments. Full owner maps, band limits/means, areas, source
coordinates and hashes accompany compact time-dependent HRU arrays. No giant
time-by-cell soil/reservoir histories are allocated.

The same deterministic, elevation-modulated storm is applied to dry and wet soil:
hours 6-9 at 4 mm/h, 9-12 at 24 mm/h, 12-18 at 8 mm/h, then rain-free recession
through hour 336 (14 days). A third case supplies spatially uniform steady
3 mm/h rain through hour 24 before recession. Storm elevation multipliers range
from 0.8 to 1.2 and are synthetic scenario forcing, not verified orographic physics
or climate calibration. Each 900-second interval advances persistent soil and
fast/slow reservoirs through the dedicated rainfall-runoff API.

`local_q_m3_s` is delayed runoff delivered by each HRU. Selected snapshots distribute
it by cell area and sum downstream on the original acyclic receiver graph.
These accumulated values are **instantaneous spatial sums, not routed channel
hydrographs**: there is no river travel time, flood wave or channel storage model.
Only a few full-grid diagnostics are retained. A legacy planned river overlay is
shown over the original mountains, not a new geomorphic preparation claim.

## Evidence and limitations

Dry soil begins at 15 mm and wet soil at 135 mm; all other runoff parameters
retain the API defaults. Persistent soil percolation may continue recharging the
slow reservoir: 48-to-96-hour outflow can rise despite no rain. The verifier
reports those values honestly and checks declining late recession from hour
168 to hour 336 rather than assuming immediate monotonic rain-free decay.

The independent budget uses saved rainfall intensity times HRU area and interval
seconds, actual ET, integrated local outflow, and initial/final soil plus both
reservoir states: rainfall = ET + outflow + delta storage. Initial wet-soil water
is accounted as initial storage, not rainfall. Reopening new NPZ artifacts
recomputes this balance independently of the solver's reported residual. Source
archives and provenance sidecars are checked against fixed code-pinned hashes
and rehashed after verification. Each case also saves the native rainfall-runoff
NPZ; its reload is tested with simulation patched to fail, so loading never rains
or advances time. The separate mountain NPZ schema `mountain-rainfall-demo-v1`
retains native mm states alongside volume states, actual ET, local rates, solver
ledger, exact full-grid owner/graph/masks, source coordinates, HRU band limits,
snapshot indices and explicitly labeled spatial diagnostic rates. The source
identity binds fixed river/raw/provenance hashes, datum and aggregation recipe;
native metadata binds forcing, parameters and states. This standalone HTML is
not connected to the old Sonnet runtime.

The report binds SHA-256 of this verifier, its focused tests and this document,
plus the rainfall-runoff core and core tests. If any implementation changes
during verification, the run is rejected. Original runs are preserved; final
evidence must be generated after the collaborating core implementation freezes.
Saved native mm states independently reconstruct volume storage and are checked
against the duplicate saved volume states. Per-HRU interval budget tolerances
use 1e-7 m3 absolute plus 1e-10 times that interval's rain, ET, outflow, storage
change and available storage; the cumulative budget is checked separately.

The review plots show area-weighted rainfall, local runoff, soil and reservoir
storage, and rain-free recession. Conservation and a visible wet/dry response
are acceptance for this scoped demonstration only. They do not establish
observational calibration, natural river mouths, unconstrained TD generation,
channel hydraulics, natural terrain conditioning or full terrain preparation.
