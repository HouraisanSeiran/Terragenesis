package com.remotemountains.region.processing;

/** Independent candidate height changes blended by measured landform weights. */
final class LandformPolicies {
    private LandformPolicies() {}

    static float apply(float raw, float trend, float local, float plain, float hill,
            float plateau, float protection) {
        return raw + protection * (.90f * plain * (trend - raw)
            + (.18f * hill + .13f * plateau) * (local - raw));
    }
}
