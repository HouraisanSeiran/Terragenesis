package com.remotemountains.watershed;

import java.util.List;
import java.util.function.ToDoubleBiFunction;

/** Immutable water elevations constrained by the untouched terrain beside every reach. */
final class RiverProfile {
    private static final double BANK_CLEARANCE = 1.5;
    private static final double MIN_DROP = .002;
    private final double[] levels;
    private final List<DrainageGraph.Node> nodes;
    private final double[][] reachLevels;

    RiverProfile(DrainageGraph graph, ToDoubleBiFunction<Double, Double> naturalSurface) {
        nodes = graph.nodes();
        levels = new double[nodes.size()];
        reachLevels = new double[nodes.size()][];
        double[][] caps = new double[nodes.size()][];
        for (DrainageGraph.Node node : nodes) levels[node.id()] = node.waterLevel();

        for (DrainageGraph.Node node : nodes) {
            if (!node.visible() || node.downstream() < 0) continue;
            DrainageGraph.Node next = nodes.get(node.downstream());
            double dx = next.x() - node.x(), dz = next.z() - node.z();
            double length = Math.hypot(dx, dz);
            double nx = -dz / length, nz = dx / length;
            int steps = Math.max(1, (int) Math.ceil(length));
            double[] samples = new double[steps + 1];
            for (int step = 0; step <= steps; step++) {
                double t = step / (double) steps;
                double x = node.x() + t * dx, z = node.z() + t * dz;
                double q = node.discharge() + t * (next.discharge() - node.discharge());
                double width = 4 + .25 * Math.sqrt(q);
                double outer = width + 15 + .68 * Math.max(0, width - 4);
                double cap = Double.POSITIVE_INFINITY;
                for (double radius : new double[] {width + .25, width + .5, width + 1,
                        width + 2, (width + outer) * .5, outer}) {
                    cap = Math.min(cap, naturalSurface.applyAsDouble(x + nx * radius, z + nz * radius));
                    cap = Math.min(cap, naturalSurface.applyAsDouble(x - nx * radius, z - nz * radius));
                }
                samples[step] = Math.max(WatershedTerrainSource.SEA, cap - BANK_CLEARANCE);
            }
            caps[node.id()] = samples;
            levels[node.id()] = Math.min(levels[node.id()], samples[0]);
            levels[next.id()] = Math.min(levels[next.id()], samples[steps]);
        }

        // Flow constraints propagate through junctions until every reach drains downhill.
        boolean changed;
        do {
            changed = false;
            for (DrainageGraph.Node node : nodes) {
                if (!node.visible() || node.downstream() < 0) continue;
                int downstream = node.downstream();
                double[] samples = caps[node.id()];
                double lower = levels[node.id()];
                for (int i = 1; i < samples.length; i++) lower = Math.min(lower - MIN_DROP, samples[i]);
                lower = Math.max(WatershedTerrainSource.SEA, lower);
                if (lower < levels[downstream]) {
                    levels[downstream] = lower;
                    changed = true;
                }
            }
        } while (changed);

        for (DrainageGraph.Node node : nodes) {
            double[] samples = caps[node.id()];
            if (samples == null) continue;
            double[] profile = new double[samples.length];
            profile[0] = levels[node.id()];
            double end = levels[node.downstream()];
            for (int i = 1; i < samples.length; i++)
                profile[i] = Math.max(WatershedTerrainSource.SEA,
                    Math.min(profile[i - 1] - MIN_DROP, samples[i]));
            for (int i = 0; i < profile.length; i++) profile[i] = Math.min(profile[i],
                levels[node.id()] + (end - levels[node.id()]) * i / (profile.length - 1));
            profile[profile.length - 1] = end;
            reachLevels[node.id()] = profile;
        }
    }

    double level(DrainageGraph.Channel channel) {
        double[] profile = reachLevels[channel.fromNode()];
        if (profile == null) return channel.waterLevel();
        DrainageGraph.Node from = nodes.get(channel.fromNode());
        DrainageGraph.Node to = nodes.get(channel.toNode());
        double dx = to.x() - from.x(), dz = to.z() - from.z();
        double t = ((channel.x() - from.x()) * dx + (channel.z() - from.z()) * dz)
            / (dx * dx + dz * dz);
        double index = Math.max(0, Math.min(profile.length - 1, t * (profile.length - 1)));
        int i = Math.min(profile.length - 2, (int) index);
        return profile[i] + (index - i) * (profile[i + 1] - profile[i]);
    }

    double nodeLevel(int id) { return levels[id]; }
}
