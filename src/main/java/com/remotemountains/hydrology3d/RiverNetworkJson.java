package com.remotemountains.hydrology3d;

import java.util.Comparator;

/** Deterministic synthetic fixture export for inspection and plotting. */
public final class RiverNetworkJson {
    private RiverNetworkJson() {}
    public static String write(RiverNetwork network) {
        StringBuilder json = new StringBuilder("{\n  \"units\": \"world blocks, block^3/s, block^3 storage\",\n  \"synthetic\": true,\n  \"nodes\": [\n");
        var nodes = network.nodes().values().stream().sorted(Comparator.comparing(RiverNode::id)).toList();
        for (int i = 0; i < nodes.size(); i++) {
            RiverNode n = nodes.get(i);
            var f = network.flow(n.id());
            json.append("    {\"id\":\"").append(n.id()).append("\",\"kind\":\"").append(n.kind())
                .append("\",\"xyz\":").append(point(n.point())).append(",\"inflow\":").append(f.incoming())
                .append(",\"outflow\":").append(f.outgoing()).append(",\"storage\":").append(f.storageAfter())
                .append(",\"width\":").append(f.width()).append('}');
            json.append(i + 1 == nodes.size() ? "\n" : ",\n");
        }
        json.append("  ],\n  \"reaches\": [\n");
        var reaches = network.reaches();
        for (int i = 0; i < reaches.size(); i++) {
            RiverReach r = reaches.get(i);
            json.append("    {\"id\":\"").append(r.id()).append("\",\"from\":\"").append(r.from())
                .append("\",\"to\":\"").append(r.to()).append("\",\"mode\":\"").append(r.mode())
                .append("\",\"flow\":").append(network.discharge(r.id())).append(",\"points\":[");
            for (int p = 0; p < r.points().size(); p++) {
                if (p > 0) json.append(',');
                json.append(point(r.points().get(p)));
            }
            json.append("]}").append(i + 1 == reaches.size() ? "\n" : ",\n");
        }
        return json.append("  ]\n}\n").toString();
    }
    private static String point(Point3 p) { return "[" + p.x() + "," + p.y() + "," + p.z() + "]"; }
}
