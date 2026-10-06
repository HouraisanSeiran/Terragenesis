package com.remotemountains.hydrology3d;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.ArrayList;
import java.util.Collections;

public final class RiverNetworkVerification {
    private static RiverNode node(String id, RiverNode.Kind kind, double x, double y, double z,
            double q, double capacity, double stored, double release) {
        return new RiverNode(id, kind, new Point3(x, y, z), y, y, q, capacity, stored, release);
    }

    private static RiverReach edge(String id, RiverNode from, RiverNode to, RiverReach.Mode mode) {
        return new RiverReach(id, from.id(), to.id(), mode, List.of(from.point(), to.point()));
    }

    public static void main(String[] args) throws Exception {
        RiverNode a = node("source_a", RiverNode.Kind.SOURCE, -20, 100, 0, 4, 0, 0, 0);
        RiverNode b = node("source_b", RiverNode.Kind.SOURCE, -20, 96, 10, 3, 0, 0, 0);
        RiverNode confluence = node("confluence", RiverNode.Kind.CONFLUENCE, 0, 90, 0, 0, 0, 0, 0);
        RiverNode sink = node("sinkhole", RiverNode.Kind.SINKHOLE, -15, 85, -15, 2, 0, 0, 0);
        RiverNode resurgence = node("resurgence", RiverNode.Kind.RESURGENCE, 5, 75, -10, 0, 0, 0, 0);
        RiverNode join = node("main_join", RiverNode.Kind.CONFLUENCE, 15, 70, 0, 0, 0, 0, 0);
        RiverNode lakeSource = node("lake_source", RiverNode.Kind.SOURCE, -10, 86, 25, 1, 0, 0, 0);
        RiverNode lake = node("lake", RiverNode.Kind.LAKE, 5, 80, 25, 0, 8, 3, .5);
        RiverNode lakeJoin = node("lake_join", RiverNode.Kind.CONFLUENCE, 25, 60, 0, 0, 0, 0, 0);
        RiverNode outlet = node("outlet", RiverNode.Kind.OUTLET, 45, 50, 0, 0, 0, 0, 0);
        List<RiverNode> nodes = List.of(a, b, confluence, sink, resurgence, join, lakeSource, lake, lakeJoin, outlet);
        List<RiverReach> reaches = List.of(
            edge("a_to_confluence", a, confluence, RiverReach.Mode.SURFACE),
            edge("b_to_confluence", b, confluence, RiverReach.Mode.SURFACE),
            edge("main", confluence, join, RiverReach.Mode.SURFACE),
            edge("cave", sink, resurgence, RiverReach.Mode.UNDERGROUND_OPEN),
            edge("resurgence_join", resurgence, join, RiverReach.Mode.SURFACE),
            edge("join_lake", join, lakeJoin, RiverReach.Mode.SURFACE),
            edge("lake_in", lakeSource, lake, RiverReach.Mode.SURFACE),
            edge("lake_out", lake, lakeJoin, RiverReach.Mode.SURFACE),
            edge("outflow", lakeJoin, outlet, RiverReach.Mode.SURFACE));
        RiverConfig config = new RiverConfig(1.8, .45, 1, 32, 2, 2, 1);
        RiverNetwork network = new RiverNetwork(nodes, reaches, config);
        ArrayList<RiverNode> reorderedNodes = new ArrayList<>(nodes);
        ArrayList<RiverReach> reorderedReaches = new ArrayList<>(reaches);
        Collections.reverse(reorderedNodes);
        Collections.reverse(reorderedReaches);
        if (!RiverNetworkJson.write(network).equals(RiverNetworkJson.write(
                new RiverNetwork(reorderedNodes, reorderedReaches, config))))
            throw new AssertionError("Network export depends on input order");
        near(network.flow("confluence").incoming(), 7);
        near(network.flow("main_join").outgoing(), 9);
        near(network.flow("lake").storageAfter(), 4);
        near(network.flow("lake").outgoing(), .5);
        near(network.flow("outlet").incoming(), 9.5);
        near(network.flow("lake").incoming() * config.stepSeconds() + lake.lakeStorage(),
            network.flow("lake").outgoing() * config.stepSeconds() + network.flow("lake").storageAfter());
        if (network.flow("main_join").width() <= network.flow("confluence").width())
            throw new AssertionError("Confluence failed to widen");
        RiverConfig oneSecond = new RiverConfig(1.8, .45, 1, 32, 2, 1, 1);
        RiverNetwork faster = new RiverNetwork(nodes, reaches, oneSecond);
        near(faster.flow("lake").storageAfter(), 3.5);
        near(faster.flow("lake").outgoing(), .5);
        reject(() -> new RiverNetwork(nodes, List.of(edge("reverse", confluence, a, RiverReach.Mode.SURFACE)), config));
        RiverNode c1 = node("cycle_1", RiverNode.Kind.CONFLUENCE, 0, 50, 0, 0, 0, 0, 0);
        RiverNode c2 = node("cycle_2", RiverNode.Kind.CONFLUENCE, 1, 50, 0, 0, 0, 0, 0);
        try {
            new RiverNetwork(List.of(c1, c2), List.of(edge("cycle1", c1, c2, RiverReach.Mode.SURFACE),
                edge("cycle2", c2, c1, RiverReach.Mode.SURFACE)), config);
            throw new AssertionError("Cycle accepted");
        } catch (IllegalArgumentException expected) {
            if (!expected.getMessage().contains("cycle")) throw expected;
        }
        RiverNode terminalLake = node("terminal_lake", RiverNode.Kind.LAKE, 0, 70, 0, 1, 8, 0, 0);
        RiverNetwork held = new RiverNetwork(List.of(terminalLake), List.of(), config);
        near(held.flow("terminal_lake").storageAfter(), 2);
        reject(() -> new RiverNetwork(List.of(node("overflow_lake", RiverNode.Kind.LAKE,
            0, 70, 0, 10, 1, 0, 0)), List.of(), config));
        reject(() -> new RiverConfig(1, .4, 1, 2, 0, 0, 1));
        // This export is synthetic graph geometry, not a Minecraft world or physical survey.
        Path output = Path.of("verification", "hydrology3d", "synthetic_network.json");
        Files.createDirectories(output.getParent());
        Files.writeString(output, RiverNetworkJson.write(network));
        System.out.println("PASS hydrology3d graph, junctions, cave, lake budgets, invalid inputs; " + output);
    }

    private static void near(double actual, double expected) {
        if (!Double.isFinite(actual) || Math.abs(actual - expected) > 1e-9)
            throw new AssertionError(actual + " != " + expected);
    }

    private static void reject(Runnable action) {
        try { action.run(); throw new AssertionError("Invalid network accepted"); }
        catch (IllegalArgumentException expected) { }
    }
}
