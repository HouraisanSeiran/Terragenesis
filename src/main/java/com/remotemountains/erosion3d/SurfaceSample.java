package com.remotemountains.erosion3d;

/** Position and depth are blocks, area is blocks squared, shear and threshold are Pa.
 * Erodibility is blocks per Pa per abstract solver tick, not per real second.
 * Wetted contact and shear come from a separate flow/contact model.
 */
public record SurfaceSample(Point3 position, Point3 outwardNormal, double area,
                            boolean wettedContact, double waterDepth, double shearPa,
                            double thresholdPa, double erodibilityBlocksPerPaTick) {
    public SurfaceSample {
        if (position == null || outwardNormal == null || !Double.isFinite(area) || area <= 0
                || !Double.isFinite(waterDepth) || waterDepth < 0
                || !Double.isFinite(shearPa) || shearPa < 0
                || !Double.isFinite(thresholdPa) || thresholdPa < 0
                || !Double.isFinite(erodibilityBlocksPerPaTick) || erodibilityBlocksPerPaTick < 0) {
            throw new IllegalArgumentException("Invalid surface sample");
        }
        outwardNormal = outwardNormal.normalized();
    }
}
