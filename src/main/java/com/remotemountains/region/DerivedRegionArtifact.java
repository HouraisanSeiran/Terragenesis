package com.remotemountains.region;

import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.region.processing.ProcessedTile;
import com.remotemountains.region.processing.RegionProcessor;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.Arrays;

/** Versioned, self-contained processed surface and vertical displacement grid. */
final class DerivedRegionArtifact {
    private static final int MAGIC = 0x524d4431;
    private static final int VERSION = 1;
    private final int side;
    private final float[] raw, height, water, temperature, rain, weights;
    private final byte[] types, labels;

    private DerivedRegionArtifact(int side, float[] raw, float[] height, float[] water,
            float[] temperature, float[] rain, float[] weights, byte[] types, byte[] labels) {
        this.side = side; this.raw = raw; this.height = height; this.water = water;
        this.temperature = temperature; this.rain = rain; this.weights = weights; this.types = types; this.labels = labels;
    }

    static Path path(Path directory, int rx, int rz) {
        return directory.resolve("r." + rx + "." + rz + ".rmd");
    }

    static DerivedRegionArtifact prepare(Path directory, long seed, String expectedIdentity, int width,
            int rx, int rz, RawRegionTerrainSource source) throws IOException {
        int halo = RegionProcessor.REQUIRED_HALO_SAMPLES;
        int side = width / 2 + 1;
        int inputSide = side + 2 * halo;
        int originX = Math.subtractExact(Math.multiplyExact(rx, width), 2 * halo);
        int originZ = Math.subtractExact(Math.multiplyExact(rz, width), 2 * halo);
        float[] input = new float[inputSide * inputSide];
        float[] mask = new float[input.length];
        Terrain.Column[] sampled = source.sampleGrid(originX, originZ, inputSide, 2);
        for (int z = 0; z < inputSide; z++) for (int x = 0; x < inputSide; x++) {
            int i = z * inputSide + x;
            Terrain.Column c = sampled[i];
            input[i] = (float) c.height();
            // Shoreline remains attached to the original water surface.
            if (Double.isFinite(c.water())) mask[i] = (float) Math.max(0, 1 - Math.abs(c.height() - c.water()) / 8);
        }
        byte[] digest = digest(input, mask);
        ProcessedTile processed = RegionProcessor.process(input, inputSide, inputSide, originX, originZ, seed, mask);
        int n = side * side;
        float[] raw = new float[n], height = new float[n], water = new float[n];
        float[] temperature = new float[n], rain = new float[n], weights = new float[n * 4];
        byte[] types = new byte[n], labels = new byte[n];
        for (int z = 0; z < side; z++) for (int x = 0; x < side; x++) {
            int i = z * side + x, j = (z + halo) * inputSide + x + halo;
            Terrain.Column c = sampled[j];
            raw[i] = input[j]; height[i] = processed.heights()[j];
            water[i] = (float) c.water();
            temperature[i] = (float) c.base().climate().temperature();
            rain[i] = (float) c.base().climate().rain();
            types[i] = (byte) c.base().type().ordinal();
            labels[i] = processed.dominantTypes()[j];
            System.arraycopy(processed.weights(), j * 4, weights, i * 4, 4);
        }
        DerivedRegionArtifact artifact = new DerivedRegionArtifact(side, raw, height, water, temperature, rain, weights, types, labels);
        artifact.validate();
        Files.createDirectories(directory);
        Path target = path(directory, rx, rz), part = Files.createTempFile(directory, "derived-region-", ".part");
        try {
            String identity = source.identity();
            if (identity.isBlank()) throw new IOException("Missing tuned model identity");
            if (!expectedIdentity.isBlank() && !expectedIdentity.equals(identity))
                throw new IOException("Tuned source identity changed");
            byte[] payload = artifact.encode(seed, identity, width, rx, rz, digest);
            try (OutputStream out = Files.newOutputStream(part)) {
                out.write(payload); out.write(sha256(payload));
            }
            Files.move(part, target, StandardCopyOption.ATOMIC_MOVE);
        } finally { Files.deleteIfExists(part); }
        return artifact;
    }

    static DerivedRegionArtifact read(Path directory, long seed, String identity, int width,
            int rx, int rz) throws IOException {
        Path file = path(directory, rx, rz);
        int side = width / 2 + 1;
        long size = Files.size(file);
        if (size < 96 || size > 50L * side * side + 4096) throw new IOException("Invalid derived region size");
        byte[] bytes = Files.readAllBytes(file), payload = Arrays.copyOf(bytes, bytes.length - 32);
        if (!MessageDigest.isEqual(sha256(payload), Arrays.copyOfRange(bytes, payload.length, bytes.length)))
            throw new IOException("Derived region checksum mismatch");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION || in.readLong() != seed
                    || !in.readUTF().equals(identity) || !in.readUTF().equals(DerivedRegionTerrainSource.RECIPE)
                    || !in.readUTF().equals(RegionProcessor.ALGORITHM_ID)
                    || in.readInt() != width || in.readInt() != rx || in.readInt() != rz
                    || in.readInt() != Math.multiplyExact(rx, width) || in.readInt() != Math.multiplyExact(rz, width)
                    || in.readInt() != side) throw new IOException("Derived region identity mismatch");
            byte[] inputDigest = in.readNBytes(32);
            if (inputDigest.length != 32) throw new IOException("Missing source digest");
            int n = side * side;
            float[] raw = new float[n], height = new float[n], water = new float[n];
            float[] temperature = new float[n], rain = new float[n], weights = new float[n * 4];
            byte[] types = new byte[n], labels = new byte[n];
            for (int i = 0; i < n; i++) {
                raw[i] = in.readFloat(); float storedHeight = in.readFloat();
                float dx = in.readFloat(), dy = in.readFloat(), dz = in.readFloat();
                if (!Float.isFinite(storedHeight) || !Float.isFinite(dx) || !Float.isFinite(dy) || !Float.isFinite(dz)
                        || dx != 0 || dz != 0 || Math.abs(dy - (storedHeight - raw[i])) > .0001f)
                    throw new IOException("Invalid derived VDM");
                height[i] = raw[i] + dy;
                water[i] = in.readFloat(); temperature[i] = in.readFloat(); rain[i] = in.readFloat();
                types[i] = in.readByte();
                labels[i] = in.readByte();
                for (int k = 0; k < 4; k++) weights[i * 4 + k] = in.readFloat();
            }
            if (in.read() != -1) throw new IOException("Trailing derived data");
            DerivedRegionArtifact result = new DerivedRegionArtifact(side, raw, height, water, temperature, rain, weights, types, labels);
            result.validate();
            return result;
        }
    }

    private byte[] encode(long seed, String identity, int width, int rx, int rz, byte[] digest) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(MAGIC); out.writeInt(VERSION); out.writeLong(seed); out.writeUTF(identity);
            out.writeUTF(DerivedRegionTerrainSource.RECIPE); out.writeUTF(RegionProcessor.ALGORITHM_ID);
            out.writeInt(width); out.writeInt(rx); out.writeInt(rz);
            out.writeInt(Math.multiplyExact(rx, width)); out.writeInt(Math.multiplyExact(rz, width));
            out.writeInt(side); out.write(digest);
            for (int i = 0; i < raw.length; i++) {
                out.writeFloat(raw[i]); out.writeFloat(height[i]);
                out.writeFloat(0); out.writeFloat(height[i] - raw[i]); out.writeFloat(0);
                out.writeFloat(water[i]); out.writeFloat(temperature[i]); out.writeFloat(rain[i]);
                out.writeByte(types[i]);
                out.writeByte(labels[i]);
                for (int k = 0; k < 4; k++) out.writeFloat(weights[i * 4 + k]);
            }
        }
        return buffer.toByteArray();
    }

    Terrain.Column sample(int x, int z) {
        int ix = Math.min(x / 2, side - 2), iz = Math.min(z / 2, side - 2);
        double fx = (x - ix * 2) / 2.0, fz = (z - iz * 2) / 2.0;
        double h = bilerp(height, ix, iz, fx, fz), w = waterAt(ix, iz, fx, fz);
        if (Double.isFinite(w) && w <= h) w = Double.NaN;
        double t = bilerp(temperature, ix, iz, fx, fz), r = bilerp(rain, ix, iz, fx, fz);
        int i = (z / 2) * side + x / 2;
        var base = new Landscape.Base(h, Landform.values()[types[i]], new Landscape.Climate(t, r), 0);
        return new Terrain.Column(h, w, base);
    }

    static double coastalWater(float[] cells, int side, int i, double fx, double fz) {
        double a = (1 - fx) * (1 - fz), b = fx * (1 - fz);
        double c = (1 - fx) * fz, d = fx * fz;
        double sum = 0, weight = 0;
        if (Float.isFinite(cells[i])) { sum += cells[i] * a; weight += a; }
        if (Float.isFinite(cells[i + 1])) { sum += cells[i + 1] * b; weight += b; }
        if (Float.isFinite(cells[i + side])) { sum += cells[i + side] * c; weight += c; }
        if (Float.isFinite(cells[i + side + 1])) { sum += cells[i + side + 1] * d; weight += d; }
        return weight > 0 ? sum / weight : Double.NaN;
    }

    private double bilerp(float[] values, int x, int z, double fx, double fz) {
        int i = z * side + x;
        double a = values[i], b = values[i + 1], c = values[i + side], d = values[i + side + 1];
        if (Float.isNaN(values[i]) || Float.isNaN(values[i + 1]) || Float.isNaN(values[i + side]) || Float.isNaN(values[i + side + 1]))
            return Double.NaN;
        return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz;
    }

    private double waterAt(int x, int z, double fx, double fz) {
        return coastalWater(water, side, z * side + x, fx, fz);
    }

    private void validate() throws IOException {
        for (int i = 0; i < raw.length; i++) {
            if (!Float.isFinite(raw[i]) || !Float.isFinite(height[i]) || !Float.isFinite(temperature[i])
                    || !Float.isFinite(rain[i]) || !(Float.isFinite(water[i]) || Float.isNaN(water[i]))
                    || types[i] < 0 || types[i] > 3 || labels[i] < 0 || labels[i] > 3)
                throw new IOException("Invalid derived sample");
            float sum = 0;
            for (int k = 0; k < 4; k++) {
                float weight = weights[i * 4 + k];
                if (!Float.isFinite(weight) || weight < 0 || weight > 1) throw new IOException("Invalid region weight");
                sum += weight;
            }
            if (Math.abs(sum - 1) > .01f) throw new IOException("Region weights do not sum to one");
        }
    }

    private static byte[] digest(float[] input, float[] mask) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(input.length * 8);
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            for (float v : input) out.writeFloat(v);
            for (float v : mask) out.writeFloat(v);
        }
        return sha256(bytes.toByteArray());
    }

    private static byte[] sha256(byte[] data) {
        try { return MessageDigest.getInstance("SHA-256").digest(data); }
        catch (NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
}
