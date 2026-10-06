package com.remotemountains.canyon;

import com.remotemountains.cliff.CliffPatch;
import com.remotemountains.cliff.CliffPlacement;
import com.remotemountains.cliff.Vec3;
import com.remotemountains.vdm.DensityColumn;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.VdmBuilder;
import com.remotemountains.vdm.VdmVoxelizer;
import com.remotemountains.watershed.WatershedTerrainSource;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Exercises canyon placement, catchment routing, and the rasterized VDM seams. */
public final class CanyonVerification {
    private static int checks;

    private static void require(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    private static void close(double actual, double expected, String message) {
        require(Math.abs(actual - expected) <= 1e-7 * Math.max(1, Math.abs(expected)),
            message + ": " + actual + " vs " + expected);
    }

    public static void main(String[] args) {
        long seed = 20260927L;
        var base = new WatershedTerrainSource(seed, "");
        double initialWater = base.graph().outlet().discharge();
        double initialSediment = base.graph().outlet().sedimentFlux();
        var mixed = new CanyonCliffModifier(base, seed, true);
        List<CliffPlacement> sites = mixed.placements();
        require(sites.size() >= 2, "Canyon must extend both valley sides");
        require(sites.equals(new CanyonCliffLayout(base, seed, true).placements()),
            "Placement changes across layout instances");
        require(!sites.equals(new CanyonCliffLayout(base, seed + 1, true).placements()),
            "Seed must alter placement");
        require(mixed.results().size() == sites.size() && mixed.audits().size() == sites.size(),
            "Every placed side needs a completed chart and audit");
        Set<Double> mixedAngles = new HashSet<>();
        for (int i = 0; i < sites.size(); i++) {
            var site = sites.get(i);
            mixedAngles.add(site.settings().angleDegrees());
            require(mixed.result(i).statistics().erodedRock() > 0, "Chart did not erode");
            Vec3 inverse = site.toLocal(site.x(), site.z());
            close(inverse.x(), 256, "Placement X inverse");
            close(inverse.z(), 256, "Placement Z inverse");
            for (int j = 0; j < sites.size(); j++) if (i != j) {
                var other = sites.get(j);
                for (int u = -144; u <= 144; u += 16) for (int v = -64; v <= 64; v += 16) {
                    Vec3 local = new Vec3(256, 0, 256)
                        .add(CliffPatch.ALONG.scale(u)).add(CliffPatch.OUT.scale(v));
                    Vec3 world = site.toWorld(local.x(), local.z());
                    require(!other.contains(world.x(), world.z()), "Canyon charts overlap");
                }
            }
        }
        require(mixedAngles.size() >= 2, "Mixed recipe needs distinct reference angles");

        double taken = 0, returned = 0, sediment = 0;
        for (var audit : mixed.audits()) {
            require(audit.allocatedPerStep() > 0 && audit.waterOut() > 0,
                "Patch must receive and return river flow");
            close(audit.waterIn(), audit.allocatedPerStep() * audit.steps(), "Input budget");
            close(audit.waterResidual(), 0, "Patch water balance");
            close(audit.sedimentResidual(), 0, "Patch sediment balance");
            taken += audit.allocatedPerStep();
            returned += Math.min(audit.allocatedPerStep(), audit.returnedPerStep());
            sediment += audit.sedimentOutPerStep();
        }
        var legacyAudit = mixed.legacy().audit();
        taken += legacyAudit.allocatedPerStep();
        returned += Math.min(legacyAudit.allocatedPerStep(), legacyAudit.returnedPerStep());
        sediment += legacyAudit.sedimentOutPerStep();
        require(base.graph().bankExchanges().size() == sites.size() + 1,
            "All bank charts must register exactly one exchange");
        close(base.graph().outlet().discharge(), initialWater - taken + returned,
            "Downstream water includes every bank chart");
        close(base.graph().outlet().sedimentFlux(), initialSediment + sediment,
            "Downstream sediment includes every bank chart");
        close(base.graph().ledger().waterResidual(), 0, "Catchment water balance");
        close(base.graph().ledger().sedimentResidual(), 0, "Catchment sediment balance");
        double onceWater = base.graph().outlet().discharge();
        double onceSediment = base.graph().outlet().sedimentFlux();
        var repeated = new CanyonCliffModifier(base, seed, true);
        require(base.graph().bankExchanges().size() == sites.size() + 1,
            "Reconstruction double-registered exchange");
        close(base.graph().outlet().discharge(), onceWater, "Reconstruction changed downstream water");
        close(base.graph().outlet().sedimentFlux(), onceSediment,
            "Reconstruction changed downstream sediment");
        require(repeated.placements().equals(sites), "Reconstruction changed placement");

        // Wet channels are sampled across the entire catchment, including the old bank cliff.
        int wetSamples = 0;
        Displacement zero = new Displacement(0, 0, 0);
        for (int x = 0; x <= 1600; x += 16) {
            var channel = base.graph().nearestChannel(x, 0);
            if (channel == null) continue;
            for (int offset = -16; offset <= 16; offset += 8) {
                double z = channel.z() + offset;
                var actualChannel = base.graph().nearestChannel(x, z);
                if (actualChannel == null || actualChannel.distance() > actualChannel.width() + 15) continue;
                wetSamples++;
                require(mixed.apply(x, z, zero).equals(mixed.legacy().apply(x, z, zero)),
                    "New canyon sculpting entered a wet river corridor");
            }
        }
        require(wetSamples > 200, "Wet corridor check did not cover the river");

        var singleBase = new WatershedTerrainSource(seed, "");
        var single = new CanyonCliffModifier(singleBase, seed, false);
        require(single.placements().size() == sites.size(), "Single recipe changed canyon count");
        for (var site : single.placements())
            close(site.settings().angleDegrees(), 76, "Single recipe reference angle");
        close(singleBase.graph().ledger().waterResidual(), 0, "Single recipe water balance");
        close(singleBase.graph().ledger().sedimentResidual(), 0, "Single recipe sediment balance");

        verifyVoxels(base, mixed, sites.getFirst());
        System.out.println("PASS canyon: " + checks + " checks, " + wetSamples + " wet corridor samples");
    }

    private static void verifyVoxels(WatershedTerrainSource base, CanyonCliffModifier canyon,
                                     CliffPlacement site) {
        // Two independent VDM tiles must rasterize the same world columns in their overlap.
        int tileX = Math.floorDiv((int) Math.floor(site.x()), 64) * 64;
        int tileZ = Math.floorDiv((int) Math.floor(site.z()), 64) * 64;
        var builder = new VdmBuilder(base, canyon, 2, 64);
        var raster = new VdmVoxelizer();
        int seamX = tileX;
        int regionZ = (int) Math.floor(site.z()) - 8;
        DensityColumn[] left = raster.rasterize(builder.build(tileX - 64, tileZ, 64),
            seamX - 2, regionZ, 5);
        DensityColumn[] right = raster.rasterize(builder.build(tileX, tileZ, 64),
            seamX - 2, regionZ, 5);
        for (int i = 0; i < left.length; i++) for (int y = 32; y <= 350; y++)
            require(left[i].solid(y) == right[i].solid(y), "Adjacent canyon VDM tile seam");

        // Compare actual rasterized terrain columns against the unsculpted VDM.
        Vec3 flank = new Vec3(256, 0, 256).add(CliffPatch.OUT.scale(-18));
        Vec3 world = site.toWorld(flank.x(), flank.z());
        int sx = (int) Math.floor(world.x()), sz = (int) Math.floor(world.z());
        int originX = Math.floorDiv(sx, 64) * 64, originZ = Math.floorDiv(sz, 64) * 64;
        DensityColumn[] sculpted = raster.rasterize(builder.build(originX, originZ, 64),
            originX, originZ, 64);
        DensityColumn[] baseline = raster.rasterize(new VdmBuilder(base, null, 2, 64)
            .build(originX, originZ, 64), originX, originZ, 64);
        double largest = 0;
        for (int z = 0; z < 64; z += 4) for (int x = 0; x < 64; x += 4) {
            int i = z * 64 + x;
            largest = Math.max(largest, Math.abs(sculpted[i].top() - baseline[i].top()));
        }
        require(largest > 6, "Rasterized canyon relief does not exceed six blocks");
    }
}
