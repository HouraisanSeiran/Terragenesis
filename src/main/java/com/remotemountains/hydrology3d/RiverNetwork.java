package com.remotemountains.hydrology3d;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;

/** A bounded DAG of open-channel flow; XZ crossings remain independent graph edges. */
public final class RiverNetwork {
    public record Flow(double incoming, double outgoing, double storageAfter, double width) {}
    private final Map<String, RiverNode> nodes;
    private final List<RiverReach> reaches;
    private final Map<String, Flow> flows;
    private final Map<String, Double> reachFlows;

    public RiverNetwork(List<RiverNode> nodeList, List<RiverReach> reachList, RiverConfig config) {
        Objects.requireNonNull(config);
        Map<String, RiverNode> graph = indexNodes(nodeList);
        List<RiverReach> edges = new ArrayList<>(reachList);
        edges.sort(Comparator.comparing(RiverReach::id));
        Map<String, Integer> indegree = new HashMap<>();
        Map<String, Integer> outdegree = new HashMap<>();
        Map<String, List<RiverReach>> outgoing = new HashMap<>();
        for (RiverNode node : graph.values()) {
            indegree.put(node.id(), 0);
            outdegree.put(node.id(), 0);
        }
        validateEdges(graph, edges, indegree, outdegree, outgoing);
        validateNodeDegrees(graph, indegree, outdegree);
        Map<String, Double> edgeQ = new TreeMap<>();
        Map<String, Flow> solved = solve(graph, indegree, outdegree, outgoing, edgeQ, config);
        nodes = Map.copyOf(graph);
        reaches = List.copyOf(edges);
        flows = Map.copyOf(solved);
        reachFlows = Map.copyOf(edgeQ);
    }

    private static Map<String, RiverNode> indexNodes(List<RiverNode> nodeList) {
        Map<String, RiverNode> graph = new TreeMap<>();
        for (RiverNode node : nodeList) {
            if (graph.putIfAbsent(node.id(), node) != null)
                throw new IllegalArgumentException("Duplicate node " + node.id());
        }
        return graph;
    }

    private static void validateEdges(Map<String, RiverNode> graph, List<RiverReach> edges,
            Map<String, Integer> indegree, Map<String, Integer> outdegree,
            Map<String, List<RiverReach>> outgoing) {
        Set<String> ids = new HashSet<>();
        for (RiverReach edge : edges) {
            if (!ids.add(edge.id())) {
                throw new IllegalArgumentException("Duplicate reach " + edge.id());
            }
            RiverNode from = graph.get(edge.from());
            RiverNode to = graph.get(edge.to());
            if (from == null || to == null) {
                throw new IllegalArgumentException("Unknown reach endpoint");
            }
            if (!edge.points().getFirst().equals(from.point()) || !edge.points().getLast().equals(to.point()))
                throw new IllegalArgumentException("Reach endpoint is not shared node position");
            if (from.waterElevation() + 1e-6 < to.waterElevation() || from.hydraulicHead() + 1e-6 < to.hydraulicHead())
                throw new IllegalArgumentException("Uphill water surface or hydraulic head");
            for (int i = 1; i < edge.points().size(); i++) {
                if (edge.points().get(i).y() > edge.points().get(i - 1).y() + 1e-6) {
                    throw new IllegalArgumentException("Rising open-channel route");
                }
            }
            if (edge.mode() == RiverReach.Mode.UNDERGROUND_OPEN) {
                for (Point3 point : edge.points()) {
                    if (point.y() > from.waterElevation() + 1e-6) {
                        throw new IllegalArgumentException("Underground route rises above upstream water");
                    }
                }
            }
            indegree.merge(to.id(), 1, Integer::sum);
            outdegree.merge(from.id(), 1, Integer::sum);
            outgoing.computeIfAbsent(from.id(), ignored -> new ArrayList<>()).add(edge);
        }
    }

    private static void validateNodeDegrees(Map<String, RiverNode> graph,
            Map<String, Integer> indegree, Map<String, Integer> outdegree) {
        for (RiverNode node : graph.values()) {
            if (node.kind() == RiverNode.Kind.SOURCE && indegree.get(node.id()) != 0) {
                throw new IllegalArgumentException("Source has incoming edge");
            }
            if (node.kind() == RiverNode.Kind.OUTLET && outdegree.get(node.id()) != 0) {
                throw new IllegalArgumentException("Outlet has outgoing edge");
            }
            if (outdegree.get(node.id()) > 1) {
                throw new IllegalArgumentException("Divergence needs explicit split fractions");
            }
            if (outdegree.get(node.id()) == 0 && node.kind() != RiverNode.Kind.OUTLET
                    && node.kind() != RiverNode.Kind.LAKE) {
                throw new IllegalArgumentException("Flow terminates without an outlet");
            }
        }
    }

    private static Map<String, Flow> solve(Map<String, RiverNode> graph,
            Map<String, Integer> indegree, Map<String, Integer> outdegree,
            Map<String, List<RiverReach>> outgoing, Map<String, Double> edgeQ, RiverConfig config) {
        PriorityQueue<String> ready = new PriorityQueue<>();
        for (String id : graph.keySet()) {
            if (indegree.get(id) == 0) {
                ready.add(id);
            }
        }
        Map<String, Double> incoming = new HashMap<>();
        Map<String, Flow> solved = new TreeMap<>();
        int visited = 0;
        while (!ready.isEmpty()) {
            String id = ready.remove();
            visited++;
            RiverNode node = graph.get(id);
            double qIn = incoming.getOrDefault(id, 0.0) + node.localInflow();
            if (!Double.isFinite(qIn)) {
                throw new IllegalArgumentException("Flow overflow");
            }
            Flow flow = solveNode(node, qIn, outdegree.get(id), config);
            solved.put(id, flow);
            for (RiverReach edge : outgoing.getOrDefault(id, List.of())) {
                edgeQ.put(edge.id(), flow.outgoing());
                incoming.merge(edge.to(), flow.outgoing(), Double::sum);
                if (indegree.merge(edge.to(), -1, Integer::sum) == 0) {
                    ready.add(edge.to());
                }
            }
        }
        if (visited != graph.size()) {
            throw new IllegalArgumentException("River graph has a cycle");
        }
        return solved;
    }

    private static Flow solveNode(RiverNode node, double qIn, int outgoingCount, RiverConfig config) {
        double qOut = qIn;
        double storageAfter = 0;
        if (node.kind() == RiverNode.Kind.LAKE) {
            double available = qIn * config.stepSeconds() + node.lakeStorage();
            double controlledRelease = Math.min(node.lakeRelease() * config.stepSeconds(), available);
            storageAfter = Math.min(node.lakeCapacity(), available - controlledRelease);
            qOut = (available - storageAfter) / config.stepSeconds();
            if (outgoingCount == 0 && qOut > 1e-9) {
                throw new IllegalArgumentException("Terminal lake overflows without outlet");
            }
        }
        if (!Double.isFinite(qOut)) {
            throw new IllegalArgumentException("Flow overflow");
        }
        return new Flow(qIn, qOut, storageAfter, config.width(qOut));
    }
    public Map<String, RiverNode> nodes() { return nodes; }
    public List<RiverReach> reaches() { return reaches; }
    public Flow flow(String nodeId) { return flows.get(nodeId); }
    public double discharge(String reachId) { return reachFlows.get(reachId); }
}
