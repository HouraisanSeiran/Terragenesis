package com.remotemountains.diffusion;

import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

/** Two JVM integration probe for a real installed terrain runtime. */
public final class FirstInstallProbe {
    private static final int PORT = 19894;

    private FirstInstallProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !(args[0].equals("first") || args[0].equals("cold")))
            throw new IllegalArgumentException("Usage: FirstInstallProbe first|cold HOME");
        Path home = Path.of(args[1]).toAbsolutePath().normalize();
        System.setProperty("remotemountains.diffusionHome", home.toString());
        System.setProperty("remotemountains.diffusionUrl", "http://127.0.0.1:" + PORT);
        System.setProperty("remotemountains.conditioningMode", "geographic_v1");
        System.clearProperty("remotemountains.disableAutoBootstrap");
        Path marker = home.resolve(".install-ready");
        try (ServerSocket guard = new ServerSocket()) {
            guard.bind(new InetSocketAddress("127.0.0.1", PORT));
        }
        if (args[0].equals("first")) {
            if (Files.exists(marker)) throw new AssertionError("First run already has an install marker");
            var task = DiffusionServiceManager.startFirstRunInstall();
            if (Files.exists(marker)) throw new AssertionError("Marker written before installation finished");
            task.get(35, TimeUnit.MINUTES);
            if (!Files.isRegularFile(marker) || !ManagedTerrainInstallation.installed(home))
                throw new AssertionError("Healthy first install did not write a complete marker");
            DiffusionServiceManager.ensureAvailable("");
            if (DiffusionServiceManager.status().stage() != DiffusionServiceManager.Stage.READY)
                throw new AssertionError("Service did not reach READY stage");
            DiffusionServiceManager.shutdown();
            System.out.println("PASS first install: healthy service and complete marker at " + home);
        } else {
            if (!ManagedTerrainInstallation.installed(home)) throw new AssertionError("Cold home is not fully installed");
            long before = Files.getLastModifiedTime(marker).toMillis();
            try (ServerSocket blocked = new ServerSocket()) {
                blocked.bind(new InetSocketAddress("127.0.0.1", PORT));
                DiffusionServiceManager.startFirstRunInstall().get(5, TimeUnit.SECONDS);
                if (DiffusionServiceManager.status().stage() != DiffusionServiceManager.Stage.READY)
                    throw new AssertionError("Cold startup did not report installed state");
            }
            if (Files.getLastModifiedTime(marker).toMillis() != before)
                throw new AssertionError("Cold startup rewrote the install marker");
            System.out.println("PASS cold startup: completed without binding or checking the occupied service port");
        }
    }
}
