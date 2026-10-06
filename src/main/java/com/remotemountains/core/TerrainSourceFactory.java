package com.remotemountains.core;

import com.remotemountains.diffusion.TerrainSources;
import com.remotemountains.prepared.PreparedTerrainSource;
import com.remotemountains.prepared.PreparedVdmSource;
import com.remotemountains.region.DerivedRegionTerrainSource;
import com.remotemountains.region.MetricProcessedTerrainSource;
import com.remotemountains.region.RawRegionTerrainSource;
import com.remotemountains.region.RegionRuntime;
import com.remotemountains.region.RegionTerrainSource;
import com.remotemountains.vdm.GeneratedVdmSource;

/** Resolves persisted source modes to their existing terrain pipelines. */
final class TerrainSourceFactory {
    private static final String RAW_SCALE_ID = "raw_model_sea62_1024_v1";
    private static final String TALL_SCALE_ID = "relief_3x_sea62_1024_v1";

    private TerrainSourceFactory() {
    }

    static BaseTerrainSource create(long seed, String identity, String recipe, String sourceMode,
            TerrainScale scale, int regionChunks, String regionProcessing) {
        TerrainModeRegistry.requireValid(sourceMode, recipe, scale.id());
        if (sourceMode.equals("metric_processed_readonly_v1")) {
            String file = System.getProperty("remotemountains.metricSnapshot");
            if (file == null || file.isBlank()) {
                throw new IllegalStateException("Set remotemountains.metricSnapshot to a prepared metric export");
            }
            return new MetricProcessedTerrainSource(java.nio.file.Path.of(file), seed, identity);
        }
        if (sourceMode.equals("region_diffusion_processed_v1")) {
            if (!scale.equals(TerrainScale.RAW_MODEL) || !recipe.equals(DerivedRegionTerrainSource.RECIPE)) {
                throw new IllegalArgumentException("Processed region requires its matching recipe and scale");
            }
            return RegionRuntime.createProcessed(seed, identity, recipe,
                RAW_SCALE_ID, regionChunks, regionProcessing);
        }
        if (sourceMode.equals("region_diffusion_raw_v1") || sourceMode.equals("region_diffusion_tuned_v1")) {
            String expected = sourceMode.equals("region_diffusion_tuned_v1")
                ? RawRegionTerrainSource.TUNED_RECIPE : RawRegionTerrainSource.RECIPE;
            if (!scale.equals(TerrainScale.RAW_MODEL) || !recipe.equals(expected)) {
                throw new IllegalArgumentException("Raw model source requires its matching recipe and scale");
            }
            return RegionRuntime.createRaw(seed, identity, recipe,
                RAW_SCALE_ID, regionChunks, regionProcessing);
        }
        if (sourceMode.equals("region_diffusion_v1") || sourceMode.equals("region_demo_v1")) {
            return RegionRuntime.create(seed, identity, recipe,
                scale == TerrainScale.TALL ? TALL_SCALE_ID : "legacy",
                regionChunks, regionProcessing, sourceMode);
        }
        BaseTerrainSource base = TerrainSources.create(seed, identity, sourceMode);
        if (base instanceof PreparedTerrainSource prepared) {
            if (!PreparedVdmSource.RECIPE.equals(recipe)) {
                throw new IllegalArgumentException("Prepared source requires prepared VDM recipe");
            }
            return new PreparedVdmSource(prepared, scale);
        }
        return new GeneratedVdmSource(base, seed, recipe, scale);
    }

    static String recipeOf(BaseTerrainSource source) {
        if (source instanceof RegionTerrainSource region) {
            return region.recipe();
        }
        if (source instanceof RawRegionTerrainSource raw) {
            return raw.recipe();
        }
        if (source instanceof DerivedRegionTerrainSource derived) {
            return derived.recipe();
        }
        if (source instanceof MetricProcessedTerrainSource metric) {
            return metric.recipe();
        }
        if (source instanceof GeneratedVdmSource generated) {
            return generated.recipe();
        }
        if (source instanceof PreparedVdmSource prepared) {
            return prepared.recipe();
        }
        return "prototype";
    }
}
