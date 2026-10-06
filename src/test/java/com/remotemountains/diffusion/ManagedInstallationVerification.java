package com.remotemountains.diffusion;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Exercises the install marker and future lifecycle without network or a model service. */
public final class ManagedInstallationVerification {
    private ManagedInstallationVerification() {}

    public static void main(String[] args) throws Exception {
        Path home = Files.createTempDirectory(Path.of("build"), "installation-verification-").toAbsolutePath();
        System.setProperty("remotemountains.diffusionHome", home.toString());
        System.clearProperty("remotemountains.disableAutoBootstrap");
        if (ManagedTerrainInstallation.installed(home)) throw new AssertionError("Empty install accepted");

        CompletableFuture<Void> pending = new CompletableFuture<>();
        setTask(pending);
        if (DiffusionServiceManager.startFirstRunInstall() != pending
                || DiffusionServiceManager.startFirstRunInstall() != pending)
            throw new AssertionError("Concurrent installation did not share one future");
        CountDownLatch waiting = new CountDownLatch(1);
        AtomicReference<Throwable> threadFailure = new AtomicReference<>();
        Thread consumer = new Thread(() -> {
            waiting.countDown();
            try {
                DiffusionServiceManager.ensureAvailable("");
                throw new AssertionError("Failed installation was ignored");
            } catch (IllegalStateException expected) {
                if (!expected.getMessage().contains("Terrain installation failed")) threadFailure.set(expected);
            } catch (Throwable failure) {
                threadFailure.set(failure);
            }
        }, "install-future-consumer");
        consumer.setDaemon(true);
        consumer.start();
        if (!waiting.await(2, TimeUnit.SECONDS)) throw new AssertionError("Install waiter did not start");
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (consumer.getState() != Thread.State.WAITING && System.nanoTime() < deadline) Thread.sleep(5);
        if (consumer.getState() != Thread.State.WAITING) throw new AssertionError("Install waiter did not join pending future");
        Thread completer = new Thread(() -> {
            synchronized (DiffusionServiceManager.class) {
                pending.completeExceptionally(new IllegalStateException("offline test failure"));
            }
        }, "install-future-completer");
        completer.setDaemon(true);
        completer.start();
        completer.join(2000);
        consumer.join(2000);
        if (completer.isAlive() || consumer.isAlive()) throw new AssertionError("Install future blocked under manager lock");
        if (threadFailure.get() != null) throw new AssertionError("Install failure was not propagated", threadFailure.get());
        setTask(null);

        createMarkerFixture(home);
        if (!ManagedTerrainInstallation.installed(home)) throw new AssertionError("Complete fixture not accepted");
        CompletableFuture<Void> ready = DiffusionServiceManager.startFirstRunInstall();
        if (!ready.isDone() || ready.isCompletedExceptionally()) throw new AssertionError("Installed marker started an installer");
        if (DiffusionServiceManager.status().stage() != DiffusionServiceManager.Stage.READY)
            throw new AssertionError("Installed state was not reported ready");
        Files.delete(home.resolve("python/python311.dll"));
        if (ManagedTerrainInstallation.installed(home)) throw new AssertionError("Incomplete runtime was accepted");
        System.out.println("PASS managed installation marker, shared future, and failure propagation");
    }

    private static void setTask(CompletableFuture<Void> task) throws Exception {
        Field field = DiffusionServiceManager.class.getDeclaredField("installTask");
        field.setAccessible(true);
        field.set(null, task);
    }

    private static void createMarkerFixture(Path home) throws Exception {
        for (String name : new String[] {"python/python.exe", "python/python311.dll", "python/python311.zip",
                "python/python311._pth", "python/.portable-ready", "runtime/upstream.json"}) {
            Path file = home.resolve(name);
            Files.createDirectories(file.getParent());
            Files.writeString(file, switch (name) {
                case "python/.portable-ready" -> PortablePythonInstaller.SHA256 + "\n";
                case "python/python311._pth" -> "import site\n";
                default -> "fixture";
            });
        }
        Path model = home.resolve("models/terrain-diffusion-30m");
        Files.createDirectories(model);
        Files.writeString(model.resolve("weights.bin"), "test");
        Files.writeString(model.resolve("manifest.json"), "{\"files\":{\"weights.bin\":{\"bytes\":4}}}");
        Path assets = home.resolve("bootstrap-assets");
        Files.createDirectories(assets);
        Files.writeString(assets.resolve("upstream-manifest.json"), "{\"source\":\"vendor/test\",\"files\":{\"code.py\":{\"bytes\":4}}}");
        Path upstream = home.resolve("vendor/test/code.py");
        Files.createDirectories(upstream.getParent());
        Files.writeString(upstream, "pass");
        ManagedTerrainInstallation.markReady(home);
    }
}
