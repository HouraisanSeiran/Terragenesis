package com.remotemountains.canyon;

import com.remotemountains.cliff.CliffPatch;
import com.remotemountains.cliff.CliffPlacement;
import com.remotemountains.cliff.Vec3;
import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Noise;
import com.remotemountains.watershed.DrainageGraph;
import com.remotemountains.watershed.WatershedTerrainSource;
import java.util.ArrayList;
import java.util.List;

/** Selects whole, separated charts on valley flanks of the finite catchment. */
public final class CanyonCliffLayout {
    public static final double CHANNEL_HALO = 64;
    private static final double LEGACY_X = 900;
    private static final double LEGACY_ROTATION = Math.atan2(-CliffPatch.OUT.x(), -CliffPatch.OUT.z());
    private static final double LOCAL_ANGLE = Math.atan2(CliffPatch.OUT.z(), CliffPatch.OUT.x());
    private final List<Site> sites;

    public record Site(CliffPlacement placement, int fromNode, int returnNode, double baselineDischarge) {}

    public CanyonCliffLayout(BaseTerrainSource base, long seed, boolean mixed) {
        if (!(base instanceof WatershedTerrainSource watershed))
            throw new IllegalArgumentException("Canyon cliffs require WatershedTerrainSource");
        DrainageGraph graph = watershed.graph();
        List<Site> selected = new ArrayList<>();
        double[] stations = {620, 1050, 1390};
        int[] sides = {-1, -1, 1};
        for (int i = 0; i < stations.length; i++) {
            Site chosen = null;
            for (int shift = 0; shift <= 64 && chosen == null; shift += 32) {
                double x = stations[i] + shift;
                double riverZ = DrainageGraph.bend(x, seed);
                double dzdx = (DrainageGraph.bend(x + 16, seed) - DrainageGraph.bend(x - 16, seed)) / 32;
                double norm = Math.hypot(1, dzdx);
                double outX = sides[i] * dzdx / norm;
                double outZ = -sides[i] / norm;
                double rotation = Math.atan2(outZ, outX) - LOCAL_ANGLE;
                for (int distance = 192; distance <= 240 && chosen == null; distance += 16) {
                    double z = riverZ + sides[i] * distance;
                    long key = Noise.mix(seed ^ (i + 1) * 0x72bdaa37L);
                    CliffPlacement placement = new CliffPlacement(key, x, z, rotation,
                        CanyonCliffStyle.of(mixed).settings(seed, i));
                    if (!clearOfChannels(placement, graph)
                            || !hasFlankRelief(placement, watershed)
                            || !separated(placement, selected, graph)) continue;
                    DrainageGraph.Channel reach = graph.nearestChannel(x, riverZ);
                    if (reach == null) continue;
                    DrainageGraph.Node from = graph.baselineNode(reach.fromNode());
                    DrainageGraph.Node to = graph.baselineNode(reach.toNode());
                    double dx = to.x() - from.x(), dz = to.z() - from.z();
                    double t = Math.max(0, Math.min(1,
                        ((reach.x() - from.x()) * dx + (reach.z() - from.z()) * dz) / (dx * dx + dz * dz)));
                    double q = from.discharge() + t * (to.discharge() - from.discharge());
                    chosen = new Site(placement, from.id(), to.id(), q);
                }
            }
            if (chosen != null) selected.add(chosen);
        }
        sites = List.copyOf(selected);
    }

    public List<Site> sites() { return sites; }
    public List<CliffPlacement> placements() { return sites.stream().map(Site::placement).toList(); }

    private static boolean clearOfChannels(CliffPlacement placement, DrainageGraph graph) {
        // The full chart plus a collar is checked before any water is allocated.
        for (int u = -160; u <= 160; u += 8) for (int v = -80; v <= 80; v += 8) {
            Vec3 local = CliffPatch.ALONG.scale(u).add(CliffPatch.OUT.scale(v));
            Vec3 world = placement.toWorld(256 + local.x(), 256 + local.z());
            DrainageGraph.Channel channel = graph.nearestChannel(world.x(), world.z());
            if (channel != null && channel.distance() < channel.width() + CHANNEL_HALO) return false;
        }
        return true;
    }

    private static boolean hasFlankRelief(CliffPlacement placement, WatershedTerrainSource base) {
        double upper = 0, lower = 0;
        for (int u = -96; u <= 96; u += 48) {
            Vec3 along = CliffPatch.ALONG.scale(u);
            Vec3 high = placement.toWorld(256 + along.x() - 60 * CliffPatch.OUT.x(),
                256 + along.z() - 60 * CliffPatch.OUT.z());
            Vec3 low = placement.toWorld(256 + along.x() + 60 * CliffPatch.OUT.x(),
                256 + along.z() + 60 * CliffPatch.OUT.z());
            var a = base.sample(high.x(), high.z());
            var b = base.sample(low.x(), low.z());
            if (Double.isFinite(a.water()) || Double.isFinite(b.water())) return false;
            upper += a.height();
            lower += b.height();
        }
        return (upper - lower) / 5 >= 3 && lower / 5 > WatershedTerrainSource.SEA + 3;
    }

    private static boolean separated(CliffPlacement candidate, List<Site> selected, DrainageGraph graph) {
        DrainageGraph.Channel oldReach = graph.nearestChannel(LEGACY_X, 0);
        if (oldReach != null) {
            CliffPlacement legacy = new CliffPlacement(0, LEGACY_X, oldReach.z() + 96,
                LEGACY_ROTATION, candidate.settings());
            if (intersects(candidate, legacy, 12)) return false;
        }
        for (Site site : selected) {
            CliffPlacement other = site.placement();
            if (intersects(candidate, other, 24)) return false;
        }
        return true;
    }

    private static boolean intersects(CliffPlacement a, CliffPlacement b, double gap) {
        Vec3 aAlong = a.rotate(CliffPatch.ALONG), aOut = a.rotate(CliffPatch.OUT);
        Vec3 bAlong = b.rotate(CliffPatch.ALONG), bOut = b.rotate(CliffPatch.OUT);
        Vec3 between = new Vec3(b.x() - a.x(), 0, b.z() - a.z());
        for (Vec3 axis : new Vec3[] {aAlong, aOut, bAlong, bOut}) {
            double ra = (160 + gap / 2) * Math.abs(axis.dot(aAlong))
                + (80 + gap / 2) * Math.abs(axis.dot(aOut));
            double rb = (160 + gap / 2) * Math.abs(axis.dot(bAlong))
                + (80 + gap / 2) * Math.abs(axis.dot(bOut));
            if (Math.abs(axis.dot(between)) > ra + rb) return false;
        }
        return true;
    }
}
