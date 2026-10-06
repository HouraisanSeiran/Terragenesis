package com.remotemountains.hydrology3d;

/** Point is water-surface centerline; flows are block-cubed/second, storage is block-cubed. */
public record RiverNode(String id, Kind kind, Point3 point, double waterElevation,
        double hydraulicHead, double localInflow, double lakeCapacity,
        double lakeStorage, double lakeRelease) {
    public enum Kind { SOURCE, CONFLUENCE, SINKHOLE, RESURGENCE, LAKE, OUTLET }
    public RiverNode {
        if (id == null || !id.matches("[A-Za-z0-9_-]+") || kind == null || point == null
                || !Double.isFinite(waterElevation) || !Double.isFinite(hydraulicHead)
                || !Double.isFinite(localInflow) || localInflow < 0
                || !Double.isFinite(lakeCapacity) || lakeCapacity < 0
                || !Double.isFinite(lakeStorage) || lakeStorage < 0 || lakeStorage > lakeCapacity
                || !Double.isFinite(lakeRelease) || lakeRelease < 0)
            throw new IllegalArgumentException("Invalid river node");
        if (hydraulicHead < waterElevation - 1e-6)
            throw new IllegalArgumentException("Hydraulic head below water surface");
        if (Math.abs(point.y() - waterElevation) > 1e-6)
            throw new IllegalArgumentException("Node centerline Y differs from water elevation");
        if (kind != Kind.LAKE && (lakeCapacity != 0 || lakeStorage != 0 || lakeRelease != 0))
            throw new IllegalArgumentException("Storage is reserved for lakes");
    }
}
