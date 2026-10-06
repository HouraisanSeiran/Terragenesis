package com.remotemountains.region.processing;

/** Deterministic processing of absolute Minecraft Y sampled every two world blocks. */
public final class RegionProcessor {
    public static final String ALGORITHM_ID = ProcessingConfig.ID;
    public static final int REQUIRED_HALO_SAMPLES = ProcessingConfig.HALO_SAMPLES;

    private RegionProcessor() {}

    /**
     * Returns new arrays; inputs remain unchanged. Interior results require 25 halo samples.
     * The widest filter has sigma 8 and radius 24; its central-difference slope extends
     * support by one sample. Edge clamping affects only the supplied halo.
     */
    public static ProcessedTile process(float[] rawHeight, int width, int height,
            int originWorldX, int originWorldZ, long seed, float[] protectionMask) {
        if (rawHeight == null || width < 2 || height < 2 || (long) width * height != rawHeight.length
                || protectionMask != null && protectionMask.length != rawHeight.length)
            throw new IllegalArgumentException("Invalid grid or protection mask");
        for (int i = 0; i < rawHeight.length; i++)
            if (!Float.isFinite(rawHeight[i]) || protectionMask != null
                    && (!Float.isFinite(protectionMask[i]) || protectionMask[i] < 0 || protectionMask[i] > 1))
                throw new IllegalArgumentException("Invalid sample at " + i);
        RegionFeatures features = RegionFeatures.from(rawHeight, width, height);
        float[] trend = features.trend();
        float[] out = new float[rawHeight.length];
        float[] weights = new float[rawHeight.length * 4];
        byte[] type = new byte[rawHeight.length];
        for (int z = 0; z < height; z++) for (int x = 0; x < width; x++) {
            int i = z * width + x;
            float y = rawHeight[i];
            LandformClassifier.classify(y, features, x, z, width, height, weights, type);
            float external = protectionMask == null ? 0 : protectionMask[i];
            float protection = SurfaceProtection.blend(y, trend[i], features.coast()[i], external);
            out[i] = LandformPolicies.apply(y, trend[i], features.local()[i],
                weights[4 * i], weights[4 * i + 1], weights[4 * i + 2], protection);
        }
        return new ProcessedTile(out, weights, type);
    }

    static float smooth(float lo, float hi, float x) {
        float t = Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
        return t * t * (3 - 2 * t);
    }
}
