package com.remotemountains.erosion3d;

/** Empirical contact erosion, not a hydrodynamic or paper-faithful solver. */
public final class Erosion3d {
    private Erosion3d() {
    }

    /** deltaTicks is an abstract solver interval, not elapsed seconds or Minecraft ticks. */
    public static ErosionResult apply(SurfaceSample surface, SweptPath path,
                                      ErosionConfig config, double deltaTicks, SedimentLedger ledger) {
        if (surface == null || path == null || config == null || ledger == null
                || !Double.isFinite(deltaTicks) || deltaTicks <= 0) {
            throw new IllegalArgumentException("Invalid erosion step");
        }

        double influence = path.sample(surface.position()).weight();
        double retreat = 0;
        if (surface.wettedContact() && surface.waterDepth() >= config.minWaterDepth()) {
            retreat = Math.min(config.maxRetreatPerStep(), deltaTicks * influence
                    * surface.erodibilityBlocksPerPaTick()
                    * Math.max(0, surface.shearPa() - surface.thresholdPa()));
        }
        if (!Double.isFinite(retreat)) {
            throw new IllegalArgumentException("Retreat overflow");
        }

        double removedVolume = surface.area() * retreat;
        ErosionResult result = new ErosionResult(surface.outwardNormal().multiply(-retreat),
                retreat, removedVolume, removedVolume * config.rockToSedimentFraction());
        ledger.add(result);
        return result;
    }
}
