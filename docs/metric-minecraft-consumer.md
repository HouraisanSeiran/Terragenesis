# Metric processed surface: Minecraft consumer v1

The `processed` selector now resolves `metric_processed_readonly_v1` with recipe
`metric-processed-surface-v1` and scale `metric_1m_sea62_1024_v1`. Existing
`region_diffusion_processed_v1` world records still resolve their legacy reader.

The authoritative terrain is a published Python metric region package. After
offline preparation, run:

```
D:/anaconda/python.exe -X utf8 tools/export_metric_minecraft.py REGION_DIR SNAPSHOT.tgmc
```

Set Java property `remotemountains.metricSnapshot` to the snapshot path before
opening a world. The snapshot pins its source derived content ID, full payload
identity, seed, datum, complete grid, 64-block-aligned finite bounds and checksum.
Set the saved world `diffusion_identity` to the snapshot identity when moving or
restoring a world; a wrong identity or missing file fails before sampling. The
property is an explicit local path and is never used to launch Python or a model.

The adapter maps each axis at 1 metre per block and maps elevation by
`Minecraft Y = core elevation metres - core sea level metres + 62`. The core
sea level defaults to 126 metres in the prepared package and may differ by
package. The Minecraft sea level remains Y=62. Every reconstructed surface
sample must be at or below Y=800 for publication, including peaks outside
the playable interior. Lower mountains are allowed. The exporter also retains
the Minecraft bottom and build-height checks. It rejects an out-of-range
surface before creating the snapshot; it does not scale or clip elevations. The
consumer accepts vertical surface displacement only. Water, cave topology,
materials and climate are absent from this metric region version; no water or
cave is generated. Minecraft's fixed `temperate` biome variant and basic block
palette are explicit adapter policy, not source climate or geology. Landform
labels 0-3 are used only to select one of the four existing biome palette rows
(plain->inselberg, hill->rift, plateau->karst, mountain->pillars); these names
are compatibility palette slots, not claims about geological type.

The finite bounds are half-open and aligned to 64-block tile edges. Sampling,
biome lookup or chunk preparation beyond them fails. This snapshot covers one
contiguous grid; joining multiple storage chunks and richer consumer data need
a later format version. The Java reader verifies the whole file when created;
mutating the snapshot while a world is open is unsupported.

The earlier plains snapshot at `verification/metric-region-v1/minecraft-plains.tgmc`
is a legacy test fixture whose Y951 peak now exceeds the Y800 publication limit.
The older v2 plateau and highland samples exceed Minecraft build height and are
rejected. The separately generated v3 plateau and highland samples pass the
Y800 publication check; see
`docs/height-budget-v3.md`.
