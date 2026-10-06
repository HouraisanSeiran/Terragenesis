package com.remotemountains.core;

import java.nio.file.Path;

/** Explicit preparation contract; sampling a missing artifact must not prepare it. */
public interface TerrainPreparation {
    Path prepareRegion(int regionX, int regionZ);

    void prepareBounds(int minWorldX, int minWorldZ,
                       int maxWorldXInclusive, int maxWorldZInclusive);
}
