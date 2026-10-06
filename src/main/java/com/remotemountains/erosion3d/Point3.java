package com.remotemountains.erosion3d;

/** Three-dimensional position or displacement in world-block units. */
public record Point3(double x, double y, double z) {
    public Point3 {
        if (!Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z)) {
            throw new IllegalArgumentException("Nonfinite point");
        }
    }

    public Point3 add(Point3 other) {
        return new Point3(x + other.x, y + other.y, z + other.z);
    }

    public Point3 subtract(Point3 other) {
        return new Point3(x - other.x, y - other.y, z - other.z);
    }

    public Point3 multiply(double scalar) {
        return new Point3(x * scalar, y * scalar, z * scalar);
    }

    public double dot(Point3 other) {
        return x * other.x + y * other.y + z * other.z;
    }

    public Point3 cross(Point3 other) {
        return new Point3(y * other.z - z * other.y,
                z * other.x - x * other.z, x * other.y - y * other.x);
    }

    public double length() {
        return Math.sqrt(dot(this));
    }

    public Point3 normalized() {
        double length = length();
        if (length <= 1e-12) {
            throw new IllegalArgumentException("Zero direction");
        }
        return multiply(1 / length);
    }
}
