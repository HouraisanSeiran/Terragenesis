package com.remotemountains.region;

/** Saved contract for chunk-aligned storage regions. */
public record RegionConfig(int chunks, String processing) {
    public static final RegionConfig DEFAULT = new RegionConfig(24, "none_v1");
    public static final int SPACING = 2, HALO = 64;
    public RegionConfig {
        if (chunks < 3 || chunks > 96 || chunks % 3 != 0 || !"none_v1".equals(processing))
            throw new IllegalArgumentException("Region chunks must be a multiple of 3 from 3 to 96; processing must be none_v1");
    }
    public int worldWidth() { return chunks * 16; }
    public int localWidth() { return worldWidth() / 3; }
    public int gridSize() { return (localWidth() + 2 * HALO) / SPACING + 1; }
}
