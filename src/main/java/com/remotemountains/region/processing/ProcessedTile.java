package com.remotemountains.region.processing;

/** Row-major derived terrain; weight order is plain, hill, plateau, mountain. */
public record ProcessedTile(float[] heights, float[] weights, byte[] dominantTypes) {
    public static final byte PLAIN = 0, HILL = 1, PLATEAU = 2, MOUNTAIN = 3;
}
