package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

/** Checks raw source persistence, offline reuse, and cache isolation. */
public final class RawRegionVerification {
    public static void main(String[] args) throws Exception {
        Path root = Path.of("verification", "regions", "raw-unit");
        Files.createDirectories(root);
        Path directory = Files.createTempDirectory(root, "raw-");
        RegionConfig config = new RegionConfig(3, "none_v1");
        if (TerrainScale.RAW_MODEL.factor() != 1 || TerrainScale.RAW_MODEL.seaLevel() != 62
                || TerrainScale.RAW_MODEL.upperY() != 1024
                || TerrainScale.RAW_MODEL.height(72) != 62 || TerrainScale.RAW_MODEL.height(172) != 162)
            throw new AssertionError("Raw scale is not one-to-one with sea level 62");
        AtomicInteger calls = new AtomicInteger();
        BaseTerrainSource model = new BaseTerrainSource() {
            public String identity() { return "synthetic-raw-v1"; }
            public Terrain.Column sample(double x, double z) {
                calls.incrementAndGet();
                double h = 72 + .25 * x + .5 * z;
                return new Terrain.Column(h, Double.NaN,
                    new Landscape.Base(h, Landform.KARST, new Landscape.Climate(.4, .6), 0));
            }
        };
        RawRegionTerrainSource source = new RawRegionTerrainSource(directory, 1234, model.identity(), config, () -> model);
        RawRegionTerrainSource tuned = new RawRegionTerrainSource(directory, 1234, model.identity(),
            RawRegionTerrainSource.TUNED_RECIPE, config, () -> model);
        if (source.directory().equals(tuned.directory())) throw new AssertionError("Profiles share a cache directory");
        source.prepareBounds(-48, -48, 48, 47);
        for (int[] point : new int[][] {{0, 0}, {47, 47}, {48, 0}, {-1, -1}, {-48, -48}})
            near(source.sample(point[0], point[1]).height(), 62 + .25 * point[0] + .5 * point[1]);
        if (calls.get() == 0) throw new AssertionError("Raw model was not sampled");
        RawRegionTerrainSource offline = new RawRegionTerrainSource(directory, 1234, model.identity(), config,
            () -> { throw new AssertionError("Offline read invoked model"); });
        System.setProperty("remotemountains.regionOffline", "true");
        try {
            near(offline.sample(-1, -1).height(), 61.25);
            try { offline.sample(96, 0); throw new AssertionError("Missing region accepted"); }
            catch (IllegalStateException expected) {
                if (expected.getCause() == null || !expected.getCause().getMessage().contains("Missing offline raw region 2,0"))
                    throw expected;
            }
        } finally { System.clearProperty("remotemountains.regionOffline"); }
        if (!source.directory().toString().contains(RawRegionTerrainSource.RECIPE))
            throw new AssertionError("Raw cache is not isolated by recipe");
        tuned.prepareRegion(0, 0);
        near(tuned.sample(0, 0).height(), 62);
        try {
            RawRegionArtifact.read(tuned.directory(), 1234, model.identity(), RawRegionTerrainSource.RECIPE,
                config.worldWidth(), 0, 0);
            throw new AssertionError("Wrong profile recipe accepted");
        } catch (java.io.IOException expected) {
            if (!expected.getMessage().contains("identity")) throw expected;
        }
        Path artifact = RawRegionArtifact.path(source.directory(), 0, 0);
        byte[] data = Files.readAllBytes(artifact);
        data[data.length - 1] ^= 1;
        Files.write(artifact, data);
        try {
            RawRegionArtifact.read(source.directory(), 1234, model.identity(), RawRegionTerrainSource.RECIPE,
                config.worldWidth(), 0, 0);
            throw new AssertionError("Corrupt raw region accepted");
        } catch (java.io.IOException expected) {
            if (!expected.getMessage().contains("checksum")) throw expected;
        }
        System.out.println("PASS raw region source values, offline reload, cache identity, and checksum");
    }

    private static void near(double actual, double expected) {
        if (Math.abs(actual - expected) > 1e-9) throw new AssertionError(actual + " != " + expected);
    }
}
