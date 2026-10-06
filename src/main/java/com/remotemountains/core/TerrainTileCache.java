package com.remotemountains.core;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;

/** Bounded asynchronous height-tile cache; sampling never runs under the cache lock. */
final class TerrainTileCache implements AutoCloseable {
    @FunctionalInterface
    interface Sampler {
        Terrain.Column sample(double x, double z);
    }

    private static final int WORKER_COUNT = 2;
    private static final int MAX_ENTRIES = 64;
    private static final int PREFETCH_LIMIT = 48;

    private final Sampler sampler;
    private final ExecutorService workers = Executors.newFixedThreadPool(WORKER_COUNT,
            Thread.ofPlatform().daemon().name("remote-terrain-", 0).factory());
    private final LinkedHashMap<Long, CompletableFuture<Terrain.Column[]>> cache =
            new LinkedHashMap<>(32, .75f, true);
    private boolean closed;

    TerrainTileCache(Sampler sampler) {
        this.sampler = sampler;
    }

    CompletableFuture<Terrain.Column[]> tile(int tx, int tz) {
        long key = ((long) tx << 32) ^ (tz & 0xffffffffL);
        synchronized (cache) {
            if (closed) return CompletableFuture.failedFuture(new IllegalStateException("Tile cache closed"));
            CompletableFuture<Terrain.Column[]> existing = cache.get(key);
            if (existing != null) return existing;
            if (cache.size() >= MAX_ENTRIES) {
                cache.entrySet().removeIf(entry -> entry.getValue().isDone());
            }
            if (cache.size() >= MAX_ENTRIES) {
                return waitForCapacity(tx, tz);
            }
            CompletableFuture<Terrain.Column[]> future = new CompletableFuture<>();
            cache.put(key, future);
            try {
                workers.execute(() -> {
                    try {
                        if (!future.isCancelled()) future.complete(build(tx, tz));
                    } catch (Throwable failure) {
                        synchronized (cache) {
                            cache.remove(key, future);
                        }
                        future.completeExceptionally(failure);
                    }
                });
            } catch (RejectedExecutionException failure) {
                cache.remove(key);
                future.completeExceptionally(failure);
            }
            return future;
        }
    }

    private CompletableFuture<Terrain.Column[]> waitForCapacity(int tx, int tz) {
        CompletableFuture<Terrain.Column[]> oldest = cache.values().iterator().next();
        return oldest.handle((ignored, failure) -> null).thenCompose(ignored -> tile(tx, tz));
    }
    void prefetch(int tx, int tz) {
        synchronized (cache) {
            if (closed || cache.size() >= PREFETCH_LIMIT) return;
        }
        tile(tx + 1, tz);
        tile(tx - 1, tz);
        tile(tx, tz + 1);
        tile(tx, tz - 1);
    }

    private Terrain.Column[] build(int tx, int tz) {
        Terrain.Column[] result = new Terrain.Column[Terrain.TILE * Terrain.TILE];
        for (int z = 0; z < Terrain.TILE; z++) {
            for (int x = 0; x < Terrain.TILE; x++) {
                result[z * Terrain.TILE + x] = sampler.sample(tx * Terrain.TILE + x,
                        tz * Terrain.TILE + z);
            }
        }
        return result;
    }

    @Override
    public void close() {
        synchronized (cache) {
            if (closed) return;
            closed = true;
            for (Map.Entry<Long, CompletableFuture<Terrain.Column[]>> entry : cache.entrySet()) {
                entry.getValue().cancel(true);
            }
            cache.clear();
        }
        workers.shutdownNow();
    }
}