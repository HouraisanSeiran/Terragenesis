package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import com.remotemountains.region.processing.RegionProcessor;
import com.remotemountains.world.SurfacePalette;
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;

/** Bounded real-height import through production raw and derived artifacts. */
public final class RealSampleImportVerification {
    private static final long SEED = 20260927;
    private static final String ID = "82a3c4a1463c96ab67320649a4cfe62fd67ca5f3e4874d7776c54d4096fc73f4";
    private static final int ORIGIN_X = 4352, ORIGIN_Z = 17664, SIDE = 513;

    public static void main(String[] args) throws Exception {
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();
        Path root = Path.of("verification", "real-import");
        float[] heights = new float[SIDE * SIDE];
        try (DataInputStream input = new DataInputStream(Files.newInputStream(root.resolve("plains-height-f32be.bin")))) {
            for (int i = 0; i < heights.length; i++) heights[i] = input.readFloat();
            if (input.read() != -1) throw new AssertionError("Unexpected real fixture length");
        }
        BaseTerrainSource realHeight = new BaseTerrainSource() {
            public String identity() { return ID; }
            public Terrain.Column sample(double x, double z) {
                double gx = (x - ORIGIN_X) / 2, gz = (z - ORIGIN_Z) / 2;
                if (gx < 0 || gz < 0 || gx >= SIDE - 1 || gz >= SIDE - 1)
                    throw new IllegalArgumentException("Real sample coverage exceeded: " + x + "," + z);
                int ix = (int) gx, iz = (int) gz;
                double fx = gx - ix, fz = gz - iz;
                int i = iz * SIDE + ix;
                double h = (heights[i] * (1 - fx) + heights[i + 1] * fx) * (1 - fz)
                    + (heights[i + SIDE] * (1 - fx) + heights[i + SIDE + 1] * fx) * fz;
                double rawModelY = h + 10; // RAW_MODEL.height(y) = y - 10.
                return new Terrain.Column(rawModelY, Double.NaN,
                    new Landscape.Base(rawModelY, Landform.KARST, new Landscape.Climate(.5, .5), 0));
            }
        };
        Path store = Files.createTempDirectory(root, "bounded-");
        RegionConfig config = new RegionConfig(3, "none_v1");
        RawRegionTerrainSource raw = new RawRegionTerrainSource(store, SEED, ID,
            RawRegionTerrainSource.TUNED_RECIPE, config, () -> realHeight);
        DerivedRegionTerrainSource derived = new DerivedRegionTerrainSource(store, SEED, ID, config, () -> raw);
        int rx = 101, rz = 378;
        Path artifact = derived.prepareRegion(rx, rz);
        Path adjacent = derived.prepareRegion(rx + 1, rz);
        derived.prepareRegion(rx, rz + 1);
        derived.prepareRegion(rx + 1, rz + 1);
        byte[] artifactBefore = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(artifact));
        byte[] adjacentBefore = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(adjacent));
        var constructor = Terrain.class.getDeclaredConstructor(long.class, BaseTerrainSource.class, TerrainScale.class);
        constructor.setAccessible(true);
        SurfacePalette palette = new SurfacePalette();
        int halo = RegionProcessor.REQUIRED_HALO_SAMPLES;
        int gridSide = 49 + 2 * halo;
        int gridX = rx * 48 - 2 * halo;
        int gridZ = rz * 48 - 2 * halo;
        float[] sourceGrid = new float[gridSide * gridSide];
        for (int gz = 0; gz < gridSide; gz++) {
            for (int gx = 0; gx < gridSide; gx++) {
                sourceGrid[gz * gridSide + gx] = (float) raw.sample(gridX + gx * 2, gridZ + gz * 2).height();
            }
        }
        float[] expected = RegionProcessor.process(sourceGrid, gridSide, gridSide,
            gridX, gridZ, SEED, new float[sourceGrid.length]).heights();
        double[] firstPass = new double[49 * 49];
        try (Terrain terrain = constructor.newInstance(SEED, derived, TerrainScale.RAW_MODEL)) {
            for (int z = 0; z <= 48; z += 2) {
                for (int x = 0; x <= 48; x += 2) {
                    int worldX = rx * 48 + x;
                    int worldZ = rz * 48 + z;
                    Terrain.Column column = terrain.sample(worldX, worldZ);
                    firstPass[z * 49 + x] = column.height();
                    double baseline = expected[(z / 2 + halo) * gridSide + x / 2 + halo];
                    if (Math.abs(column.height() - baseline) > .0002) {
                        throw new AssertionError("Real derived height differs at " + worldX + "," + worldZ);
                    }
                    int surface = (int) Math.floor(column.height());
                    if (palette.sample(terrain, worldX, surface, worldZ, column) != Blocks.GRASS_BLOCK.defaultBlockState()
                            || palette.sample(terrain, worldX, surface + 1, worldZ, column) != Blocks.AIR.defaultBlockState()
                            || palette.sample(terrain, worldX, -63, worldZ, column) != Blocks.BEDROCK.defaultBlockState()) {
                        throw new AssertionError("Minecraft BlockState differs at " + worldX + "," + worldZ);
                    }
                }
            }
        }
        var left = DerivedRegionArtifact.read(derived.directory(), SEED, ID, 48, rx, rz);
        var right = DerivedRegionArtifact.read(derived.directory(), SEED, ID, 48, rx + 1, rz);
        for (int z = 0; z <= 48; z += 2) {
            double fromLeft = left.sample(48, z).height();
            double atRight = right.sample(0, z).height();
            if (!Double.isFinite(fromLeft) || !Double.isFinite(atRight)
                    || Math.abs(fromLeft - atRight) > .0001) {
                throw new AssertionError("Adjacent real regions have a boundary gap");
            }
        }
        System.setProperty("remotemountains.regionOffline", "true");
        try {
            DerivedRegionTerrainSource offline = new DerivedRegionTerrainSource(store, SEED, ID, config,
                () -> { throw new AssertionError("Offline import invoked model"); });
            try (Terrain terrain = constructor.newInstance(SEED, offline, TerrainScale.RAW_MODEL)) {
                for (int z = 0; z <= 48; z += 2) for (int x = 0; x <= 48; x += 2) {
                    int worldX = rx * 48 + x, worldZ = rz * 48 + z;
                    var column = terrain.sample(worldX, worldZ);
                    if (Math.abs(column.height() - firstPass[z * 49 + x]) > .0001)
                        throw new AssertionError("Offline height differs");
                    int surface = (int) Math.floor(column.height());
                    if (palette.sample(terrain, worldX, surface, worldZ, column)
                            != Blocks.GRASS_BLOCK.defaultBlockState())
                        throw new AssertionError("Offline block differs");
                }
            }
        } finally {
            System.clearProperty("remotemountains.regionOffline");
        }
        if (!Arrays.equals(artifactBefore, MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(artifact))))
            throw new AssertionError("Offline load modified derived artifact");
        if (!Arrays.equals(adjacentBefore, MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(adjacent))))
            throw new AssertionError("Offline load modified adjacent artifact");
        System.out.println("PASS bounded real-height production artifact import and Minecraft BlockStates; no model service");
    }
}
