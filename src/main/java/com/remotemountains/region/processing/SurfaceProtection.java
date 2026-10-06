package com.remotemountains.region.processing;

/** Coast, waterline, external mask, and isolated peak protection. */
final class SurfaceProtection {
    private SurfaceProtection() {}

    static float blend(float raw, float trend, float coast, float external) {
        float protect = Math.max(external,
            Math.max(RegionProcessor.smooth(.01f, .22f, coast) * .85f,
                1 - RegionProcessor.smooth(ProcessingConfig.SEA_LEVEL + 1,
                    ProcessingConfig.SEA_LEVEL + 9, raw)));
        float blend = 1 - protect;
        float peakProtection = RegionProcessor.smooth(8, 26, raw - trend);
        return (1 - peakProtection) * blend;
    }
}
