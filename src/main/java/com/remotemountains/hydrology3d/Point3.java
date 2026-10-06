package com.remotemountains.hydrology3d;

public record Point3(double x, double y, double z) {
    public Point3 {
        if (!Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z))
            throw new IllegalArgumentException("Nonfinite river coordinate");
    }
    public double distance(Point3 other) {
        return Math.sqrt(Math.pow(x - other.x, 2) + Math.pow(y - other.y, 2) + Math.pow(z - other.z, 2));
    }
}
