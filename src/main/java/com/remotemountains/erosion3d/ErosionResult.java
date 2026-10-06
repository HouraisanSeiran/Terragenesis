package com.remotemountains.erosion3d;

/** VDM delta and retreat are blocks; volumes are solid-equivalent blocks cubed. */
public record ErosionResult(Point3 delta, double retreat, double removedVolume, double sedimentVolume) {}
