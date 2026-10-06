package com.remotemountains.watershed;

import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/** End-to-end finite-basin invariants and a compact preview data export. */
public final class WatershedVerification {
    private static int checks;
    private static void require(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        WatershedTerrainSource source = new WatershedTerrainSource(20260927L, "");
        WatershedTerrainSource restored = new WatershedTerrainSource(20260927L, source.identity());
        var graph = source.graph();
        var nodes = graph.nodes();
        var outlet = graph.outlet();
        require(nodes.size() == DrainageGraph.COLUMNS * DrainageGraph.ROWS, "Complete basin grid");
        require(outlet.downstream() == -1 && outlet.waterLevel() == 72, "Single sea outlet");
        for (var node : nodes) {
            require(node.discharge() >= 0 && node.sedimentFlux() >= 0, "Nonnegative flux");
            int cursor = node.id(), steps = 0;
            while (nodes.get(cursor).downstream() >= 0) {
                int next = nodes.get(cursor).downstream();
                require(nodes.get(next).waterLevel() < nodes.get(cursor).waterLevel(), "Descending water");
                cursor = next;
                require(++steps <= nodes.size(), "Acyclic river graph");
            }
            require(cursor == outlet.id(), "Every cell reaches sole outlet");
        }
        var budget = graph.ledger();
        require(Math.abs(budget.waterResidual()) < 1e-6, "Water ledger");
        require(Math.abs(budget.sedimentResidual()) < 1e-6, "Sediment ledger");
        require(source.peak().worldHeight() >= 700 && source.peak().worldHeight() <= 800,
            "700-800 world block peak");
        require(source.peak().localHeight() > 72, "Elevated headwater");
        for (int branch = 0; branch < 3; branch++) {
            int cursor = graph.source(branch).id(), wet = 0;
            while (cursor != outlet.id()) {
                var node = nodes.get(cursor);
                var next = nodes.get(node.downstream());
                double x = (node.x() + next.x()) * .5;
                double z = (node.z() + next.z()) * .5;
                Terrain.Column sample = source.sample(x, z);
                require(Double.isFinite(sample.water()) && sample.water() >= sample.height(),
                    "Continuous wet channel at " + x + "," + z);
                wet++;
                cursor = next.id();
            }
            require(wet > 40, "Full mountain-to-sea route");
        }
        for (var node : nodes) if (node.visible() && node.downstream() >= 0) {
            var next = nodes.get(node.downstream());
            for (int step = 0; step <= 4; step++) {
                double t = step / 4.0;
                double x = node.x() + t * (next.x() - node.x());
                double z = node.z() + t * (next.z() - node.z());
                Terrain.Column sample = source.sample(x, z);
                require(Double.isFinite(sample.water()) && sample.water() >= sample.height(),
                    "Visible channel body remains wet");
            }
        }
        for (int branch = 0; branch < 3; branch++) {
            var origin = graph.source(branch);
            var channel = graph.nearestChannel(origin.x(), origin.z());
            require(channel != null, "Headwater has a mapped channel");
            Terrain.Column bed = source.sample(origin.x(), origin.z());
            Terrain.Column bankLeft = source.sample(origin.x(), origin.z() - channel.width() - 12);
            Terrain.Column bankRight = source.sample(origin.x(), origin.z() + channel.width() + 12);
            require(Double.isFinite(bed.water()) && bed.height() < bed.water(),
                "Headwater is an incised wetted bed");
            require(bankLeft.height() >= bed.water() - 5 && bankRight.height() >= bed.water() - 5,
                "Headwater water is supported by adjacent ground");
        }
        require(Double.isFinite(source.sample(1660, outlet.z()).water()), "Wet ocean connection");
        for (int x = -100; x <= 1800; x += 47) for (int z = -420; z <= 420; z += 73) {
            var a = source.sample(x, z);
            var b = restored.sample(x, z);
            require(a.height() == b.height() && (Double.isNaN(a.water())
                ? Double.isNaN(b.water()) : a.water() == b.water()), "Deterministic samples");
            require(Double.isFinite(a.height()), "Finite terrain");
        }
        Path preview = Path.of("preview/watershed");
        Files.createDirectories(preview);
        StringBuilder heights = new StringBuilder("local_x,local_z,local_height,water_level,world_height\n");
        for (int z = -480; z <= 480; z += 8) for (int x = -128; x <= 1792; x += 8) {
            Terrain.Column c = source.sample(x, z);
            heights.append(String.format(Locale.ROOT, "%d,%d,%.3f,%s,%.3f%n", x, z,
                c.height(), Double.isNaN(c.water()) ? "" : String.format(Locale.ROOT, "%.3f", c.water()),
                TerrainScale.TALL.height(c.height())));
        }
        Files.writeString(preview.resolve("height_water.csv"), heights);
        StringBuilder flow = new StringBuilder("id,local_x,local_z,downstream,water_level,rainfall,infiltration,discharge,erosion,deposition,sediment_flux,visible\n");
        for (var node : nodes) flow.append(String.format(Locale.ROOT,
            "%d,%.3f,%.3f,%d,%.4f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%b%n",
            node.id(), node.x(), node.z(), node.downstream(), node.waterLevel(),
            node.rainfall(), node.infiltration(), node.discharge(), node.erosion(),
            node.deposition(), node.sedimentFlux(), node.visible()));
        Files.writeString(preview.resolve("drainage_graph.csv"), flow);
        String audit = String.format(Locale.ROOT,
            "{\"identity\":\"%s\",\"checks\":%d,\"peak_local\":%.3f,\"peak_world\":%.3f,\"peak_x\":%.1f,\"peak_z\":%.1f,\"water_residual\":%.9f,\"sediment_residual\":%.9f,\"outlet_water\":%.6f,\"outlet_sediment\":%.6f}%n",
            source.identity(), checks, source.peak().localHeight(), source.peak().worldHeight(),
            source.peak().x(), source.peak().z(), budget.waterResidual(),
            budget.sedimentResidual(), budget.outletWater(), budget.outletSediment());
        Files.writeString(preview.resolve("audit.json"), audit);
        System.out.println("PASS watershed: " + checks + " checks, world peak "
            + source.peak().worldHeight());
    }
}
