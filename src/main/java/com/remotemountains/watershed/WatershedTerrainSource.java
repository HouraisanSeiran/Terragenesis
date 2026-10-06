package com.remotemountains.watershed;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Noise;
import com.remotemountains.core.Terrain;
import com.remotemountains.diffusion.BakedTerrainSource;

/** Finite mountain-to-ocean Terrain Diffusion exhibit with a shared runoff graph. */
public final class WatershedTerrainSource implements BaseTerrainSource {
    public static final String SOURCE = "watershed_demo_v1";
    public static final String RECIPE = "watershed-vdm-runoff-v1";
    public static final String SOURCE_V2 = "watershed_heightmap_v2";
    public static final String RECIPE_V2 = "watershed-vdm-heightmap-v2";
    public static final double SEA = 72;
    private final BakedTerrainSource baked;
    private final DrainageGraph graph;
    private final String identity;
    private final long seed;
    private final Noise micro;
    private final MountainRelief mountains;
    private final Peak peak;
    private final RiverProfile riverProfile;

    public record Peak(double x, double z, double localHeight, double worldHeight) {}
    public record Audit(String identity, Peak peak, int nodes, int channels,
                        int sources, double mouthX, double mouthZ,
                        DrainageGraph.Ledger ledger) {}

    public WatershedTerrainSource(long seed, String expectedIdentity) {
        this(seed, expectedIdentity, false);
    }

    public WatershedTerrainSource(long seed, String expectedIdentity, boolean terrainAware) {
        this.seed = seed;
        baked = new BakedTerrainSource(seed, "");
        graph = new DrainageGraph(seed);
        micro = new Noise(seed ^ 0x7f2d4a08L);
        mountains = new MountainRelief(seed);
        riverProfile = terrainAware ? new RiverProfile(graph, this::naturalSurface) : null;
        identity = (terrainAware ? SOURCE_V2 + ":" + RECIPE_V2 : SOURCE + ":" + RECIPE)
            + ":" + Long.toUnsignedString(seed, 16)
            + ":" + baked.identity();
        if (expectedIdentity != null && !expectedIdentity.isEmpty()
                && !identity.equals(expectedIdentity)) {
            throw new IllegalStateException("Saved world's watershed terrain differs from installed version");
        }
        Peak highest = new Peak(0, 0, Double.NEGATIVE_INFINITY, Double.NEGATIVE_INFINITY);
        for (int x = -320; x <= 1600; x += 16) for (int z = -520; z <= 520; z += 16) {
            double height = sample(x, z).height();
            if (height > highest.localHeight())
                highest = new Peak(x, z, height, 62 + 3 * (height - SEA));
        }
        Peak coarse = highest;
        for (int x = (int) coarse.x() - 16; x <= coarse.x() + 16; x += 2)
            for (int z = (int) coarse.z() - 16; z <= coarse.z() + 16; z += 2) {
                double height = sample(x, z).height();
                if (height > highest.localHeight())
                    highest = new Peak(x, z, height, 62 + 3 * (height - SEA));
            }
        peak = highest;
    }

    @Override public String identity() { return identity; }
    public DrainageGraph graph() { return graph; }
    public double riverWaterLevel(int nodeId) {
        return riverProfile == null ? graph.baselineNode(nodeId).waterLevel()
            : riverProfile.nodeLevel(nodeId);
    }
    public Peak peak() { return peak; }
    public Audit audit() {
        return new Audit(identity, peak, graph.nodes().size(), graph.channelCount(), 3,
            graph.outlet().x(), graph.outlet().z(), graph.ledger());
    }

    @Override public Terrain.Column sample(double x, double z) {
        Terrain.Column learned = learned(x, z);
        double surface = naturalSurface(x, z, learned);
        double bend = DrainageGraph.bend(x, seed);
        double valleyDistance = Math.abs(z - bend);
        double inland = Math.min(1, Noise.smooth(-320, -40, x));
        inland *= 1 - Noise.smooth(1600, 1760, x);
        inland *= 1 - Noise.smooth(400, 520, valleyDistance);

        double water = surface < SEA ? SEA : Double.NaN;
        if (riverProfile != null && inland > .1) {
            DrainageGraph.Channel channel = graph.nearestChannel(x, z);
            if (channel != null) {
                double width = channel.width();
                double outer = width + 15 + .68 * Math.max(0, width - 4);
                if (channel.distance() < outer) {
                    double level = riverProfile.level(channel);
                    double depth = 2 + .32 * Math.max(0, width - 4);
                    double bed = level - depth;
                    double bank = level + 5;
                    double distance = channel.distance();
                    double target = distance <= width
                        ? bed + depth * Noise.smooth(0, width, distance)
                        : level + (bank - level) * Noise.smooth(width, outer, distance);
                    if (distance <= width || !besideHigherWater(x, z, target))
                        surface = Math.min(surface, target);
                    if (distance <= width && surface < level) water = level;
                }
            }
        } else if (inland > .1) {
            DrainageGraph.Channel channel = graph.nearestChannel(x, z);
            if (channel != null) {
            double width = channel.width();
            double outer = width + 15 + .68 * Math.max(0, width - 4);
            if (channel.distance() < outer) {
                double level = channel.waterLevel();
                double depth = 2 + .32 * Math.max(0, width - 4);
                double bed = level - depth;
                double bank = level + 5;
                double distance = channel.distance();
                double target = bed + (bank - bed) * Noise.smooth(width * .72, outer, distance);
                surface = Math.min(surface, target);
                if (channel.distance() <= width && surface < level)
                    water = level;
            }
            }
        }
        Landscape.Base base = new Landscape.Base(surface, learned.base().type(),
            learned.base().climate(), learned.base().landmark());
        return new Terrain.Column(surface, water, base);
    }

    private boolean besideHigherWater(double x, double z, double target) {
        for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++) {
            if (dx == 0 && dz == 0) continue;
            DrainageGraph.Channel neighbor = graph.nearestChannel(x + dx, z + dz);
            if (neighbor != null && neighbor.distance() <= neighbor.width()
                    && riverProfile.level(neighbor) > target) return true;
        }
        return false;
    }

    private Terrain.Column learned(double x, double z) {
        return baked.sample(-180 + .55 * x, 256 + .76 * z);
    }

    double naturalSurface(double x, double z) {
        return naturalSurface(x, z, learned(x, z));
    }

    private double naturalSurface(double x, double z, Terrain.Column learned) {
        double bend = DrainageGraph.bend(x, seed);
        // The baked model supplies spatial detail and biome climate; the explicit finite
        // mountain-to-sea envelope supplies scale and a guaranteed outlet for this exhibit.
        double t = Noise.clamp(x / 1600, 0, 1);
        double valleyDistance = Math.abs(z - bend);
        double smallDetail = 2.3 * micro.fbm(x / 95, z / 95, 3) * (1 - t);
        double inland = Math.min(1, Noise.smooth(-320, -40, x));
        inland *= 1 - Noise.smooth(1600, 1760, x);
        inland *= 1 - Noise.smooth(400, 520, valleyDistance);
        double mountainSurface = mountains.height(x, z, valleyDistance, learned.height())
            + smallDetail * (1 - .65 * t);
        return 48 + inland * (mountainSurface - 48);
    }
}
