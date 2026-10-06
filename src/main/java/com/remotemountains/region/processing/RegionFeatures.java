package com.remotemountains.region.processing;

/** Shared elevation, relief, slope, and coast measurements for a processing tile. */
record RegionFeatures(float[] trend, float[] local, float[] squaredTrend, float[] coast) {
    static RegionFeatures from(float[] rawHeight, int width, int height) {
        float[] trend = GaussianFilter.apply(rawHeight, width, height, 8, 24);
        float[] local = GaussianFilter.apply(rawHeight, width, height, 2, 6);
        float[] squared = new float[rawHeight.length];
        for (int i = 0; i < squared.length; i++) squared[i] = rawHeight[i] * rawHeight[i];
        float[] squaredTrend = GaussianFilter.apply(squared, width, height, 8, 24);
        float[] wet = new float[rawHeight.length];
        for (int i = 0; i < wet.length; i++) wet[i] = rawHeight[i] <= ProcessingConfig.SEA_LEVEL ? 1 : 0;
        float[] coast = GaussianFilter.apply(wet, width, height, 3, 9);
        return new RegionFeatures(trend, local, squaredTrend, coast);
    }
}
