package com.remotemountains.watershed;

import com.remotemountains.core.Noise;

/** Seeded mountain-scale ridges layered over the finite mountain-to-sea grade. */
public final class MountainRelief {
    private final Noise ridges;
    private final Noise peaks;

    public MountainRelief(long seed) {
        ridges = new Noise(seed ^ 0x148d93c2L);
        peaks = new Noise(seed ^ 0x525bd771L);
    }

    public double height(double x, double z, double valleyDistance, double learnedHeight) {
        double along = Noise.clamp(x / 1600, 0, 1);
        double headwaterRise = Noise.smooth(-320, 20, x);
        double grade = 198 * headwaterRise * Math.pow(1 - along, 1.45);
        double flank = Noise.smooth(42, 300, valleyDistance);
        double spine = Math.pow(Math.abs(ridges.at(x / 245, z / 108)), 1.55);
        double brokenRidge = Math.pow(Math.abs(ridges.at(x / 116 + 9, z / 170 - 4)), 2.0);
        double mountain = (15 + 29 * spine + 16 * brokenRidge) * flank * (1 - .78 * along);
        double summit = 14 * Math.pow(Math.max(0, peaks.at(x / 180 - 3, z / 155 + 2)), 2)
            * flank * (1 - along);
        // Saturate the baked model smoothly, retaining its relative relief.
        double modelDetail = 21 * Math.tanh((learnedHeight - 104) / 20);
        return 72 + grade + mountain + summit + modelDetail * (1 - .65 * along);
    }
}
