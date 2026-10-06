package com.remotemountains.diffusion;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

/** A running v1 service must never satisfy a new v2 world with an empty identity. */
public final class ProfileMismatchVerification {
    private ProfileMismatchVerification() {}

    public static void main(String[] args) throws Exception {
        Path home = Files.createTempDirectory(Path.of("build"), "profile-mismatch-");
        System.setProperty("remotemountains.diffusionHome", home.toAbsolutePath().toString());
        System.setProperty("remotemountains.disableAutoBootstrap", "true");
        System.setProperty("remotemountains.diffusionUrl", "http://127.0.0.1:19896");
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 19896), 0);
        server.createContext("/health", exchange -> {
            exchange.getResponseHeaders().set("X-Terrain-Identity", "0".repeat(64));
            exchange.getResponseHeaders().set("X-Blocks-Per-Pixel", "2");
            exchange.getResponseHeaders().set("X-Terrain-Profile", "geographic_v1");
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });
        server.start();
        try {
            try {
                DiffusionServiceManager.ensureAvailable("", "geographic_v2");
                throw new AssertionError("Accepted an external v1 service for a new v2 world");
            } catch (IllegalStateException expected) {
                if (!expected.getMessage().contains("different model profile")) throw expected;
            }
            DiffusionServiceManager.ensureAvailable("", "geographic_v1");
            System.out.println("PASS external service profile mismatch rejected");
        } finally {
            server.stop(0);
            System.clearProperty("remotemountains.disableAutoBootstrap");
        }
    }
}
