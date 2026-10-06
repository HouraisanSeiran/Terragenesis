package com.remotemountains.hydrology3d;

import java.util.List;

/** Open-channel centerline, never a pressurized conduit. */
public record RiverReach(String id, String from, String to, Mode mode, List<Point3> points) {
    public enum Mode { SURFACE, UNDERGROUND_OPEN }
    public RiverReach {
        if (id == null || !id.matches("[A-Za-z0-9_-]+") || from == null || to == null
                || !from.matches("[A-Za-z0-9_-]+") || !to.matches("[A-Za-z0-9_-]+") || from.equals(to)
                || mode == null || points == null || points.size() < 2)
            throw new IllegalArgumentException("Invalid river reach");
        points = List.copyOf(points);
        for (int i = 1; i < points.size(); i++)
            if (points.get(i - 1).distance(points.get(i)) <= 0)
                throw new IllegalArgumentException("Zero-length reach segment");
    }
    public double length() {
        double length = 0;
        for (int i = 1; i < points.size(); i++) length += points.get(i - 1).distance(points.get(i));
        return length;
    }
}
