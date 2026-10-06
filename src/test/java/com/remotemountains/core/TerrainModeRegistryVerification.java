package com.remotemountains.core;

/** Contract checks for selectable modes and invalid persisted combinations. */
public final class TerrainModeRegistryVerification {
    public static void main(String[] args) {
        String[] keys = {"processed", "raw", "raw_legacy", "region", "global", "demo",
            "watershed", "canyon", "canyon_single"};
        for (String key : keys) {
            TerrainModeDescriptor mode = TerrainModeRegistry.selectable(key);
            TerrainModeDescriptor validated = TerrainModeRegistry.requireValid(
                mode.source(), mode.recipe(), mode.scaleId());
            if (!mode.equals(validated)) throw new AssertionError("Selectable mode drift: " + key);
        }
        reject("live_diffusion_global", "regional-processed-vdm-v1", "relief_3x_sea62_1024_v1");
        reject("region_diffusion_processed_v1", "regional-tuned-diffusion-v1", "raw_model_sea62_1024_v1");
        reject("region_diffusion_processed_v1", "regional-processed-vdm-v1", "relief_3x_sea62_1024_v1");
        reject("metric_processed_readonly_v1", "metric-processed-surface-v1", "raw_model_sea62_1024_v1");
        if (TerrainScale.METRIC_SURFACE.height(126) != 126
                || TerrainScale.METRIC_SURFACE.localHeight(62) != 62) {
            throw new AssertionError("Metric adapter must preserve game-space Y");
        }
        TerrainModeRegistry.requireValid("demo_landforms_perlin_v2", "diffusion-vdm-demo-cliffs-v3", "legacy");
        System.out.println("PASS selectable registry, strict pairs, legacy demo scaling");
    }

    private static void reject(String source, String recipe, String scale) {
        try {
            TerrainModeRegistry.requireValid(source, recipe, scale);
            throw new AssertionError("Invalid terrain mode accepted: " + source);
        } catch (IllegalArgumentException expected) {
            // The contract rejects invalid triples before model construction.
        }
    }
}
