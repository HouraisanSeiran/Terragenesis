package com.remotemountains.erosion3d;

/** Depth and step retreat are in blocks; time uses abstract solver ticks, not seconds. */
public record ErosionConfig(double minWaterDepth, double maxRetreatPerStep, double rockToSedimentFraction) {
    public ErosionConfig {
        if (!Double.isFinite(minWaterDepth) || minWaterDepth < 0
                || !Double.isFinite(maxRetreatPerStep) || maxRetreatPerStep <= 0
                || !Double.isFinite(rockToSedimentFraction) || rockToSedimentFraction < 0
                || rockToSedimentFraction > 1) {
            throw new IllegalArgumentException("Invalid erosion config");
        }
    }
}
