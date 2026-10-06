package com.remotemountains.canyon;

import com.remotemountains.cliff.CliffSettings;
import com.remotemountains.core.Noise;

/** Reproducible inclinations for separated canyon bands. */
public enum CanyonCliffStyle {
    MIXED, SINGLE;

    public static CanyonCliffStyle of(boolean mixed) { return mixed ? MIXED : SINGLE; }

    public CliffSettings settings(long seed, int index) {
        long key = Noise.mix(seed ^ (0x647e6381L + index * 0x9E3779B97F4A7C15L));
        double angle = this == SINGLE ? 76 : switch (index % 3) {
            case 0 -> 64 + 6 * Noise.unit(key);
            case 1 -> 74 + 7 * Noise.unit(key);
            default -> 84 + 6 * Noise.unit(key);
        };
        // Ordinary cliff lean keeps the crest above its own slope. Overhangs are optional.
        return new CliffSettings(key, angle, 1, 192, .105);
    }
}
