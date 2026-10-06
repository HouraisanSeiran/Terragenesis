# Large Surface Network Benchmark

This is an independent 1024x1024+ static and one-step benchmark. It does not alter the frozen 256x256 regional solver or claim a long hydraulic run.

## Contract

- Input is a raw finite float32/float64 Terrain Diffusion height `.npy` or single-array `.npz` (`elevation_m` only), square and at least 1024x1024. Filled surfaces, regional 256 source bundles, cut geometry, or ambiguous multi-array packages are rejected.
- The default tile is 256x256 cells. Every cell has one deterministic `tile_id`; N/W/E/S strict-downhill D4 selection uses a fixed tie order. Boundary/local terminals have `receiver=-1` and are called outlets for this diagnostic only, never natural outlets.
- `receiver_tile_id` and `crossing_donor` explicitly audit cross-tile ownership. `shared_tile_edges` records physical neighboring tiles. No tile may silently drop a receiver crossing.
- The one-step benchmark partitions uniform input volume by tile for 900 seconds. It is a storage/accounting probe, not momentum, Manning, channel-cross-section, or 72-hour routing.

## Resource declaration

Default bounds are 16,777,216 cells, 256 tiles, and 256 MiB intended resident working memory. The output stores static arrays for reproducibility; a production dynamic solver must use mmap/tile working sets rather than assembling all depth/Q history. No GPU or new dependency is used.

The output is an independent UTC directory containing `static-arrays.npz`, `one-step-arrays.npz`, and `manifest.json` with source hash, tile ownership, outlet/crossing counts, and audit results.
