# Rainfall-runoff v1

Independent-cell illustrative hydrology, not calibrated rainfall prediction, river
routing, terrain generation, erosion, or Minecraft acceptance. Original terrain
and rain inputs are never modified. No frontend or default-world integration.

## API

```python
from terrain_pipeline.rainfall_runoff import (
    RunoffParameters, simulate_rainfall_runoff,
    validate_rainfall_runoff_result,
    save_rainfall_runoff_npz, load_rainfall_runoff_npz,
)

result = simulate_rainfall_runoff(
    rain_mm_h, area_m2, dt_s=900.0, source_id="saved-terrain-artifact-id",
    parameters=RunoffParameters(initial_soil_mm=10.0),
)
save_rainfall_runoff_npz("new-runoff.npz", result)
loaded = load_rainfall_runoff_npz("new-runoff.npz")
report = validate_rainfall_runoff_result(loaded)
```

Signature: `simulate_rainfall_runoff(rain_mm_h, area_m2, *, dt_s,
source_id, parameters=None) -> dict`.
Inputs must be numeric ndarrays: rain `[T,N]` in mm/hour, area `[N]` in
square metres; physical timestep in seconds. Rain is constant within each step.
All values must be finite; rain is nonnegative and area/dt strictly positive.
Complex, object, boolean arrays and boolean scalars are rejected.
Source identity is a required nonblank string, at most 4096 characters.
Cell order is exactly the input column order; no axes or coordinates are inferred.
Use source_id to identify the saved terrain, its flattening/HRU map, and storm.

### Parameters

Frozen `RunoffParameters`, spatially uniform, with illustrative defaults:

| Field | Default | Unit |
| --- | ---: | --- |
| infiltration_capacity_mm_h | 15 | mm/hour |
| soil_capacity_mm | 150 | mm |
| potential_et_mm_h | 0.15 | mm/hour |
| percolation_mm_h | 1 | mm/hour |
| fast_tau_s | 3600 | seconds |
| slow_tau_s | 259200 | seconds |
| initial_soil_mm | 30 | mm |
| initial_fast_mm | 0 | mm |
| initial_slow_mm | 0 | mm |

Initial storage is explicit in parameters and saved at state index zero.
For dry/wet antecedent experiments use soil 10 versus 142.5 mm (95% capacity).
Initial soil cannot exceed capacity; no hidden spin-up. All initial depths apply
to every cell. Rates/capacities/depths are nonnegative and <= 1e6; reservoir
times are positive and <= 1e12 seconds. These are safety bounds, not physics.

## Step ordering and conservation

1. Compute rain depth `P = rain_mm_h * dt_s / 3600`.
2. Infiltrate `I = min(P, infiltration_capacity_mm_h * dt_s / 3600,
   soil_capacity_mm - soil_before)`. All `P-I` enters the fast reservoir.
3. From soil plus infiltration, remove actual ET limited by available soil
   and potential ET depth. Rain is available to ET within this step.
4. From remaining soil, percolate at the specified rate, limited by availability.
   All percolation enters the slow reservoir. Soil never becomes negative.
5. Release each reservoir with the exact solution for a constant within-step
   incoming rate: for incoming depth `U`, old depth `S`, and `x=dt/tau`,
   `R = S*(1-exp(-x)) + U*(1-(1-exp(-x))/x)`, `S_next=S+U-R`.
   `expm1` and a small-x series avoid subtractive cancellation. New rain is
   not instantaneously sent to the river; fast/slow storage delays release.
6. Convert released depth to volume with `area_m2/1000`; divide by `dt_s`
   for timestep-average `local_q_m3_s`. No river routing or intercell transfer.

Every cell/step obeys `rain_volume - et_volume - outflow_volume -
storage_change = balance_residual`. Infiltration and percolation are internal
transfers, not losses. No saturation clamp discards mass. Dry steps may have
baseflow from explicit antecedent storage. ET has priority over percolation.
Soil splitting is ordered, not an exact coupled ODE solution: when saturation
occurs, smaller timesteps allow repeated infiltration after drainage and results
converge with refinement. Reservoir integration alone is exact for constant input.

Percolation is a constant-rate, availability-limited illustrative bucket flux,
not a calibrated soil-moisture-proportional drainage model. Rain-free does not
imply immediately declining discharge: wet antecedent soil can continue recharging
the slow reservoir, so 96-hour discharge may exceed 48-hour discharge. Use a
14-day dry extension to observe soil depletion and subsequent exponential
baseflow recession. With zero soil/percolation and only initial reservoir storage,
rain-free recession is exponential from the first step.

## Returned arrays and identity

- `[T+1,N]`: `soil_mm`, `fast_mm`, `slow_mm`; index 0 is initial state,
  index t+1 is end-of-step t. Depths in mm, not water levels or river stage.
- `[N]`: `area_m2`.
- `[T,N]`: `rain_mm_h`, `local_q_m3_s`, `infiltration_mm`, `actual_et_mm`,
  `percolation_mm`, `excess_mm`, `fast_release_mm`, `slow_release_mm`.
- `[T,N]` cubic-metre ledger: `rain_volume_m3`, `et_volume_m3`,
  `outflow_volume_m3`, `storage_change_m3`, `balance_residual_m3`.
  Storage change and numerical residual can be signed.
- `metadata`: algorithm `rainfall-runoff-v1`, schema `rainfall-runoff-npz-v1`,
  source_id, dt_s, complete parameters, canonical parameter SHA-256,
  cell-order statement and discharge semantics. All arrays are independent of inputs.

Static validation returns `{"valid": True, "max_abs_balance_residual_m3": ...}`
or raises ValueError. It recomputes component storage changes, rain partition,
ordered soil flux limits, analytical fast/slow releases, ledger and discharge conversion from saved arrays,
not by rerunning the solver. Ledger comparisons use atol 1e-8 and rtol 1e-10;
the zero-balance check scales with the absolute physical fluxes. This checks
accounting, not geological realism or authentication of a claimed source.

## Resource and persistence contract

Before allocating simulation outputs: T <= 100000, N <= 100000,
T*N <= 1000000, conservative workspace estimate
`24*8*(T+1)*N <= 256 MiB`. dt_s is between 1e-6 and 1e7 seconds;
area <= 1e12 m2 and rain <= 1e6 mm/hour. Oversized workloads must use HRUs or
explicit caller batching. For example, 32 HRUs whose areas sum to 213452100 m2
fit much longer storms than 237169 land cells; the latter exceed the per-call
cell bound. The caller must retain the HRU-to-land-cell map; this module does
not infer one or redistribute local discharge. Discharge sums scale with area.

Archives contain numeric NPY arrays and a uint8 UTF-8 JSON manifest, never
pickled objects. SHA-256 covers each array's shape/dtype/bytes and canonical
metadata. Load inspects exact ZIP member names, total uncompressed bytes,
bounded NPY headers, dtypes and declared byte sizes before loading arrays;
then verifies hashes/schema and statically validates balances. Hashes detect
accidental or unrehashed tampering, not malicious rewriting of all hashes.
Global rain/state/flux shapes and the simulation resource budget are checked
before np.load allocates arrays. JSON duplicate keys and nonfinite constants
are rejected; metadata keys, complete parameter keys, q_semantics and cell_order
must match the v1 contract exactly. Conservative but constitutively invalid
rehash counterfeits are rejected by static flux/release checks.

Save validates first, writes/fsyncs a temporary file in the destination directory,
then publishes with a no-replace atomic hard link, cleaning up the temporary
file even on failure. An existing destination (including a publication race)
is never overwritten. Destination directory must already exist; filesystems
without hard-link support fail safely rather than fall back to overwrite-prone
publication. No sidecar files. No changes to frozen artifacts.

## Focused verification

`python -m unittest discover -s tests -p test_rainfall_runoff.py -v`

Covers dry and rain analytic volumes, antecedent saturation, availability-limited
ET/percolation, delayed recession, area scaling, exact reservoir subdivision,
soil timestep convergence, small-dt cancellation, determinism, input isolation,
invalid inputs and preallocation budgets, static saved-ledger corruption,
archive roundtrip/hash tampering/pickle rejection, no-overwrite and cleanup.
