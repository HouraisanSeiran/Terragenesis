package com.remotemountains.watershed;

import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import com.remotemountains.vdm.GeneratedVdmSource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/** Check complete river bank transitions, including the reported hillside site. */
public final class WatershedHeightmapVerification {
    public static void main(String[] args) throws Exception {
        int checks = 0;
        for (long seed : new long[] {20260927L, 1L, 812943L}) {
            var source = new WatershedTerrainSource(seed, "", true);
            var restored = new WatershedTerrainSource(seed, source.identity(), true);
            var nodes = source.graph().nodes();
            for (var node : nodes) {
                if (!node.visible() || node.downstream() < 0) continue;
                var next = nodes.get(node.downstream());
                if (source.riverWaterLevel(next.id()) > source.riverWaterLevel(node.id()) + .001)
                    throw new AssertionError("Uphill water at node " + node.id());
                double dx = next.x() - node.x(), dz = next.z() - node.z();
                double length = Math.hypot(dx, dz);
                for (int step = 0; step <= (int) length; step += 2) {
                    double t = step / length, x = node.x() + t * dx, z = node.z() + t * dz;
                    double nx = -dz / length, nz = dx / length;
                    var center = source.sample(x, z);
                    if (!Double.isFinite(center.water()) || center.water() <= center.height())
                        throw new AssertionError("Dry channel at " + x + "," + z);
                    for (int side : new int[] {-1, 1}) {
                        boolean foundDry = false;
                        for (int radius = 0; radius <= 48; radius++) {
                            double px = x + side * nx * radius, pz = z + side * nz * radius;
                            Terrain.Column current = source.sample(px, pz);
                            if (Double.isFinite(current.water()) && current.water() > current.height())
                                continue;
                            if (radius == 0) throw new AssertionError("Dry center");
                            double precedingX = x + side * nx * (radius - 1);
                            double precedingZ = z + side * nz * (radius - 1);
                            Terrain.Column wet = source.sample(precedingX, precedingZ);
                            if (Double.isFinite(wet.water()) && wet.water() > wet.height()) {
                                double dryFloor = Math.floor(TerrainScale.TALL.height(current.height()));
                                double wetSurface = Math.floor(TerrainScale.TALL.height(wet.water()));
                                if (dryFloor + 1 < wetSurface)
                                    throw new AssertionError("Perched river edge seed=" + seed
                                        + " at " + px + "," + pz + " dry=" + dryFloor
                                        + " water=" + wetSurface + " radius=" + radius
                                        + " localDry=" + current.height() + " localWet=" + wet.water()
                                        + " dryChannel=" + source.graph().nearestChannel(px,pz)
                                        + " wetChannel=" + source.graph().nearestChannel(precedingX,precedingZ)
                                        + " naturalDry=" + source.naturalSurface(px,pz));
                                checks++;
                            }
                            foundDry = true;
                            break;
                        }
                        if (!foundDry && x < 1450)
                            throw new AssertionError("Unbounded river width at " + x + "," + z);
                    }
                }
            }
            if (seed == 20260927L) {
                writeProfile(source);
                var finalTerrain = new GeneratedVdmSource(source, seed,
                    WatershedTerrainSource.RECIPE_V2, TerrainScale.TALL);
                int worldWet = 0, worldEdges = 0;
                for (int x = 270; x <= 450; x++) for (int z = -90; z <= 105; z++) {
                    Terrain.Column a = source.sample(x / 3.0, z / 3.0);
                    Terrain.Column b = restored.sample(x / 3.0, z / 3.0);
                    if (a.height() != b.height() || Double.doubleToLongBits(a.water()) != Double.doubleToLongBits(b.water()))
                        throw new AssertionError("Non-deterministic screenshot region");
                    Terrain.Column block = finalTerrain.sample(x, z);
                    if (!Double.isFinite(block.water())
                            || Math.floor(block.water()) <= Math.floor(block.height())) continue;
                    worldWet++;
                    for (int[] direction : new int[][] {{1, 0}, {-1, 0}, {0, 1}, {0, -1}}) {
                        Terrain.Column adjacent = finalTerrain.sample(x + direction[0], z + direction[1]);
                        if (Double.isFinite(adjacent.water())
                                && Math.floor(adjacent.water()) > Math.floor(adjacent.height())) continue;
                        if (Math.floor(adjacent.height()) + 1 < Math.floor(block.water()))
                            throw new AssertionError("Final voxel perched water at world " + x + "," + z
                                + " water=" + block.water() + " dry=" + adjacent.height());
                        checks++;
                        worldEdges++;
                    }
                }
                if (worldWet < 100 || worldEdges < 10)
                    throw new AssertionError("Screenshot region missed actual river: wet=" + worldWet
                        + " edges=" + worldEdges);
            }
            if (source.peak().worldHeight() < 700 || source.peak().worldHeight() > 800)
                throw new AssertionError("Peak outside target: " + source.peak());
        }
        System.out.println("PASS river heightmap bank edges: " + checks);
    }

    private static void writeProfile(WatershedTerrainSource source) throws Exception {
        Path file = Path.of("preview/watershed/river-profile-v2.csv");
        Files.createDirectories(file.getParent());
        StringBuilder rows = new StringBuilder("x,z,original_bank_left,original_bank_right,bed,water,river_node_level\n");
        var graph = source.graph();
        for (var node : graph.nodes()) {
            if (!node.visible() || node.downstream() < 0) continue;
            var next = graph.baselineNode(node.downstream());
            double dx = next.x() - node.x(), dz = next.z() - node.z();
            double length = Math.hypot(dx, dz);
            for (int step = 0; step <= (int) length; step += 4) {
                double t = step / length, x = node.x() + t * dx, z = node.z() + t * dz;
                var channel = graph.nearestChannel(x, z);
                if (channel == null) continue;
                double nx = -dz / length, nz = dx / length, r = channel.width() + 1;
                var c = source.sample(x, z);
                rows.append(String.format(Locale.ROOT, "%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f%n",
                    x, z, source.naturalSurface(x + nx * r, z + nz * r),
                    source.naturalSurface(x - nx * r, z - nz * r), c.height(), c.water(),
                    source.riverWaterLevel(node.id())));
            }
        }
        Files.writeString(file, rows);
        var legacy = new WatershedTerrainSource(20260927L, "");
        double centerZ = graph.nearestChannel(127, 12).z();
        StringBuilder cross = new StringBuilder("local_z,legacy_ground,legacy_water,corrected_ground,corrected_water\n");
        for (int i = -150; i <= 150; i++) {
            double z = centerZ + i / 3.0;
            var before = legacy.sample(127, z);
            var after = source.sample(127, z);
            cross.append(String.format(Locale.ROOT, "%.4f,%.4f,%s,%.4f,%s%n", z,
                before.height(), Double.isFinite(before.water()) ? Double.toString(before.water()) : "",
                after.height(), Double.isFinite(after.water()) ? Double.toString(after.water()) : ""));
        }
        Files.writeString(Path.of("preview/watershed/river-cross-section-v2.csv"), cross);
    }
}
