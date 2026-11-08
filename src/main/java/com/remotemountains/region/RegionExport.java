package com.remotemountains.region;

import java.nio.file.Path;

/** Prepares a bounded rectangle of storage regions before visiting it in game. */
public final class RegionExport {
    private RegionExport() {}

    public static void main(String[] args) throws java.io.IOException {
        if (args.length != 7 && args.length != 8)
            throw new IllegalArgumentException("Usage: RegionExport <output-dir> <seed> <diffusion-identity-or-empty> <min-rx> <min-rz> <max-rx> <max-rz> [chunks]");
        Path directory = Path.of(args[0]).toAbsolutePath().normalize();
        long seed = Long.parseLong(args[1]);
        String identity = args[2];
        int minRx = Integer.parseInt(args[3]), minRz = Integer.parseInt(args[4]);
        int maxRx = Integer.parseInt(args[5]), maxRz = Integer.parseInt(args[6]);
        int chunks = args.length == 8 ? Integer.parseInt(args[7]) : RegionConfig.DEFAULT.chunks();
        RegionConfig config = new RegionConfig(chunks, RegionConfig.DEFAULT.processing());
        long countX = (long)maxRx - minRx + 1, countZ = (long)maxRz - minRz + 1;
        long bound = 30_000_000L / config.worldWidth();
        if (countX <= 0 || countZ <= 0 || countX * countZ > 4096
                || minRx < -bound || minRz < -bound || maxRx > bound || maxRz > bound)
            throw new IllegalArgumentException("Region rectangle must contain 1 to 4096 regions");
        System.setProperty("remotemountains.regionDir", directory.toString());
        RegionTerrainSource source = RegionRuntime.create(seed, identity, RegionTerrainSource.RECIPE,
            "relief_3x_sea62_1024_v1", config.chunks(), config.processing());
        for (int rz = minRz; rz <= maxRz; rz++) for (int rx = minRx; rx <= maxRx; rx++) {
            source.prepareRegion(rx, rz);
            RegionArtifact artifact = RegionArtifact.read(source.directory(), seed, source.identity(),
                    source.recipe(), config, rx, rz);
            System.out.println("Prepared region " + rx + "," + rz + " at " + RegionArtifact.path(source.directory(), rx, rz)
                + " sha256=" + artifact.identity());
        }
        System.out.println("Terrain Diffusion identity: " + source.identity());
    }
}
