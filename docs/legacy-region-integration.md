# Existing region results: portable surface pair

`terrain_pipeline.legacy_region.prepare_legacy_region(source_path, processed_path, destination)`
explicitly imports one existing Terrain Diffusion NPZ and its matching
`regional_landforms_v1` region-processing NPZ. It validates their saved mapping,
25-sample halo, matching float32 processor input, origin, shape, and recipe.
It does not run either generator. The destination must be a new directory.

The published directory contains `base/` and `derived/` terrain artifact v1
packages plus a pair manifest. Publication happens after both packages reload
and verify their source binding. The base grid keeps exact model elevation
samples after halo removal, in metres relative to the model sea-level datum.
The derived grid stores the legacy processed height as vertical displacement
from that reference. Its identity records the processed NPZ checksum and recipe.
The original model NPZ checksum and generation configuration belong to the
base identity. Legacy game mapping values are conversion provenance; they do
not define the portable grid units. No water is supplied by these archives,
so both packages leave water absent.

`terrain_pipeline.legacy_region.load_legacy_region(path)` reads an existing
pair only. It validates both packages, their manifest IDs, common reference
surface, and source relationship. It requires neither legacy NPZ nor model
runtime. The returned `LegacyRegion.reconstructed_elevation_m()` gives a
separate array of processed elevations in metres.

Run `D:/anaconda/python.exe -X utf8 tools/verify_legacy_region.py` for the
fixed gate. It checks the 50 protected source hashes, runs the integration
tests, and publishes a real pair plus `report.json` under a new run directory
in `verification/legacy-region-integration/`. This verifies an existing
surface-data integration only; it does not validate water, material, cave
topology, region seams, naturalness, or an external software consumer.
