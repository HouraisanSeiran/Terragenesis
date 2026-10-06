package com.remotemountains.region.processing;

/** Bounded separable Gaussian with clamped outer edge. */
final class GaussianFilter {
    private GaussianFilter() {}
    static float[] apply(float[] input, int width, int height, double sigma, int radius) {
        double[] kernel = new double[2 * radius + 1];
        double total = 0;
        for (int d = -radius; d <= radius; d++) total += kernel[d + radius] = Math.exp(-d * d / (2 * sigma * sigma));
        for (int k = 0; k < kernel.length; k++) kernel[k] /= total;
        float[] temp = new float[input.length], out = new float[input.length];
        for (int z = 0; z < height; z++) for (int x = 0; x < width; x++) {
            double value = 0;
            for (int d = -radius; d <= radius; d++)
                value += kernel[d + radius] * input[z * width + clamp(x + d, width)];
            temp[z * width + x] = (float) value;
        }
        for (int z = 0; z < height; z++) for (int x = 0; x < width; x++) {
            double value = 0;
            for (int d = -radius; d <= radius; d++)
                value += kernel[d + radius] * temp[clamp(z + d, height) * width + x];
            out[z * width + x] = (float) value;
        }
        return out;
    }
    private static int clamp(int x, int size) { return Math.max(0, Math.min(size - 1, x)); }
}
