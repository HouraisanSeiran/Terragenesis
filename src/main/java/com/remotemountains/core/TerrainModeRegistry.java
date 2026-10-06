package com.remotemountains.core;

import com.remotemountains.cliff.CliffSettings;
import com.remotemountains.cliff.RegionalCliffLayout;
import com.remotemountains.region.DerivedRegionTerrainSource;
import com.remotemountains.region.MetricProcessedTerrainSource;
import com.remotemountains.region.RawRegionTerrainSource;
import com.remotemountains.region.RegionTerrainSource;
import com.remotemountains.watershed.WatershedTerrainSource;
import java.util.Map;
import java.util.Set;

/** Single contract for saved source, recipe, scale, and mode capabilities. */
public final class TerrainModeRegistry {
    private static final String RAW_SCALE = "raw_model_sea62_1024_v1";
    private static final String METRIC_SCALE = "metric_1m_sea62_1024_v1";
    private static final String TALL_SCALE = "relief_3x_sea62_1024_v1";
    private static final Map<String, TerrainModeDescriptor> SELECTABLE = Map.ofEntries(
        Map.entry("processed", new TerrainModeDescriptor("metric_processed_readonly_v1", MetricProcessedTerrainSource.RECIPE, METRIC_SCALE, false, TerrainModeDescriptor.Preflight.NONE)),
        Map.entry("raw", new TerrainModeDescriptor("region_diffusion_tuned_v1", RawRegionTerrainSource.TUNED_RECIPE, RAW_SCALE, true, TerrainModeDescriptor.Preflight.INSTALL_ONLY)),
        Map.entry("raw_legacy", new TerrainModeDescriptor("region_diffusion_raw_v1", RawRegionTerrainSource.RECIPE, RAW_SCALE, true, TerrainModeDescriptor.Preflight.INSTALL_ONLY)),
        Map.entry("region", new TerrainModeDescriptor("region_diffusion_v1", RegionTerrainSource.RECIPE, TALL_SCALE, true, TerrainModeDescriptor.Preflight.INSTALL_ONLY)),
        Map.entry("global", new TerrainModeDescriptor("live_diffusion_global", RegionalCliffLayout.GLOBAL_RECIPE, TALL_SCALE, false, TerrainModeDescriptor.Preflight.START_SERVICE)),
        Map.entry("demo", new TerrainModeDescriptor("demo_landforms_perlin_v2", RegionalCliffLayout.DEMO_RECIPE, TALL_SCALE, false, TerrainModeDescriptor.Preflight.NONE)),
        Map.entry("watershed", new TerrainModeDescriptor("watershed_heightmap_v2", WatershedTerrainSource.RECIPE_V2, TALL_SCALE, false, TerrainModeDescriptor.Preflight.NONE)),
        Map.entry("canyon", new TerrainModeDescriptor("watershed_heightmap_v2", "watershed-vdm-canyon-v2", TALL_SCALE, false, TerrainModeDescriptor.Preflight.NONE)),
        Map.entry("canyon_single", new TerrainModeDescriptor("watershed_heightmap_v2", "watershed-vdm-canyon-single-v2", TALL_SCALE, false, TerrainModeDescriptor.Preflight.NONE)));
    private static final Set<String> LEGACY_RECIPES = Set.of(
        "diffusion-vdm-cliff-v1", CliffSettings.RECIPE, RegionalCliffLayout.GLOBAL_RECIPE,
        RegionalCliffLayout.DEMO_RECIPE, WatershedTerrainSource.RECIPE,
        WatershedTerrainSource.RECIPE_V2, "watershed-vdm-prepared-v1",
        "watershed-vdm-canyon-v2", "watershed-vdm-canyon-single-v2",
        RegionTerrainSource.RECIPE, RawRegionTerrainSource.RECIPE,
        RawRegionTerrainSource.TUNED_RECIPE, DerivedRegionTerrainSource.RECIPE,
        MetricProcessedTerrainSource.RECIPE);
    private static final Map<String, RegionMode> REGION_MODES = Map.of(
        "region_diffusion_processed_v1", new RegionMode(DerivedRegionTerrainSource.RECIPE, RAW_SCALE, true),
        "metric_processed_readonly_v1", new RegionMode(MetricProcessedTerrainSource.RECIPE, METRIC_SCALE, false),
        "region_diffusion_tuned_v1", new RegionMode(RawRegionTerrainSource.TUNED_RECIPE, RAW_SCALE, true),
        "region_diffusion_raw_v1", new RegionMode(RawRegionTerrainSource.RECIPE, RAW_SCALE, true),
        "region_diffusion_v1", new RegionMode(RegionTerrainSource.RECIPE, TALL_SCALE, true),
        "region_demo_v1", new RegionMode(RegionTerrainSource.RECIPE, TALL_SCALE, false));
    private static final Set<String> OTHER_SOURCES = Set.of(
        "legacy_auto", "baked_demo", "demo_landforms_v1", "demo_landforms_perlin_v2",
        "live_diffusion_global", "watershed_demo_v1", "watershed_heightmap_v2",
        "watershed_prepared_v1");

    private record RegionMode(String recipe, String scaleId, boolean installOnly) {}

    private TerrainModeRegistry() {}

    public static TerrainModeDescriptor selectable(String key) {
        TerrainModeDescriptor mode = SELECTABLE.get(key);
        if (mode == null) throw new IllegalArgumentException("Unknown terrain mode: " + key);
        return requireValid(mode.source(), mode.recipe(), mode.scaleId());
    }

    public static TerrainModeDescriptor requireValid(String source, String recipe, String scaleId) {
        TerrainScale.of(scaleId);
        if (!LEGACY_RECIPES.contains(recipe)) {
            throw new IllegalArgumentException("Unsupported saved VDM recipe");
        }
        RegionMode region = REGION_MODES.get(source);
        if (region != null) {
            if (!region.recipe().equals(recipe) || !region.scaleId().equals(scaleId)) {
                throw new IllegalArgumentException("Region source requires its matching scale and recipe");
            }
            return new TerrainModeDescriptor(source, recipe, scaleId, true,
                region.installOnly() ? TerrainModeDescriptor.Preflight.INSTALL_ONLY
                    : TerrainModeDescriptor.Preflight.NONE);
        }
        if (!OTHER_SOURCES.contains(source)) {
            throw new IllegalArgumentException("Unsupported terrain source: " + source);
        }
        requireNonRegionPair(source, recipe, scaleId);
        TerrainModeDescriptor.Preflight preflight = source.equals("live_diffusion_global")
            ? TerrainModeDescriptor.Preflight.START_SERVICE : TerrainModeDescriptor.Preflight.NONE;
        return new TerrainModeDescriptor(source, recipe, scaleId, false, preflight);
    }

    private static void requireNonRegionPair(String source, String recipe, String scaleId) {
        boolean tall = TALL_SCALE.equals(scaleId);
        boolean valid = switch (source) {
            case "legacy_auto" -> "diffusion-vdm-cliff-v1".equals(recipe)
                || CliffSettings.RECIPE.equals(recipe);
            case "baked_demo" -> "diffusion-vdm-cliff-v1".equals(recipe);
            case "demo_landforms_v1", "demo_landforms_perlin_v2" -> (tall || "legacy".equals(scaleId))
                && RegionalCliffLayout.DEMO_RECIPE.equals(recipe);
            case "live_diffusion_global" -> tall
                && RegionalCliffLayout.GLOBAL_RECIPE.equals(recipe);
            case "watershed_demo_v1" -> WatershedTerrainSource.RECIPE.equals(recipe);
            case "watershed_heightmap_v2" -> tall && (WatershedTerrainSource.RECIPE_V2.equals(recipe)
                || "watershed-vdm-canyon-v2".equals(recipe)
                || "watershed-vdm-canyon-single-v2".equals(recipe));
            case "watershed_prepared_v1" -> tall && "watershed-vdm-prepared-v1".equals(recipe);
            default -> false;
        };
        if (!valid) {
            throw new IllegalArgumentException("Source requires its matching scale and recipe");
        }
    }
}
