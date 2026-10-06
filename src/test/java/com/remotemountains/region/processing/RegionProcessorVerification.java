package com.remotemountains.region.processing;

import java.util.Arrays;

public final class RegionProcessorVerification {
    public static void main(String[] args) {
        int n = 160;
        float[] raw = new float[n * n], mask = new float[raw.length];
        for (int z = 0; z < n; z++) for (int x = 0; x < n; x++) {
            double wave = 3 * Math.sin(x * .9) * Math.sin(z * .8);
            raw[z * n + x] = (float) (76 + wave);
            if (x < 35) raw[z * n + x] = 57 + (float) wave;
            if (x > 100) raw[z * n + x] = (float) (130 + 90 * Math.exp(-((x - 128) * (x - 128)
                    + (z - 80) * (z - 80)) / 180.0) + wave);
        }
        mask[70 * n + 70] = 1;
        float[] saved = raw.clone(), savedMask = mask.clone();
        ProcessedTile processed = RegionProcessor.process(raw, n, n, -320, 400, 12345, mask);
        check(Arrays.equals(raw, saved) && Arrays.equals(mask, savedMask), "input changed");
        double before = 0, after = 0;
        for (int z = 45; z < 110; z++) for (int x = 45; x < 95; x++) {
            int i = z * n + x;
            before += Math.abs(raw[i] - raw[i + 1]);
            after += Math.abs(processed.heights()[i] - processed.heights()[i + 1]);
        }
        check(after < before * .55, "plain roughness not reduced");
        check(processed.heights()[80 * n + 128] > raw[80 * n + 128] - 1, "peak lowered");
        check(processed.heights()[70 * n + 70] == raw[70 * n + 70], "mask not respected");
        for (int z = 30; z < 130; z++) for (int x = 3; x < 25; x++)
            check(processed.heights()[z * n + x] == raw[z * n + x], "seabed changed");
        for (int i = 0; i < raw.length; i++) {
            float sum = 0;
            for (int k = 0; k < 4; k++) {
                float w = processed.weights()[4 * i + k];
                check(Float.isFinite(w) && w >= 0 && w <= 1, "invalid weight");
                sum += w;
            }
            check(Math.abs(sum - 1) < 1e-5, "weights not normalized");
        }
        float[] window = new float[112 * 112];
        for (int z = 0; z < 112; z++) System.arraycopy(raw, (z + 20) * n + 20, window, z * 112, 112);
        ProcessedTile smaller = RegionProcessor.process(window, 112, 112, -280, 440, 12345, null);
        ProcessedTile full = RegionProcessor.process(raw, n, n, -320, 400, 12345, null);
        for (int z = 25; z < 87; z++) for (int x = 25; x < 87; x++) {
            int a = (z + 20) * n + x + 20, b = z * 112 + x;
            check(Math.abs(full.heights()[a] - smaller.heights()[b]) < 1e-4, "window seam");
            for (int k = 0; k < 4; k++)
                check(Math.abs(full.weights()[4 * a + k] - smaller.weights()[4 * b + k]) < 1e-5, "weight seam");
        }
        System.out.println("Regional processing verification passed");
    }
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
}
