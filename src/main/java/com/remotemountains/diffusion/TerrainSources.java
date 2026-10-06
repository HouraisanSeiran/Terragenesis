package com.remotemountains.diffusion;

import com.remotemountains.core.BaseTerrainSource;

/** Resolve from persisted identity; new worlds default to the self-contained diffusion demo. */
public final class TerrainSources {
    public static BaseTerrainSource create(long seed,String identity){
        return create(seed,identity,"legacy_auto");
    }
    public static BaseTerrainSource create(long seed,String identity,String mode){
        return switch(mode){
            case "watershed_demo_v1" -> new com.remotemountains.watershed.WatershedTerrainSource(seed,identity);
            case "watershed_heightmap_v2" -> new com.remotemountains.watershed.WatershedTerrainSource(seed,identity,true);
            case "watershed_prepared_v1" -> {
                String directory = System.getProperty("remotemountains.preparedDir", "");
                if (directory.isBlank()) throw new IllegalStateException("Prepared terrain directory is required");
                try {
                    yield com.remotemountains.prepared.PreparedArtifact
                        .read(java.nio.file.Path.of(directory), seed, identity).terrain();
                } catch (java.io.IOException e) {
                    throw new IllegalStateException("Cannot load prepared terrain", e);
                }
            }
            case "live_diffusion_global" -> new DiffusionTerrainSource(seed,identity);
            case "demo_landforms_v1" -> new DemoLandformSource(seed,identity);
            case "demo_landforms_perlin_v2" -> new DemoLandformSource(seed,identity,true);
            case "baked_demo" -> new BakedTerrainSource(seed,identity);
            case "legacy_auto" -> {
                if(identity.startsWith(DemoLandformSource.NATURAL_PREFIX))yield new DemoLandformSource(seed,identity,true);
                if(identity.startsWith(DemoLandformSource.PREFIX))yield new DemoLandformSource(seed,identity);
                boolean live=identity.isEmpty()?Boolean.getBoolean("remotemountains.liveDiffusion"):!identity.startsWith("baked-");
                yield live?new DiffusionTerrainSource(seed,identity):new BakedTerrainSource(seed,identity);
            }
            default -> throw new IllegalArgumentException("Unsupported terrain source: "+mode);
        };
    }
}
