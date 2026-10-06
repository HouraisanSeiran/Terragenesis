package com.remotemountains.core;

/** Validated persisted terrain mode and its user-facing capabilities. */
public record TerrainModeDescriptor(String source, String recipe, String scaleId,
        boolean supportsRegions, Preflight preflight) {
    public enum Preflight { NONE, INSTALL_ONLY, START_SERVICE }
}
