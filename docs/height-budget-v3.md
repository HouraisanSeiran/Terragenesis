# Geographic v3 height budget

`geographic_v3` is a versioned Terrain Diffusion conditioning profile for the
1 metre per Minecraft block consumer. It reduces positive geographic elevation
conditions to 18% of the v2 values and uses that reduced elevation for the
temperature lapse calculation and precipitation. The elevation conditioning SNR
is 0.1. The model still determines the generated terrain; condition height alone
does not guarantee output height. v2 files and their generation identity remain
unchanged.

The target is a generated and processed maximum Minecraft Y of 800 or lower.
There is no minimum mountain peak. Minecraft sea level stays Y=62 and the core
sea level defaults to 126 metres. The mapping is `Y = elevation_m - core_sea_m + 62`.
No per-region normalization, post-generation vertical scale, or clipping is used.

Generate real, immutable 513 by 513 samples at the pinned test locations:

```powershell
runtime/venv/Scripts/python.exe tools/probe_tuned_terrain.py --profile geographic_v3 --seed 20260927 --x -16000 --z -13952 --size 513 --label height-budget-plateau
runtime/venv/Scripts/python.exe tools/probe_tuned_terrain.py --profile geographic_v3 --seed 20260928 --x 384 --z 15488 --size 513 --label height-budget-highland
```

The probe refuses to overwrite an existing source. Then prepare and validate both
with `runtime/venv/Scripts/python.exe tools/prepare_height_budget_samples.py`.
Each run gets a new directory under `verification/height-budget-v3/`, publishes
base and derived metric artifacts, exports Minecraft read-only snapshots and
records raw and processed height maxima, source hashes, identities and top margin.
Raw and processed maxima must both satisfy Y<=800. The fixed-sample check and
the formal exporter share the same Minecraft publication check, which also
enforces the bottom and 1024 build-height bounds. Run results do not alter the
old v2 samples.

The current checked run is
`verification/height-budget-v3/run-20260929T091944094519Z/report.json`.
Its plateau maximum is Y763.09 after processing; the highland maximum is Y716.51.
These are two local samples, not a guarantee for all seeds or a complete world.
