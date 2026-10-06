package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainPreparation;
import com.remotemountains.region.processing.RegionProcessor;
import java.io.IOException;
import java.nio.file.*;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.function.Supplier;

/** Disk-first processed terrain, derived from immutable tuned model regions. */
public final class DerivedRegionTerrainSource implements BaseTerrainSource, TerrainPreparation {
    public static final String RECIPE = "regional-processed-vdm-v1";
    private final Path directory;
    private final long seed;
    private final int width;
    private volatile String identity;
    private final Supplier<RawRegionTerrainSource> rawFactory;
    private RawRegionTerrainSource raw;
    private final Object cacheLock = new Object();
    private final Object preparationLock = new Object();
    private final Map<Long, CompletableFuture<DerivedRegionArtifact>> preparations = new HashMap<>();
    private final Map<Long, DerivedRegionArtifact> regions = new LinkedHashMap<>(8, .75f, true) {
        @Override protected boolean removeEldestEntry(Map.Entry<Long, DerivedRegionArtifact> entry) {
            long bytes = (long) (width / 2 + 1) * (width / 2 + 1) * 50;
            return size() > Math.max(1, Math.min(8, 32_000_000 / bytes));
        }
    };

    public DerivedRegionTerrainSource(Path root, long seed, String identity, RegionConfig config) {
        this(root, seed, identity, config,
            () -> new RawRegionTerrainSource(root, seed, identity,
                RawRegionTerrainSource.TUNED_RECIPE, config));
    }

    public DerivedRegionTerrainSource(Path root, long seed, String identity, RegionConfig config,
            Supplier<RawRegionTerrainSource> rawFactory) {
        this.seed = seed; this.identity = identity; this.width = config.worldWidth();
        this.rawFactory = rawFactory;
        directory = root.resolve("seed-" + seed).resolve(RECIPE + "-" + config.chunks()
            + "-" + config.processing() + "-" + RegionProcessor.ALGORITHM_ID);
        Path manifest = directory.resolve("dataset.id");
        if (Files.exists(manifest)) try {
            String[] lines = Files.readString(manifest).split("\\R");
            if (lines.length != 5 || !lines[0].equals(Long.toString(seed))
                    || !lines[2].equals(RECIPE) || !lines[3].equals(Integer.toString(width))
                    || !lines[4].equals(RegionProcessor.ALGORITHM_ID)
                    || (!identity.isBlank() && !identity.equals(lines[1])))
                throw new IllegalStateException("Derived dataset identity mismatch");
            this.identity = lines[1];
        } catch (IOException ex) { throw new IllegalStateException("Cannot read derived identity", ex); }
    }

    @Override public String identity() { return identity; }
    public String recipe() { return RECIPE; }
    public Path directory() { return directory; }

    @Override public Terrain.Column sample(double x, double z) {
        int wx = (int) Math.floor(x), wz = (int) Math.floor(z);
        int rx = Math.floorDiv(wx, width), rz = Math.floorDiv(wz, width);
        DerivedRegionArtifact artifact = region(rx, rz, false);
        return artifact.sample(Math.floorMod(wx, width), Math.floorMod(wz, width));
    }

    @Override
    public Path prepareRegion(int rx, int rz) {
        region(rx, rz, true);
        return DerivedRegionArtifact.path(directory, rx, rz);
    }

    @Override
    public void prepareBounds(int minWorldX, int minWorldZ,
            int maxWorldXInclusive, int maxWorldZInclusive) {
        if (maxWorldXInclusive < minWorldX || maxWorldZInclusive < minWorldZ) {
            throw new IllegalArgumentException("Invalid preparation bounds");
        }
        int minRegionX = Math.floorDiv(minWorldX, width);
        int maxRegionX = Math.floorDiv(maxWorldXInclusive, width);
        int minRegionZ = Math.floorDiv(minWorldZ, width);
        int maxRegionZ = Math.floorDiv(maxWorldZInclusive, width);
        for (int rz = minRegionZ; rz <= maxRegionZ; rz++) {
            for (int rx = minRegionX; rx <= maxRegionX; rx++) {
                prepareRegion(rx, rz);
            }
        }
    }

    private DerivedRegionArtifact region(int rx, int rz, boolean allowPreparation) {
        long key = ((long) rx << 32) ^ (rz & 0xffffffffL);
        CompletableFuture<DerivedRegionArtifact> future;
        boolean owner = false;
        synchronized (cacheLock) {
            DerivedRegionArtifact cached = regions.get(key);
            if (cached != null) return cached;
            future = preparations.get(key);
            if (future == null) {
                if (!allowPreparation && !Files.exists(DerivedRegionArtifact.path(directory, rx, rz))) {
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
                throw new IllegalStateException("Cannot load derived region " + rx + "," + rz,
                        failure.getCause());
            }
        }
        try {
            DerivedRegionArtifact artifact = loadOrPrepare(rx, rz, allowPreparation);
            synchronized (cacheLock) {
                regions.put(key, artifact);
            }
            future.complete(artifact);
            return artifact;
        } catch (Throwable failure) {
            future.completeExceptionally(failure);
            if (failure instanceof Error error) throw error;
            if (failure instanceof IllegalStateException state) throw state;
            throw new IllegalStateException("Cannot load derived region " + rx + "," + rz, failure);
        } finally {
            synchronized (cacheLock) {
                preparations.remove(key, future);
            }
        }
    }

    private DerivedRegionArtifact loadOrPrepare(int rx, int rz, boolean allowPreparation) throws IOException {
        Path file = DerivedRegionArtifact.path(directory, rx, rz);
        if (Files.exists(file)) {
            if (identity.isBlank()) throw new IOException("Model identity is required to read derived region");
            return DerivedRegionArtifact.read(directory, seed, identity, width, rx, rz);
        }
        if (!allowPreparation || Boolean.getBoolean("remotemountains.regionOffline")) {
            throw missingRegion(rx, rz);
        }
        synchronized (preparationLock) {
            if (Files.exists(file)) {
                return DerivedRegionArtifact.read(directory, seed, identity, width, rx, rz);
            }
            if (raw == null) raw = rawFactory.get();
            DerivedRegionArtifact artifact = DerivedRegionArtifact.prepare(directory, seed, identity,
                    width, rx, rz, raw);
            if (identity.isBlank()) identity = raw.identity();
            if (!identity.equals(raw.identity()) || identity.isBlank()) {
                throw new IOException("Derived source model identity changed or is blank");
            }
            writeManifest();
            return artifact;
        }
    }

    private IllegalStateException missingRegion(int rx, int rz) {
        String state = Boolean.getBoolean("remotemountains.regionOffline")
                ? "Missing offline derived region " : "Missing prepared derived region ";
        return new IllegalStateException("Cannot load derived region " + rx + "," + rz,
                new IOException(state + rx + "," + rz));
    }

    private void writeManifest() throws IOException {
        Path manifest = directory.resolve("dataset.id");
        if (Files.exists(manifest)) return;
        Path part = Files.createTempFile(directory, "derived-dataset-", ".part");
        try {
            Files.writeString(part, seed + "\n" + identity + "\n" + RECIPE + "\n" + width
                    + "\n" + RegionProcessor.ALGORITHM_ID + "\n");
            Files.move(part, manifest, StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(part);
        }
    }
}