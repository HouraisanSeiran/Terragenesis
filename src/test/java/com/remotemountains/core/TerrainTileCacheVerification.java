package com.remotemountains.core;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Deterministic coalescing, pressure, retry, and close checks. */
public final class TerrainTileCacheVerification {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger starts = new AtomicInteger();
        TerrainTileCache cache = new TerrainTileCache((x, z) -> {
            if (x % Terrain.TILE == 0 && z == 0) {
                starts.incrementAndGet();
                entered.countDown();
                try {
                    if (!release.await(10, TimeUnit.SECONDS)) throw new AssertionError("Timed out");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            }
            return null;
        });
        CompletableFuture<Terrain.Column[]> first = cache.tile(0, 0);
        if (first != cache.tile(0, 0)) throw new AssertionError("Same tile did not coalesce");
        CompletableFuture<Terrain.Column[]> second = cache.tile(1, 0);
        if (!entered.await(10, TimeUnit.SECONDS)) throw new AssertionError("Workers did not start");
        List<CompletableFuture<Terrain.Column[]>> pending = new ArrayList<>();
        for (int i = 2; i < 65; i++) pending.add(cache.tile(i, 0));
        CompletableFuture<Terrain.Column[]> pressured = pending.get(pending.size() - 1);
        if (pressured.isDone()) throw new AssertionError("Required tile failed under pressure");
        release.countDown();
        pressured.get(30, TimeUnit.SECONDS);
        if (starts.get() < 3) throw new AssertionError("Pressure request did not run");
        cache.close();
        if (!cache.tile(0, 0).isCompletedExceptionally()) throw new AssertionError("Closed cache accepted request");

        AtomicBoolean fail = new AtomicBoolean(true);
        TerrainTileCache retry = new TerrainTileCache((x, z) -> {
            if (fail.getAndSet(false)) throw new IllegalStateException("once");
            return null;
        });
        try {
            retry.tile(0, 0).get(10, TimeUnit.SECONDS);
            throw new AssertionError("Expected first failure");
        } catch (java.util.concurrent.ExecutionException expected) {
            // The next request must rebuild rather than receive the cached failure.
        }
        retry.tile(0, 0).get(10, TimeUnit.SECONDS);
        retry.close();

        CountDownLatch blocked = new CountDownLatch(1);
        CountDownLatch unblock = new CountDownLatch(1);
        TerrainTileCache closing = new TerrainTileCache((x, z) -> {
            blocked.countDown();
            try { unblock.await(); } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(interrupted);
            }
            return null;
        });
        CompletableFuture<Terrain.Column[]> active = closing.tile(0, 0);
        if (!blocked.await(10, TimeUnit.SECONDS)) throw new AssertionError("Close test did not start");
        for (int i = 1; i < 64; i++) closing.tile(i, 0);
        CompletableFuture<Terrain.Column[]> waiting = closing.tile(64, 0);
        closing.close();
        unblock.countDown();
        if (!active.isCancelled() || !waiting.isCompletedExceptionally()) {
            throw new AssertionError("Close left tile waiters pending");
        }
        System.out.println("TerrainTileCache verification passed");
    }
}