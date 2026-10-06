package com.remotemountains.region;

import com.remotemountains.core.Landform;
import com.remotemountains.core.Noise;

/** Seeded, irregular logical landforms independent of the storage-region grid. */
public final class RegionLandformLayout {
    public static final String VERSION = "landform_layout_v1";
    private static final int SITE_SPACING = 2304;
    private static final double TRANSITION = 300;
    private static final int SEARCH_RADIUS = 3;
    private final long seed;
    private final Noise warp;

    public record Sample(Landform primary, Landform secondary, double primaryWeight) {
        public double secondaryWeight() { return 1 - primaryWeight; }
    }

    public RegionLandformLayout(long seed) {
        this.seed = seed;
        this.warp = new Noise(seed ^ 0x6D8A93E7B41C275FL);
    }

    /** Coordinates are Minecraft world blocks, including at negative positions. */
    public Sample at(double worldX, double worldZ) {
        double x = worldX + 190 * warp.fbm(worldX / 1150, worldZ / 1150, 3);
        double z = worldZ + 190 * warp.fbm(worldX / 1150 + 43, worldZ / 1150 - 29, 3);
        int gx = (int) Math.floor(x / SITE_SPACING);
        int gz = (int) Math.floor(z / SITE_SPACING);
        double best = Double.POSITIVE_INFINITY, next = Double.POSITIVE_INFINITY;
        Landform first = null, second = null;
        for (int dz = -SEARCH_RADIUS; dz <= SEARCH_RADIUS; dz++) for (int dx = -SEARCH_RADIUS; dx <= SEARCH_RADIUS; dx++) {
            long h = Noise.hash(seed, gx + dx, gz + dz);
            double score = score(x, z, gx + dx, gz + dz, h);
            if (score < best) {
                best = score;
                first = type(h);
            }
        }
        for (int dz = -SEARCH_RADIUS; dz <= SEARCH_RADIUS; dz++) for (int dx = -SEARCH_RADIUS; dx <= SEARCH_RADIUS; dx++) {
            long h = Noise.hash(seed, gx + dx, gz + dz);
            Landform type = type(h);
            if (type == first) continue;
            double score = score(x, z, gx + dx, gz + dz, h);
            if (score < next) {
                next = score;
                second = type;
            }
        }
        double weight = .5 + .5 * Noise.smooth(0, TRANSITION, (next - best) / SITE_SPACING);
        return new Sample(first, second == null ? first : second, weight);
    }

    private static Landform type(long hash) {
        return Landform.values()[(int) Math.floorMod(Noise.mix(hash + 3), Landform.values().length)];
    }

    private static double score(double x, double z, int gridX, int gridZ, long hash) {
        double sx = (gridX + .5 + (Noise.unit(hash) - .5) * .65) * SITE_SPACING;
        double sz = (gridZ + .5 + (Noise.unit(hash + 1) - .5) * .65) * SITE_SPACING;
        double radius = (.38 + .22 * Noise.unit(hash + 2)) * SITE_SPACING;
        double dx = x - sx, dz = z - sz;
        return dx * dx + dz * dz - radius * radius;
    }
}
