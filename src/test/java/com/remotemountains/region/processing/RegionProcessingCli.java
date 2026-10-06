package com.remotemountains.region.processing;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Binary bridge for real-sample offline verification; big-endian float32 grids. */
public final class RegionProcessingCli {
    public static void main(String[] args) throws IOException {
        if (args.length != 7) throw new IllegalArgumentException(
                "Usage: RegionProcessingCli <input> <output> <width> <height> <worldX> <worldZ> <seed>");
        Path input = Path.of(args[0]), output = Path.of(args[1]);
        int width = Integer.parseInt(args[2]), height = Integer.parseInt(args[3]);
        float[] raw = new float[Math.multiplyExact(width, height)];
        try (DataInputStream in = new DataInputStream(Files.newInputStream(input))) {
            for (int i = 0; i < raw.length; i++) raw[i] = in.readFloat();
            if (in.read() != -1) throw new IOException("Extra input bytes");
        }
        long started = System.nanoTime();
        ProcessedTile tile = RegionProcessor.process(raw, width, height,
                Integer.parseInt(args[4]), Integer.parseInt(args[5]), Long.parseLong(args[6]), null);
        System.out.println(RegionProcessor.ALGORITHM_ID + " " + ((System.nanoTime() - started) / 1_000_000.0));
        try (DataOutputStream out = new DataOutputStream(Files.newOutputStream(output))) {
            for (float value : tile.heights()) out.writeFloat(value);
            for (float value : tile.weights()) out.writeFloat(value);
            out.write(tile.dominantTypes());
        }
    }
}
