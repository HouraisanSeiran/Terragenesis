package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Terrain;
import com.remotemountains.diffusion.DiffusionTerrainSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

/** Disk-first cache of the model's unmodified height and water samples. */
public final class RawRegionTerrainSource implements BaseTerrainSource {
    public static final String RECIPE = "regional-raw-diffusion-v1";
    public static final String TUNED_RECIPE = "regional-tuned-diffusion-v1";
    private final Path directory;
    private final long seed;
    private final int width;
    private final String recipe;
    private volatile String identity;
    private BaseTerrainSource model;
    private final Supplier<BaseTerrainSource> modelFactory;
    private final Map<Long, RawRegionArtifact> regions = new LinkedHashMap<>(8, .75f, true) {
        @Override protected boolean removeEldestEntry(Map.Entry<Long, RawRegionArtifact> entry) {
            return size() > Math.max(9, Math.min(16, 32_000_000 / (width * width)));
        }
    };

    public RawRegionTerrainSource(Path root, long seed, String identity, RegionConfig config) {
        this(root, seed, identity, RECIPE, config);
    }

    public RawRegionTerrainSource(Path root, long seed, String identity, String recipe, RegionConfig config) {
        this(root, seed, identity, recipe, config,
            () -> new DiffusionTerrainSource(seed, identity, true,
                recipe.equals(TUNED_RECIPE) ? "geographic_v2" : "geographic_v1"));
    }

    public RawRegionTerrainSource(Path root, long seed, String identity, RegionConfig config,
            Supplier<BaseTerrainSource> modelFactory) {
        this(root, seed, identity, RECIPE, config, modelFactory);
    }

    public RawRegionTerrainSource(Path root, long seed, String identity, String recipe, RegionConfig config,
            Supplier<BaseTerrainSource> modelFactory) {
        if (!recipe.equals(RECIPE) && !recipe.equals(TUNED_RECIPE))
            throw new IllegalArgumentException("Unsupported raw model recipe: " + recipe);
        this.seed = seed; this.identity = identity; this.width = config.worldWidth(); this.recipe = recipe;
        this.modelFactory = modelFactory;
        directory = root.resolve("seed-" + seed).resolve(recipe + "-" + config.chunks() + "-" + config.processing());
        Path manifest = directory.resolve("dataset.id");
        if (Files.exists(manifest)) try {
            String[] lines = Files.readString(manifest).split("\\R");
            if (lines.length != 4 || !lines[0].equals(Long.toString(seed)) || !lines[2].equals(recipe)
                    || !lines[3].equals(Integer.toString(width)) || (!identity.isBlank() && !identity.equals(lines[1])))
                throw new IllegalStateException("Raw region dataset identity mismatch");
            this.identity = lines[1];
        } catch (IOException ex) { throw new IllegalStateException("Cannot read raw region identity", ex); }
    }

    @Override public String identity() { return identity; }
    public String recipe() { return recipe; }
    public Path directory() { return directory; }

    @Override public synchronized Terrain.Column sample(double x, double z) {
        int wx = (int) Math.floor(x), wz = (int) Math.floor(z);
        int rx = Math.floorDiv(wx, width), rz = Math.floorDiv(wz, width);
        RawRegionArtifact artifact = region(rx, rz);
        return artifact.sample(Math.floorMod(wx, width), Math.floorMod(wz, width));
    }

    /** Read a regular world grid in region-sized strips to avoid LRU churn across a halo. */
    public synchronized Terrain.Column[] sampleGrid(int originX, int originZ, int side, int spacing) {
        if (side <= 0 || spacing <= 0) throw new IllegalArgumentException("Invalid raw grid dimensions");
        int endX = Math.addExact(originX, Math.multiplyExact(side - 1, spacing));
        int endZ = Math.addExact(originZ, Math.multiplyExact(side - 1, spacing));
        Terrain.Column[] result = new Terrain.Column[Math.multiplyExact(side, side)];
        for (int rz = Math.floorDiv(originZ, width);
                rz <= Math.floorDiv(endZ, width); rz++) {
            int firstZ = Math.max(0, Math.floorDiv(rz * width - originZ + spacing - 1, spacing));
            int lastZ = Math.min(side - 1, Math.floorDiv((rz + 1) * width - 1 - originZ, spacing));
            for (int rx = Math.floorDiv(originX, width);
                    rx <= Math.floorDiv(endX, width); rx++) {
                int firstX = Math.max(0, Math.floorDiv(rx * width - originX + spacing - 1, spacing));
                int lastX = Math.min(side - 1, Math.floorDiv((rx + 1) * width - 1 - originX, spacing));
                RawRegionArtifact artifact = region(rx, rz);
                for (int z = firstZ; z <= lastZ; z++) for (int x = firstX; x <= lastX; x++) {
                    int wx = originX + x * spacing, wz = originZ + z * spacing;
                    result[z * side + x] = artifact.sample(wx - rx * width, wz - rz * width);
                }
            }
        }
        return result;
    }

    private RawRegionArtifact region(int rx, int rz) {
        long key = ((long) rx << 32) ^ (rz & 0xffffffffL);
        RawRegionArtifact cached = regions.get(key);
        if (cached != null) return cached;
        try {
            Path file = RawRegionArtifact.path(directory, rx, rz);
            RawRegionArtifact artifact;
            if (Files.exists(file)) {
                if (identity.isBlank()) throw new IOException("Model identity is required to read raw region");
                artifact = RawRegionArtifact.read(directory, seed, identity, recipe, width, rx, rz);
            } else {
                if (Boolean.getBoolean("remotemountains.regionOffline"))
                    throw new IOException("Missing offline raw region " + rx + "," + rz);
                if (model == null) model = modelFactory.get();
                if (!identity.isBlank() && !identity.equals(model.identity()))
                    throw new IOException("Raw region model identity changed");
                identity = model.identity();
                Files.createDirectories(directory);
                Path manifest = directory.resolve("dataset.id");
                if (!Files.exists(manifest)) {
                    Path part = Files.createTempFile(directory, "raw-dataset-", ".part");
                    try {
                        Files.writeString(part, seed + "\n" + identity + "\n" + recipe + "\n" + width + "\n");
                        Files.move(part, manifest, StandardCopyOption.ATOMIC_MOVE);
                    } finally { Files.deleteIfExists(part); }
                }
                artifact = RawRegionArtifact.prepare(directory, seed, identity, recipe, width, rx, rz, model);
            }
            regions.put(key, artifact);
            return artifact;
        } catch (IOException ex) { throw new IllegalStateException("Cannot load raw terrain region " + rx + "," + rz, ex); }
    }
}
