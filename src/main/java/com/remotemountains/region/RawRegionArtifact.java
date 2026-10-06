package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/** Immutable, unmodified model samples at Minecraft block coordinates. */
final class RawRegionArtifact {
    private static final int MAGIC = 0x524d5232;
    private final int width;
    private final double[] heights, waters, temperatures, rains;
    private final byte[] types;

    private RawRegionArtifact(int width, double[] heights, double[] waters,
            double[] temperatures, double[] rains, byte[] types) {
        this.width = width;
        this.heights = heights;
        this.waters = waters;
        this.temperatures = temperatures;
        this.rains = rains;
        this.types = types;
    }

    static Path path(Path directory, int rx, int rz) { return directory.resolve("r." + rx + "." + rz + ".rmraw"); }

    static RawRegionArtifact prepare(Path directory, long seed, String identity, String recipe, int width,
            int rx, int rz, BaseTerrainSource source) throws IOException {
        int n = Math.multiplyExact(width, width);
        double[] heights = new double[n], waters = new double[n], temperatures = new double[n], rains = new double[n];
        byte[] types = new byte[n];
        for (int z = 0; z < width; z++) for (int x = 0; x < width; x++) {
            int i = z * width + x;
            Terrain.Column c = source.sample(rx * (double) width + x, rz * (double) width + z);
            heights[i] = c.height(); waters[i] = c.water();
            temperatures[i] = c.base().climate().temperature(); rains[i] = c.base().climate().rain();
            types[i] = (byte) c.base().type().ordinal();
            check(heights[i], waters[i], temperatures[i], rains[i], types[i]);
        }
        Files.createDirectories(directory);
        Path target = path(directory, rx, rz), part = Files.createTempFile(directory, "raw-region-", ".part");
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (DataOutputStream out = new DataOutputStream(buffer)) {
                out.writeInt(MAGIC); out.writeInt(1); out.writeLong(seed); out.writeUTF(identity);
                out.writeUTF(recipe); out.writeInt(width); out.writeInt(rx); out.writeInt(rz);
                for (int i = 0; i < n; i++) {
                    out.writeDouble(heights[i]); out.writeDouble(waters[i]); out.writeDouble(temperatures[i]);
                    out.writeDouble(rains[i]); out.writeByte(types[i]);
                }
            }
            byte[] payload = buffer.toByteArray();
            try (DataOutputStream out = new DataOutputStream(Files.newOutputStream(part))) {
                out.write(payload); out.write(sha256(payload));
            }
            Files.move(part, target, StandardCopyOption.ATOMIC_MOVE);
        } finally { Files.deleteIfExists(part); }
        return new RawRegionArtifact(width, heights, waters, temperatures, rains, types);
    }

    static RawRegionArtifact read(Path directory, long seed, String identity, String recipe, int width,
            int rx, int rz) throws IOException {
        Path file = path(directory, rx, rz);
        long length = Files.size(file);
        if (length < 64 || length > 33L * width * width + 4096) throw new IOException("Invalid raw region size");
        byte[] bytes = Files.readAllBytes(file);
        byte[] payload = Arrays.copyOf(bytes, bytes.length - 32);
        if (!MessageDigest.isEqual(sha256(payload), Arrays.copyOfRange(bytes, bytes.length - 32, bytes.length)))
            throw new IOException("Raw region checksum mismatch");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload))) {
            if (in.readInt() != MAGIC || in.readInt() != 1 || in.readLong() != seed
                    || !in.readUTF().equals(identity) || !in.readUTF().equals(recipe)
                    || in.readInt() != width || in.readInt() != rx || in.readInt() != rz)
                throw new IOException("Raw region identity or layout mismatch");
            int n = width * width;
            double[] heights = new double[n], waters = new double[n], temperatures = new double[n], rains = new double[n];
            byte[] types = new byte[n];
            for (int i = 0; i < n; i++) {
                heights[i] = in.readDouble(); waters[i] = in.readDouble(); temperatures[i] = in.readDouble();
                rains[i] = in.readDouble(); types[i] = in.readByte();
                check(heights[i], waters[i], temperatures[i], rains[i], types[i]);
            }
            if (in.read() != -1) throw new IOException("Trailing raw region data");
            return new RawRegionArtifact(width, heights, waters, temperatures, rains, types);
        }
    }

    Terrain.Column sample(int x, int z) {
        int i = z * width + x;
        double height = TerrainScale.RAW_MODEL.height(heights[i]);
        double water = Double.isFinite(waters[i]) ? TerrainScale.RAW_MODEL.height(waters[i]) : Double.NaN;
        var base = new Landscape.Base(height, Landform.values()[types[i]],
            new Landscape.Climate(temperatures[i], rains[i]), 0);
        return new Terrain.Column(height, water, base);
    }

    private static void check(double h, double w, double t, double r, byte type) throws IOException {
        if (!Double.isFinite(h) || !(Double.isNaN(w) || Double.isFinite(w))
                || !Double.isFinite(t) || !Double.isFinite(r) || type < 0 || type >= Landform.values().length)
            throw new IOException("Invalid raw model sample");
    }

    private static byte[] sha256(byte[] data) {
        try { return MessageDigest.getInstance("SHA-256").digest(data); }
        catch (NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
}
