package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainPreparation;
import com.remotemountains.diffusion.DiffusionTerrainSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.function.Supplier;

/** Disk-first cache of the model's unmodified height and water samples. */
public final class RawRegionTerrainSource implements BaseTerrainSource, TerrainPreparation {
    public static final String RECIPE = "regional-raw-diffusion-v1";
    public static final String TUNED_RECIPE = "regional-tuned-diffusion-v1";
    private final Path directory;
    private final long seed;
    private final int width;
    private final String recipe;
    private volatile String identity;
    private BaseTerrainSource model;
    private final Supplier<BaseTerrainSource> modelFactory;
    private final Object cacheLock = new Object();
    private final Object preparationLock = new Object();
    private final Map<Long, CompletableFuture<RawRegionArtifact>> preparations = new HashMap<>();
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

    @Override public Terrain.Column sample(double x, double z) {
        int wx = (int) Math.floor(x), wz = (int) Math.floor(z);
        int rx = Math.floorDiv(wx, width), rz = Math.floorDiv(wz, width);
        RawRegionArtifact artifact = region(rx, rz, false);
        return artifact.sample(Math.floorMod(wx, width), Math.floorMod(wz, width));
    }

    /** Read a regular world grid in region-sized strips to avoid LRU churn across a halo. */
    public Terrain.Column[] sampleGrid(int originX, int originZ, int side, int spacing) {
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
                RawRegionArtifact artifact = region(rx, rz, false);
                for (int z = firstZ; z <= lastZ; z++) for (int x = firstX; x <= lastX; x++) {
                    int wx = originX + x * spacing, wz = originZ + z * spacing;
                    result[z * side + x] = artifact.sample(wx - rx * width, wz - rz * width);
                }
            }
        }
        return result;
    }

    @Override public Path prepareRegion(int rx, int rz) {
        region(rx, rz, true);
        return RawRegionArtifact.path(directory, rx, rz);
    }

    @Override public void prepareBounds(int minWorldX, int minWorldZ,
            int maxWorldXInclusive, int maxWorldZInclusive) {
        if (maxWorldXInclusive < minWorldX || maxWorldZInclusive < minWorldZ) {
            throw new IllegalArgumentException("Invalid preparation bounds");
        }
        for (int rz = Math.floorDiv(minWorldZ, width); rz <= Math.floorDiv(maxWorldZInclusive, width); rz++) {
            for (int rx = Math.floorDiv(minWorldX, width); rx <= Math.floorDiv(maxWorldXInclusive, width); rx++) {
                prepareRegion(rx, rz);
            }
        }
    }

    private RawRegionArtifact region(int rx, int rz, boolean allowPreparation) {
        long key = ((long) rx << 32) ^ (rz & 0xffffffffL);
        CompletableFuture<RawRegionArtifact> future;
        boolean owner = false;
        synchronized (cacheLock) {
            RawRegionArtifact cached = regions.get(key);
            if (cached != null) {
                return cached;
            }
            future = preparations.get(key);
            if (future == null) {
                if (!allowPreparation && !Files.exists(RawRegionArtifact.path(directory, rx, rz))) {
                    throw missingRegion(rx, rz);
                }
                future = new CompletableFuture<>();
                preparations.put(key, future);
                owner = true;
            }
        }
        if (!owner) {
            try {
                return future.join();
            } catch (CompletionException failure) {
                throw new IllegalStateException("Cannot load raw terrain region " + rx + "," + rz, failure.getCause());
            }
        }
        try {
            RawRegionArtifact artifact = loadOrPrepare(rx, rz, allowPreparation);
            synchronized (cacheLock) {
                regions.put(key, artifact);
            }
            future.complete(artifact);
            return artifact;
        } catch (Throwable failure) {
            future.completeExceptionally(failure);
            if (failure instanceof Error error) {
                throw error;
            }
            if (failure instanceof IllegalStateException state) {
                throw state;
            }
            throw new IllegalStateException("Cannot load raw terrain region " + rx + "," + rz, failure);
        } finally {
            synchronized (cacheLock) {
                preparations.remove(key, future);
            }
        }
    }

    private IllegalStateException missingRegion(int rx, int rz) {
        String state = Boolean.getBoolean("remotemountains.regionOffline")
                ? "Missing offline raw region " : "Missing prepared raw region ";
        return new IllegalStateException("Cannot load raw terrain region " + rx + "," + rz,
                new IOException(state + rx + "," + rz));
    }

    private RawRegionArtifact loadOrPrepare(int rx, int rz, boolean allowPreparation) throws IOException {
        Path file = RawRegionArtifact.path(directory, rx, rz);
        if (Files.exists(file)) {
            if (identity.isBlank()) {
                throw new IOException("Model identity is required to read raw region");
            }
            return RawRegionArtifact.read(directory, seed, identity, recipe, width, rx, rz);
        }
        if (!allowPreparation || Boolean.getBoolean("remotemountains.regionOffline")) {
            throw missingRegion(rx, rz);
        }
        synchronized (preparationLock) {
            if (Files.exists(file)) {
                return RawRegionArtifact.read(directory, seed, identity, recipe, width, rx, rz);
            }
            if (model == null) {
                model = modelFactory.get();
            }
            if (!identity.isBlank() && !identity.equals(model.identity())) {
                throw new IOException("Raw region model identity changed");
            }
            if (model.identity().isBlank()) {
                throw new IOException("Raw region model identity is blank");
            }
            identity = model.identity();
            Files.createDirectories(directory);
            writeManifest();
            return RawRegionArtifact.prepare(directory, seed, identity, recipe, width, rx, rz, model);
        }
    }

    private void writeManifest() throws IOException {
        Path manifest = directory.resolve("dataset.id");
        if (Files.exists(manifest)) {
            return;
        }
        Path part = Files.createTempFile(directory, "raw-dataset-", ".part");
        try {
            Files.writeString(part, seed + "\n" + identity + "\n" + recipe + "\n" + width + "\n");
            Files.move(part, manifest, StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(part);
        }
    }
}
