package com.remotemountains.watershed;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** One finite, directed catchment. Water volumes are cubic metres per model step. */
public final class DrainageGraph {
    public static final int SPACING = 32;
    public static final int COLUMNS = 51;
    public static final int ROWS = 25;
    private static final int MID_ROW = ROWS / 2;
    private static final double CELL_AREA = SPACING * SPACING;
    private final List<Node> nodes;
    private final List<Segment> channels;
    private final Map<Long, List<Segment>> buckets;
    private final long seed;
    private final Ledger baseLedger;
    private final Map<String, BankExchange> exchanges = new HashMap<>();
    private final double[] bankAllocations = new double[COLUMNS * ROWS];
    private final double[] waterChanges = new double[COLUMNS * ROWS];
    private final double[] sedimentChanges = new double[COLUMNS * ROWS];
    private double divertedWater, addedSediment, bankDeposition;

    public record Node(int id, double x, double z, int downstream, double waterLevel,
                       double rainfall, double infiltration, double discharge,
                       double erosion, double deposition, double sedimentFlux,
                       boolean visible) {}

    public record Channel(double x, double z, double distance, double waterLevel,
                          double discharge, double sedimentFlux, double width,
                          int fromNode, int toNode) {}

    public record Ledger(double rainfall, double infiltration, double outletWater,
                         double erodedSediment, double depositedSediment,
                         double outletSediment, double bankWaterLoss) {
        public double waterResidual() { return rainfall - infiltration - bankWaterLoss - outletWater; }
        public double sedimentResidual() {
            return erodedSediment - depositedSediment - outletSediment;
        }
    }

    private record Segment(Node a, Node b) {}
    public record BankExchange(String key, int fromNode, int returnNode,
                               double waterTaken, double waterReturned,
                               double sedimentAdded, double sedimentDeposited) {}

    public DrainageGraph(long seed) {
        this.seed = seed;
        int count = COLUMNS * ROWS;
        double[] runoff = new double[count];
        double[] inputSediment = new double[count];
        Node[] result = new Node[count];
        boolean[] namedRoute = new boolean[count];
        for (int sourceRow : new int[] {2, MID_ROW, ROWS - 3}) {
            int row = sourceRow;
            for (int col = 0; col < COLUMNS; col++) {
                namedRoute[id(col, row)] = true;
                if (row != MID_ROW && col % 2 == 1) row += row < MID_ROW ? 1 : -1;
            }
        }
        double rainTotal = 0, lossTotal = 0, erosionTotal = 0, depositTotal = 0;
        for (int col = 0; col < COLUMNS; col++) {
            for (int order = 0; order < ROWS; order++) {
                int row = order < MID_ROW ? order : ROWS - 1 - (order - MID_ROW);
                if (order == ROWS - 1) row = MID_ROW;
                int id = id(col, row);
                double x = col * SPACING;
                double towardCenter = row == MID_ROW ? 0 : row < MID_ROW ? .5 : -.5;
                double z = (row - MID_ROW + (col % 2 == 1 ? towardCenter : 0))
                    * SPACING + bend(x, seed);
                double rainDepth = .0015 + .00035 * Math.sin((x + seed % 1000) * .003)
                    + .00022 * Math.cos(z * .009);
                double rain = Math.max(.0006, rainDepth) * CELL_AREA;
                double infiltration = rain * .18;
                rainTotal += rain;
                lossTotal += infiltration;
                double q = runoff[id] + rain - infiltration;
                double waterLevel = level(col) + .12 * Math.abs(row - MID_ROW);
                double slope = col == COLUMNS - 1 ? .12 : level(col) - level(col + 1);
                double erosion = row == MID_ROW && col == COLUMNS - 1 ? 0
                    : .00055 * Math.sqrt(q) * Math.max(.05, slope);
                double deposition = (inputSediment[id] + erosion) * (row == MID_ROW && col == COLUMNS - 1 ? .12 : .008);
                double sediment = inputSediment[id] + erosion - deposition;
                erosionTotal += erosion;
                depositTotal += deposition;
                int next = -1;
                if (col < COLUMNS - 1) {
                    int nextRow = row;
                    if (row != MID_ROW && col % 2 == 1) nextRow += row < MID_ROW ? 1 : -1;
                    next = id(col + 1, nextRow);
                    runoff[next] += q;
                    inputSediment[next] += sediment;
                } else if (row != MID_ROW) {
                    next = id(col, row + (row < MID_ROW ? 1 : -1));
                    runoff[next] += q;
                    inputSediment[next] += sediment;
                }
                result[id] = new Node(id, x, z, next, waterLevel, rain, infiltration,
                    q, erosion, deposition, sediment,
                    row == MID_ROW || namedRoute[id] || q >= 300);
            }
        }
        nodes = List.of(result);
        Node outlet = result[id(COLUMNS - 1, MID_ROW)];
        baseLedger = new Ledger(rainTotal, lossTotal, outlet.discharge(), erosionTotal,
            depositTotal, outlet.sedimentFlux(), 0);
        List<Segment> edges = new ArrayList<>();
        Map<Long, List<Segment>> spatial = new HashMap<>();
        for (Node node : nodes) {
            if (node.downstream() < 0 || !node.visible()) continue;
            Segment edge = new Segment(node, result[node.downstream()]);
            edges.add(edge);
            double mx = (edge.a.x() + edge.b.x()) * .5;
            double mz = (edge.a.z() + edge.b.z()) * .5;
            int bx = (int) Math.floor(mx / 64), bz = (int) Math.floor(mz / 64);
            for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                spatial.computeIfAbsent(key(bx + dx, bz + dz), ignored -> new ArrayList<>()).add(edge);
        }
        channels = List.copyOf(edges);
        buckets = Collections.unmodifiableMap(spatial);
    }

    private static int id(int col, int row) { return col * ROWS + row; }
    public static double bend(double x, long seed) {
        double phase = (seed & 1023) * .0061;
        return 21 * Math.sin(x / 180 + phase) + 9 * Math.sin(x / 73 - phase * .7);
    }
    private static long key(int x, int z) { return ((long) x << 32) ^ (z & 0xffffffffL); }
    public static double level(int column) {
        double t = Math.min(1, Math.max(0, column / (double) (COLUMNS - 1)));
        return 72 + 202 * Math.pow(1 - t, 1.45);
    }
    public synchronized List<Node> nodes() {
        List<Node> copy = new ArrayList<>(nodes.size());
        for (Node node : nodes) copy.add(adjusted(node));
        return List.copyOf(copy);
    }
    public synchronized Ledger ledger() {
        return new Ledger(baseLedger.rainfall(), baseLedger.infiltration(),
            baseLedger.outletWater() - divertedWater,
            baseLedger.erodedSediment() + addedSediment,
            baseLedger.depositedSediment() + bankDeposition,
            baseLedger.outletSediment() + addedSediment - bankDeposition,
            divertedWater);
    }
    public synchronized Node outlet() { return adjusted(nodes.get(id(COLUMNS - 1, MID_ROW))); }
    public Node baselineNode(int id) { return nodes.get(id); }
    public double baselineDischarge(int id) { return nodes.get(id).discharge(); }
    public Node source(int index) { return nodes.get(id(0, new int[] {2, MID_ROW, ROWS - 3}[index])); }
    public int channelCount() { return channels.size(); }

    /** Divert water from an upstream reach, return it downstream, and add bank sediment. */
    public synchronized BankExchange registerBankExchange(String key, int fromNode, int returnNode,
            double waterTaken, double waterReturned, double sedimentAdded, double sedimentDeposited) {
        if (key == null || key.isBlank()) throw new IllegalArgumentException("Exchange key required");
        BankExchange exchange = new BankExchange(key, fromNode, returnNode, waterTaken,
            waterReturned, sedimentAdded, sedimentDeposited);
        BankExchange prior = exchanges.get(key);
        if (prior != null) {
            if (!prior.equals(exchange)) throw new IllegalArgumentException("Conflicting exchange key: " + key);
            return prior;
        }
        if (fromNode < 0 || fromNode >= nodes.size() || returnNode < 0 || returnNode >= nodes.size()
                || !Double.isFinite(waterTaken) || !Double.isFinite(waterReturned)
                || !Double.isFinite(sedimentAdded) || !Double.isFinite(sedimentDeposited)
                || waterTaken < 0 || waterReturned < 0 || waterReturned > waterTaken
                || sedimentAdded < 0 || sedimentDeposited < 0
                || sedimentDeposited > sedimentAdded
                || waterTaken + bankAllocations[fromNode]
                    > nodes.get(fromNode).discharge() + waterChanges[fromNode]) {
            throw new IllegalArgumentException("Invalid bank exchange budget");
        }
        int cursor = nodes.get(fromNode).downstream();
        while (cursor >= 0 && cursor != returnNode) cursor = nodes.get(cursor).downstream();
        if (cursor < 0) throw new IllegalArgumentException("Bank return is not downstream");
        cursor = nodes.get(fromNode).downstream();
        while (cursor >= 0 && cursor != returnNode) {
            waterChanges[cursor] -= waterTaken;
            cursor = nodes.get(cursor).downstream();
        }
        while (cursor >= 0) {
            waterChanges[cursor] -= waterTaken - waterReturned;
            sedimentChanges[cursor] += sedimentAdded - sedimentDeposited;
            cursor = nodes.get(cursor).downstream();
        }
        divertedWater += waterTaken - waterReturned;
        addedSediment += sedimentAdded;
        bankDeposition += sedimentDeposited;
        bankAllocations[fromNode] += waterTaken;
        exchanges.put(key, exchange);
        return exchange;
    }

    public synchronized List<BankExchange> bankExchanges() { return List.copyOf(exchanges.values()); }

    private Node adjusted(Node node) {
        return new Node(node.id(), node.x(), node.z(), node.downstream(), node.waterLevel(),
            node.rainfall(), node.infiltration(), node.discharge() + waterChanges[node.id()],
            node.erosion(), node.deposition(), node.sedimentFlux() + sedimentChanges[node.id()],
            node.visible());
    }

    /** Nearest wet edge in a bounded local neighbourhood; null beyond 96 blocks. */
    public synchronized Channel nearestChannel(double x, double z) {
        int bx = (int) Math.floor(x / 64), bz = (int) Math.floor(z / 64);
        List<Segment> nearby = buckets.get(key(bx, bz));
        if (nearby == null) return null;
        Channel nearest = null;
        for (Segment edge : nearby) {
            double dx = edge.b.x() - edge.a.x(), dz = edge.b.z() - edge.a.z();
            double t = Math.max(0, Math.min(1,
                ((x - edge.a.x()) * dx + (z - edge.a.z()) * dz) / (dx * dx + dz * dz)));
            double px = edge.a.x() + t * dx, pz = edge.a.z() + t * dz;
            double distance = Math.hypot(x - px, z - pz);
            if (distance > 96 || nearest != null && distance >= nearest.distance()) continue;
            double aq = edge.a.discharge() + waterChanges[edge.a.id()];
            double bq = edge.b.discharge() + waterChanges[edge.b.id()];
            double q = aq + t * (bq - aq);
            double as = edge.a.sedimentFlux() + sedimentChanges[edge.a.id()];
            double bs = edge.b.sedimentFlux() + sedimentChanges[edge.b.id()];
            double sediment = as + t * (bs - as);
            double water = edge.a.waterLevel() + t * (edge.b.waterLevel() - edge.a.waterLevel());
            double baseline = edge.a.discharge() + t * (edge.b.discharge() - edge.a.discharge());
            double width = 4 + .25 * Math.sqrt(Math.max(0, baseline));
            nearest = new Channel(px, pz, distance, water, q, sediment, width,
                edge.a.id(), edge.b.id());
        }
        return nearest;
    }
}
