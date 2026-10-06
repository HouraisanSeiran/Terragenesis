package com.remotemountains.diffusion;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/** End-to-end local service startup using the installed model and its own port. */
public final class ManagedServiceVerification {
    public static void main(String[] args) {
        if (args.length != 1) throw new IllegalArgumentException("Expected prepared terrain home");
        System.setProperty("remotemountains.diffusionHome", args[0]);
        System.setProperty("remotemountains.disableAutoBootstrap", "true");
        System.setProperty("remotemountains.diffusionUrl", "http://127.0.0.1:19892");
        System.setProperty("remotemountains.conditioningMode", "geographic_v1");
        if (healthy()) throw new AssertionError("Verification port is already occupied");
        System.setProperty("remotemountains.diffusionHome", java.nio.file.Path.of(args[0], "missing-terrain-home").toString());
        try {
            DiffusionServiceManager.ensureAvailable("");
            throw new AssertionError("Missing terrain home was accepted");
        } catch (IllegalStateException expected) {
            if (!expected.getMessage().contains("does not exist")) throw expected;
        }
        if (healthy()) throw new AssertionError("A service started despite missing assets");
        System.setProperty("remotemountains.diffusionHome", args[0]);
        try {
            DiffusionServiceManager.ensureAvailable("");
            DiffusionClient client = new DiffusionClient(20260928L, "");
            if (!client.identity().matches("[0-9a-f]{64}")) throw new AssertionError("Missing identity");
            DiffusionClient.Result sample = client.sample(0, 0);
            if (!Double.isFinite(sample.height())) throw new AssertionError("Non-finite terrain height");
            System.out.println("PASS managed terrain service: " + client.identity() + ", height=" + sample.height());
            try {
                DiffusionServiceManager.ensureAvailable("0000000000000000000000000000000000000000000000000000000000000000");
                throw new AssertionError("Mismatched model identity accepted");
            } catch (IllegalStateException expected) {
                if (!expected.getMessage().contains("different terrain model")) throw expected;
            }
        } finally {
            DiffusionServiceManager.shutdown();
            for (int attempt = 0; attempt < 20 && healthy(); attempt++) {
                try { Thread.sleep(250); }
                catch (InterruptedException ex) { Thread.currentThread().interrupt(); throw new IllegalStateException(ex); }
            }
            if (healthy()) throw new AssertionError("Managed terrain service stayed alive after shutdown");
        }
    }

    private static boolean healthy() {
        try {
            HttpResponse<Void> response = HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:19892/health"))
                .timeout(Duration.ofSeconds(1)).build(), HttpResponse.BodyHandlers.discarding());
            return response.statusCode() == 200;
        } catch (Exception ignored) { return false; }
    }
}
