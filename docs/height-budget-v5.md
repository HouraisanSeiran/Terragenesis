# Geographic v5 soft-knee input experiment

`geographic_v5` is a separate, immutable Terrain Diffusion conditioning
identity. The raw positive land base is `b = max(shore, 0) * 3600 * 0.18`
metres. For knee `k` and headroom `h`, the conditioned base is
`min(b, k) + h * (1 - exp(-max(b-k, 0)/h))`. It preserves the base below the
knee and smoothly approaches `k+h` above it. The mountain relief remains a
separate `0.18 * relief` term, and offshore depth approaches 40 m smoothly.
Temperature and precipitation conditioning use the resulting elevation.
This is input conditioning only; the model output is never scaled or clipped.

The fixed experiment compares `k=120 m` with `h=40/80/120 m`, elevation SNR
0.1, on two known mountain windows and one deep-ocean window. It records the
full raw model grid, the processed interior after the 13-sample halo, 30 m
physical slope, height bounds, source hashes and model identity. Input
condition ranges are diagnostic probes in the upstream coarse coordinate
system; actual model tiles may sample additional halo cells. The selected
candidate is then tested at four fixed locations under new seed 20261004.
The relief-distance ranking is not an assessment of naturalness.

The checked run is
`verification/height-budget-v5/run-20260929T103819083596Z/summary.json`.
All three candidates failed the known high window: full raw peaks were
Y863.02, Y887.08 and Y911.90 for headrooms 40/80/120 m. At the normal mountain
window, processed interior relief p95-p5 was 79.72/91.98/102.32 m, compared
with 145.94 m for the v3 processed interior. The deep-ocean window passed all
three. The predetermined morphology ranking selected `h=120 m` for research
holdout; it was not the best candidate for the height limit. Its four new-seed
windows passed height checks. The screen failure keeps the height gate closed;
no terrain package, Minecraft snapshot or river network was published.
The condition probe covers the native window's coarse coordinates, not every
conditioning cell read through model tile halos. Input compression is not an
output guarantee, so these results do not show that the model violated a hard
height constraint.
