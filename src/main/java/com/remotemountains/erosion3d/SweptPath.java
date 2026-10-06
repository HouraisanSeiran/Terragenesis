package com.remotemountains.erosion3d;

import java.util.List;

/** Finite block-space 3D corridor. Its weight is not a water solution. */
public final class SweptPath {
    public record Sample(Point3 nearest, Point3 tangent, Point3 across, Point3 up,
                         double distance, double weight, int segment) {
    }
    private final List<Point3> points;
    private final double radius;

    public SweptPath(List<Point3> points, double radius) {
        if (points == null || points.size() < 2 || !Double.isFinite(radius) || radius <= 0) {
            throw new IllegalArgumentException("Invalid path or radius");
        }
        this.points = List.copyOf(points);
        for (int i = 1; i < points.size(); i++) {
            if (points.get(i).subtract(points.get(i - 1)).length() <= 1e-9) {
                throw new IllegalArgumentException("Degenerate path segment");
            }
        }
        this.radius = radius;
    }

    public Sample sample(Point3 position) {
        double nearestDistance = Double.POSITIVE_INFINITY;
        Point3 nearest = null;
        Point3 tangent = null;
        int segment = -1;
        for (int i = 0; i < points.size() - 1; i++) {
            Point3 start = points.get(i);
            Point3 vector = points.get(i + 1).subtract(start);
            double t = Math.max(0, Math.min(1, position.subtract(start).dot(vector) / vector.dot(vector)));
            Point3 projected = start.add(vector.multiply(t));
            double distance = position.subtract(projected).length();
            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearest = projected;
                tangent = vector.normalized();
                segment = i;
            }
        }
        Point3 reference = Math.abs(tangent.y()) < .9 ? new Point3(0, 1, 0) : new Point3(1, 0, 0);
        Point3 across = reference.cross(tangent).normalized();
        Point3 up = tangent.cross(across).normalized();
        double t = Math.max(0, Math.min(1, 1 - nearestDistance / radius));
        return new Sample(nearest, tangent, across, up, nearestDistance,
                t * t * (3 - 2 * t), segment);
    }
}
