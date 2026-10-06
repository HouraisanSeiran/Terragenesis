# Legacy Java algorithm inventory

Inventory based on source and call-site search on 2026-09-30. Java sources remain in place; this is a review record, not a migration.

| Java algorithm/package | Current callers | Python counterpart | Migration status |
| --- | --- | --- | --- |
| `region.processing.RegionProcessor` (plus `SurfaceProtection`, `ProcessingConfig`) | `DerivedRegionArtifact`, `DerivedRegionTerrainSource`, `RegionProcessorVerification`, Gradle `verifyRegionProcessor` | `terrain_pipeline/metric_region.py`, `terrain_pipeline/metric_region_storage.py` | First-stage metric processor migrated and verified; Java still compiles and serves runtime compatibility paths. |
| `region.RawRegionTerrainSource` / `DerivedRegionTerrainSource` and artifact readers | `TerrainSourceFactory`, `TerrainModeRegistry`, `RegionRuntime`, `Terrain`, verification classes | `terrain_pipeline/legacy_region.py` (read-only import/package), `terrain_pipeline/artifacts/` | Explicit Python legacy import exists; Java region sources remain active consumers and are not removed. |
| `watershed.DrainageGraph`, `WatershedTerrainSource`, `RiverProfile` | `watershedcliff`, canyon modifiers, watershed verification/preview | `terrain_pipeline/surface_rivers/` and metric channel modules | Not migrated as a drop-in full-domain graph. Java watershed is a fixed demonstration; Python surface river pipeline is the replacement diagnostic path. |
| `vdm.VdmVoxelizer`, `VdmTerrainSource`, `GeneratedVdmSource` | `RegionTerrainSource`, prepared sources, terrain/core verifications | No accepted Python VDM replacement; channel/height diagnostics are separate | Unmigrated; retain Java implementation and mark future scope. |
| `canyon.*`, `cliff.*`, `watershedcliff.*` modifiers | `Terrain`/world verification and watershed sources | No accepted Python equivalent | Unmigrated feature-specific shaping; not part of the metric RegionProcessor cutover. |
| `world.RemoteGenerator` and model-backed sources | Runtime/world integration and verification | No Python runtime/game consumer | Unmigrated integration; outside offline diagnostic scope. |

## River task consistency

2026-09-30 review correction: task 22 has been reopened. Its budget allocations and caller-supplied recovery flags are diagnostics, not implemented valley geometry, rerouting, or lake balance. Surface preparation task 24 is under active review; this inventory does not certify river completion. Java archival remains pending removal of active legacy callers.

Tasks 17, 21, and 22 agree with the current code and reports: diagnostics, static stage/inundation/joint checks, and valley budget/recovery planning are complete slices, while a real complete domain with natural outlets, actual rerouting, lake balance, and publishable river output remains open. The next mainline slice is selecting a measured full hydrologic domain with two tributaries and legal natural outlets, then implementing and validating constrained rerouting/bed adjustment inside that domain. Lake handling should follow only after outlet/domain feasibility is demonstrated.

Evidence: `.scratch/terrain-framework/issues/17-river-feasibility-diagnostics.md`, `.scratch/terrain-framework/issues/21-stage-bank-joint.md`, `.scratch/terrain-framework/issues/22-valley-budget-recovery.md`, `.scratch/terrain-framework/river-feasibility-review.md`, `.scratch/terrain-framework/channel-joint-review.md`, and `.scratch/terrain-framework/valley-budget-review.md`.
