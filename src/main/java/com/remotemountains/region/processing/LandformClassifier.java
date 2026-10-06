package com.remotemountains.region.processing;

/** Converts measured trend, relief, and slope into four continuous weights. */
final class LandformClassifier {
    private LandformClassifier() {}

    static void classify(float raw, RegionFeatures features, int x, int z, int width, int height,
            float[] weights, byte[] types) {
        int i = z * width + x;
        float[] trend = features.trend();
        float relief = (float) Math.sqrt(Math.max(0,
            features.squaredTrend()[i] - trend[i] * trend[i]));
        float high = RegionProcessor.smooth(220, 290, trend[i]);
        float tx = (trend[z * width + Math.min(x + 1, width - 1)]
                - trend[z * width + Math.max(x - 1, 0)]) / (x == 0 || x == width - 1 ? 2 : 4);
        float tz = (trend[Math.min(z + 1, height - 1) * width + x]
                - trend[Math.max(z - 1, 0) * width + x]) / (z == 0 || z == height - 1 ? 2 : 4);
        float trendSlope = (float) Math.hypot(tx, tz);
        float rugged = Math.max(RegionProcessor.smooth(9, 28, relief),
            Math.max(RegionProcessor.smooth(.3f, .9f, trendSlope),
                RegionProcessor.smooth(10, 24, raw - trend[i]) * .85f));
        weights[4 * i] = (1 - high) * (1 - rugged);
        weights[4 * i + 1] = (1 - high) * rugged;
        weights[4 * i + 2] = high * (1 - rugged);
        weights[4 * i + 3] = high * rugged;
        int best = 0;
        for (int k = 1; k < 4; k++) {
            if (weights[4 * i + k] > weights[4 * i + best]) best = k;
        }
        types[i] = (byte) best;
    }
}
