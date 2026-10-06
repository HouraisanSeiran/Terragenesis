package com.remotemountains.core;

import com.remotemountains.cliff.CliffPipeline;
import com.remotemountains.cliff.CliffSettings;
import com.remotemountains.region.DerivedRegionTerrainSource;
import com.remotemountains.region.MetricProcessedTerrainSource;
import com.remotemountains.region.RawRegionTerrainSource;
import com.remotemountains.vdm.DensityColumn;
import com.remotemountains.vdm.GeneratedVdmSource;
import java.util.concurrent.CompletableFuture;

/** Seed-bound terrain facade used by world generation and biome lookup. */
public final class Terrain implements AutoCloseable {
    public static final int TILE = 64;
    private static final int DEFAULT_REGION_CHUNKS = 24;
    private static final String DEFAULT_REGION_PROCESSING = "none_v1";

    public record Column(double height, double water, Landscape.Base base, DensityColumn density) {
        public Column(double height, double water, Landscape.Base base) {
            this(height, water, base, null);
        }
    }

    public final Landscape landscape;
    public final Hydrology hydrology;
    public final TerrainScale scale;
    private final BaseTerrainSource source;
    private final TerrainTileCache tiles;

    public Terrain(long seed) {
        this(seed, "");
    }

    public Terrain(long seed, String identity) {
        this(seed, identity, CliffSettings.RECIPE);
    }

    public Terrain(long seed, String identity, String recipe) {
        this(seed, identity, recipe, "legacy_auto");
    }

    public Terrain(long seed, String identity, String recipe, String sourceMode) {
        this(seed, identity, recipe, sourceMode, "legacy");
    }

    public Terrain(long seed, String identity, String recipe, String sourceMode, String scaleId) {
        this(seed, identity, recipe, sourceMode, scaleId, DEFAULT_REGION_CHUNKS, DEFAULT_REGION_PROCESSING);
    }

    public Terrain(long seed, String identity, String recipe, String sourceMode, String scaleId,
            int regionChunks, String regionProcessing) {
        this(seed, TerrainSourceFactory.create(seed, identity, recipe, sourceMode,
            TerrainScale.of(scaleId), regionChunks, regionProcessing), TerrainScale.of(scaleId));
    }

    private Terrain(long seed, BaseTerrainSource source) {
        this(seed, source, TerrainScale.LEGACY);
    }

    private Terrain(long seed, BaseTerrainSource source, TerrainScale scale) {
        this.scale = scale;
        this.landscape = new Landscape(seed);
        this.hydrology = new Hydrology(landscape);
        this.source = source == null ? new PrototypeTerrainSource(landscape, hydrology) : source;
        this.tiles = new TerrainTileCache(this::sample);
    }

    public static Terrain proceduralPrototype(long seed) {
        return new Terrain(seed, (BaseTerrainSource) null);
    }

    public String identity() {
        return source.identity();
    }

    public String vdmIdentity() {
        return TerrainSourceFactory.recipeOf(source);
    }

    public CliffPipeline.Result cliff() {
        return source instanceof GeneratedVdmSource generated ? generated.cliff() : null;
    }

    public Column sample(double x, double z) {
        return source.sample(x, z);
    }

    public CompletableFuture<Column[]> tile(int tx, int tz) {
        return tiles.tile(tx, tz);
    }

    public void prefetch(int tx, int tz) {
        tiles.prefetch(tx, tz);
    }

    /** Prepare a completed region before read-only sampling when the source supports it. */
    public void prepareBounds(int minWorldX, int minWorldZ,
            int maxWorldXInclusive, int maxWorldZInclusive) {
        if (source instanceof TerrainPreparation preparation) {
            preparation.prepareBounds(minWorldX, minWorldZ, maxWorldXInclusive, maxWorldZInclusive);
        }
    }

    public boolean needsPreparation() {
        return source instanceof TerrainPreparation;
    }

    public boolean metricSurface() {
        return source instanceof MetricProcessedTerrainSource;
    }

    public boolean solid(int x, int y, int z, Column column) {
        Landscape.Base base = column.base();
        Landscape.Base local = new Landscape.Base(scale.localHeight(base.height()), base.type(),
            base.climate(), base.landmark());
        if (source instanceof RawRegionTerrainSource || source instanceof DerivedRegionTerrainSource
                || source instanceof MetricProcessedTerrainSource) {
            return y <= Math.floor(column.height());
        }
        boolean filled = column.density() != null
            ? column.density().solid(y) : y <= Math.floor(column.height());
        return filled && !landscape.caves.contains(scale.local(x), scale.localHeight(y), scale.local(z),
            local, scale.localHeight(column.height()), scale.localHeight(column.water()));
    }

    @Override
    public void close() {
        tiles.close();
    }
}
