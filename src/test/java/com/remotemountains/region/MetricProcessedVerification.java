package com.remotemountains.region;

import com.remotemountains.core.Terrain;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public final class MetricProcessedVerification {
    public static void main(String[] arguments) throws Exception {
        Path sourcePath = Path.of(arguments[0]);
        byte[] original = Files.readAllBytes(sourcePath);
        Path copy = Files.createTempFile("metric-consumer-", ".tgmc");
        try {
            Files.write(copy, original);
            MetricProcessedTerrainSource source = new MetricProcessedTerrainSource(copy, 20260927L, "");
            if (!source.identity().matches("[0-9a-f]{64}")) throw new AssertionError("missing identity");
            Terrain.Column a = source.sample(65728, 265408);
            Terrain.Column b = source.sample(65729, 265409);
            if (!Double.isFinite(a.height()) || !Double.isFinite(b.height())
                    || Double.isFinite(a.water()) || Math.abs(a.height() - b.height()) > 100
                    || Math.abs(a.height() - 503.75499620225685) > 1e-9
                    || a.base().climate().variant() != 2) {
                throw new AssertionError("invalid metric interpolation");
            }
            source.prepareBounds(65728, 265408, 65791, 265471);
            System.setProperty("remotemountains.metricSnapshot", copy.toString());
            try (Terrain terrain = new Terrain(20260927L, source.identity(), MetricProcessedTerrainSource.RECIPE,
                    "metric_processed_readonly_v1", "metric_1m_sea62_1024_v1")) {
                if (!terrain.metricSurface() || terrain.needsPreparation() == false
                        || !terrain.identity().equals(source.identity())) {
                    throw new AssertionError("Factory failed to bind read-only metric source");
                }
                Terrain.Column tileCell = terrain.tile(1027, 4147).join()[0];
                if (Math.abs(tileCell.height() - source.sample(65728, 265408).height()) > 1e-9
                        || !terrain.solid(65728, (int) Math.floor(tileCell.height()), 265408, tileCell)
                        || terrain.solid(65728, (int) Math.floor(tileCell.height()) + 1, 265408, tileCell)) {
                    throw new AssertionError("Factory tile, surface or solid mapping differs");
                }
            } finally {
                System.clearProperty("remotemountains.metricSnapshot");
            }
            reject(() -> source.sample(65727, 265408));
            reject(() -> source.prepareBounds(65727, 265408, 65791, 265471));
            reject(() -> new MetricProcessedTerrainSource(copy, 0, ""));
            reject(() -> new MetricProcessedTerrainSource(copy, 20260927L, "wrong"));
            byte[] damaged = Arrays.copyOf(original, original.length);
            damaged[damaged.length - 40] ^= 1;
            Files.write(copy, damaged);
            reject(() -> new MetricProcessedTerrainSource(copy, 20260927L, ""));
            Files.write(copy, Arrays.copyOf(original, original.length - 1));
            reject(() -> new MetricProcessedTerrainSource(copy, 20260927L, ""));
            System.out.println("PASS read-only metric source, bounds, identity and damage rejection");
        } finally {
            Files.deleteIfExists(copy);
        }
    }

    private static void reject(Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Invalid metric input accepted");
        } catch (IllegalArgumentException | IllegalStateException expected) {
            // Invalid or unavailable published data must fail at the consumer boundary.
        }
    }
}
