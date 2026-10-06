package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Concurrent same-region ownership, cached reads, and failed-owner retry. */
public final class DerivedConcurrencyVerification {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory(Path.of("verification", "governance"), "derived-concurrent-");
        RegionConfig config = new RegionConfig(3, "none_v1");
        AtomicInteger calls = new AtomicInteger();
        BaseTerrainSource model = new BaseTerrainSource() {
            public String identity() { return "concurrency-model-v1"; }
            public Terrain.Column sample(double x, double z) {
                calls.incrementAndGet();
                double y = 90 + Math.sin(x / 10) + Math.cos(z / 10);
                return new Terrain.Column(y, Double.NaN,
                    new Landscape.Base(y, Landform.KARST, new Landscape.Climate(.5, .5), 0));
            }
        };
        RawRegionTerrainSource raw = new RawRegionTerrainSource(root, 23, model.identity(),
            RawRegionTerrainSource.TUNED_RECIPE, config, () -> model);
        AtomicInteger factoryCalls = new AtomicInteger();
        DerivedRegionTerrainSource source = new DerivedRegionTerrainSource(root, 23, model.identity(),
            config, () -> { factoryCalls.incrementAndGet(); return raw; });
        CompletableFuture<Path> first = CompletableFuture.supplyAsync(() -> source.prepareRegion(0, 0));
        CompletableFuture<Path> second = CompletableFuture.supplyAsync(() -> source.prepareRegion(0, 0));
        if (!first.get(60, TimeUnit.SECONDS).equals(second.get(60, TimeUnit.SECONDS))
                || factoryCalls.get() != 1) throw new AssertionError("Same region was prepared twice");

        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        RawRegionTerrainSource slowRaw = new RawRegionTerrainSource(root.resolve("slow"), 23,
            model.identity(), RawRegionTerrainSource.TUNED_RECIPE, config, () -> new BaseTerrainSource() {
                public String identity() { return model.identity(); }
                public Terrain.Column sample(double x, double z) {
                    entered.countDown();
                    try { if (!release.await(30, TimeUnit.SECONDS)) throw new AssertionError("Slow source timed out"); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new AssertionError(e); }
                    return model.sample(x, z);
                }
            });
        DerivedRegionTerrainSource mixed = new DerivedRegionTerrainSource(root, 23, model.identity(),
            config, () -> slowRaw);
        CompletableFuture<Path> preparing = CompletableFuture.supplyAsync(() -> mixed.prepareRegion(2, 0));
        try {
            if (!entered.await(10, TimeUnit.SECONDS)) throw new AssertionError("Slow preparation did not start");
            CompletableFuture<Terrain.Column> cachedRead = CompletableFuture.supplyAsync(() -> mixed.sample(0, 0));
            cachedRead.get(2, TimeUnit.SECONDS);
        } finally { release.countDown(); }
        preparing.get(60, TimeUnit.SECONDS);

        AtomicInteger attempts = new AtomicInteger();
        DerivedRegionTerrainSource retry = new DerivedRegionTerrainSource(root.resolve("retry"), 23,
            model.identity(), config, () -> {
                if (attempts.getAndIncrement() == 0) throw new IllegalStateException("injected failure");
                return new RawRegionTerrainSource(root.resolve("retry"), 23, model.identity(),
                    RawRegionTerrainSource.TUNED_RECIPE, config, () -> model);
            });
        try { retry.prepareRegion(0, 0); throw new AssertionError("Injected failure was accepted"); }
        catch (IllegalStateException expected) { /* The failed owner must release its in-flight entry. */ }
        retry.prepareRegion(0, 0);
        if (attempts.get() != 2) throw new AssertionError("Failed region was not retried");
        System.out.println("PASS derived concurrent owner, cached read during slow prepare, retry");
    }
}
