package com.remotemountains.canyon;

import com.remotemountains.cliff.CliffPipeline;
import com.remotemountains.cliff.CliffPlacement;
import com.remotemountains.cliff.ErosionStatistics;
import com.remotemountains.cliff.RunoffBoundary;
import com.remotemountains.cliff.Vec3;
import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.SurfaceModifier;
import com.remotemountains.watershed.DrainageGraph;
import com.remotemountains.watershed.WatershedTerrainSource;
import com.remotemountains.watershedcliff.WatershedCliffModifier;
import java.util.ArrayList;
import java.util.List;

/** Adds separated canyon bands to the original watershed bank and runoff ledger. */
public final class CanyonCliffModifier implements SurfaceModifier {
    public static final String MIXED_RECIPE = "watershed-vdm-canyon-v2";
    public static final String SINGLE_RECIPE = "watershed-vdm-canyon-single-v2";
    private static final double PATCH_FRACTION = .008;

    private final WatershedCliffModifier legacy;
    private final CanyonCliffLayout layout;
    private final List<CliffPlacement> placements;
    private final List<CliffPipeline.Result> results;
    private final List<WatershedCliffModifier.LocalAudit> audits;

    public CanyonCliffModifier(BaseTerrainSource base, long seed, boolean mixed) {
        if (!(base instanceof WatershedTerrainSource watershed))
            throw new IllegalArgumentException("Canyon cliffs require WatershedTerrainSource");
        legacy = new WatershedCliffModifier(base, seed);
        layout = new CanyonCliffLayout(base, seed, mixed);
        placements = layout.placements();
        DrainageGraph graph = watershed.graph();
        List<CliffPipeline.Result> built = new ArrayList<>();
        List<WatershedCliffModifier.LocalAudit> localAudits = new ArrayList<>();
        String recipe = mixed ? MIXED_RECIPE : SINGLE_RECIPE;
        int index = 0;
        for (CanyonCliffLayout.Site site : layout.sites()) {
            CliffPlacement placement = site.placement();
            double allocated = site.baselineDischarge() * PATCH_FRACTION;
            BaseTerrainSource local = (x, z) -> {
                Vec3 world = placement.toWorld(x, z);
                return base.sample(world.x(), world.z());
            };
            CliffPipeline.Result result = new CliffPipeline().build(local, placement.settings(),
                CliffPipeline.Stage.ERODED, new RunoffBoundary(allocated, 0, 14));
            ErosionStatistics statistics = result.statistics();
            int steps = placement.settings().steps();
            WatershedCliffModifier.LocalAudit audit = new WatershedCliffModifier.LocalAudit(
                WatershedCliffModifier.STEP_SECONDS, steps, site.baselineDischarge(), allocated,
                statistics.waterIn(), statistics.waterOut(), statistics.waterStored(),
                statistics.sedimentOut(), statistics.sedimentStored(), statistics.erodedRock(),
                statistics.waterError(), statistics.sedimentError(), site.fromNode(), site.returnNode());
            graph.registerBankExchange(recipe + ":" + index, site.fromNode(), site.returnNode(),
                allocated, Math.min(allocated, audit.returnedPerStep()),
                statistics.erodedRock() / steps, statistics.sedimentStored() / steps);
            built.add(result);
            localAudits.add(audit);
            index++;
        }
        results = List.copyOf(built);
        audits = List.copyOf(localAudits);
    }

    public WatershedCliffModifier legacy() { return legacy; }
    public CanyonCliffLayout layout() { return layout; }
    public List<CliffPlacement> placements() { return placements; }
    public List<CliffPipeline.Result> results() { return results; }
    public CliffPipeline.Result result(int index) { return results.get(index); }
    public List<WatershedCliffModifier.LocalAudit> audits() { return audits; }

    @Override public Displacement apply(double x, double z, Displacement initial) {
        Displacement displacement = legacy.apply(x, z, initial);
        for (int i = 0; i < placements.size(); i++) {
            CliffPlacement placement = placements.get(i);
            if (!placement.contains(x, z)) continue;
            Vec3 local = placement.toLocal(x, z);
            Displacement delta = results.get(i).patch().delta(local.x(), local.z());
            Vec3 rotated = placement.rotate(new Vec3(delta.dx(), delta.dy(), delta.dz()));
            displacement = new Displacement(displacement.dx() + rotated.x(),
                displacement.dy() + rotated.y(), displacement.dz() + rotated.z());
        }
        return displacement;
    }
}
