# Metric regional landform processing

For 30-metre real-source grids, `METRIC_30M_RECIPE_V1` is the frozen processing
recipe: trend 120/360 m, local 60/180 m, and coast 90/270 m sigma/radius.
The legacy numeric metre defaults remain available for smaller sampled grids.
Run `tools/verify_metric_recipe_gate.py` to recompute literal, moderate and
selected recipes from three immutable real inputs. The measured engineering
regression budget
requires <=16 m local and extrema changes, zero movement within 1 m of the
sea line when coast cells are present, 0.1%-5% plains grid roughness reduction
and <=0.1 m mean highland/plateau disturbance. No coast cells occur in these
three real samples, so this coast gate is not applicable there; a separate
synthetic test checks protection. The selected recipe reduces plains roughness
by 1.86%, against 2.19% for moderate, while disturbing the highland less
(0.026 m versus 0.037 m mean); it offers a more conservative response across
these samples while keeping other budgets. Report and hashes are in
`verification/metric-region-v1/final-recipe-gate.json`. This is an
algorithm acceptance gate; it does not claim hydrology or Minecraft visual
quality. The consumer export and limits are in `docs/metric-minecraft-consumer.md`.

`terrain_pipeline.metric_region.process_region` accepts a finite `[z,x]` grid in
core metres, a named sea-level elevation, and independent X/Z sample spacings in
metres. It computes trend, local relief, slope in m/m, coastal proximity, four
continuous landform weights (plain, hill, plateau, mountain), protection, and a
separate smoothed surface. Height thresholds are relative to sea level. Filter
sigma and radius are physical metres; the kernel samples only points within its
declared radius. No Minecraft coordinate or block-height scaling enters the
processor.

`RegionRecipe()` retains the old numeric thresholds as metre starting values.
At 30 m input resolution, its 2-24 m filters cannot resolve the terrain.
`prepare_metric_region` selects `METRIC_30M_RECIPE_V1` by default only when
both spacings are exactly 30 m; callers can pass an explicit recipe at any
spacing. The frozen recipe is an engineering preset for the measured inputs,
not a general naturalness claim. Historical `resolvable_30m_candidate`
packages remain experimental evidence; the current verifier writes the
named `metric_30m_v1` candidate.

`prepare_metric_region(base, destination, protection_mask=None, recipe=...)`
requires a dry base artifact, computes with the required halo, crops its valid
interior, and publishes an immutable base/derived pair plus landform weights and
labels. It verifies the temporary package before publishing and refuses to
overwrite. The cropped base identity records the full input content identity,
original algorithm identity, original grid, and halo. The derived identity
records all recipe parameters and the optional protection-mask SHA-256. The
published package stores no mask; callers must keep the planning constraint
separately if they need to inspect it later.

`load_metric_region(path)` validates contents and source binding without running
processing. The derived displacement is vertical XYZ: `dx=dz=0`, `dy` is the
processed minus base surface. Landform labels are sidecar data because the v1
surface artifact has no categorical material field. Water-bearing base surfaces
are rejected until water reconciliation is designed; the processor does not
generate river paths or cave topology.

`rebase_base_surface(base, target_sea_level_m)` shifts the reference heights and
sea level together. The default core bottom is 0 m with sea level 126 m; a
Minecraft consumer maps `Y = core_elevation_m - core_sea_level_m + 62` and
uses 1 m per block. The fixed game sea level is therefore Y=62, while the core
sea-level datum can change without changing relative relief.

Run `D:/anaconda/python.exe -X utf8 tools/verify_metric_region.py` for the
fixed CPU-only tests, three real-sample statistics, and plains comparison image
in a new `verification/metric-region-v1/run-*/` directory. The input is Terrain
Diffusion data at 30 m spacing; this gate does not validate Minecraft rendering
or visual naturalness.
