package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainPreparation;
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/** Reads one finite, verified Python export; all processing finished before construction. */
public final class MetricProcessedTerrainSource implements BaseTerrainSource, TerrainPreparation {
    public static final String RECIPE = "metric-processed-surface-v1";
    private static final byte[] MAGIC = "TGMCMT01".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    private static final int MAX_SAMPLES = 16_000_000;
    private static final Landscape.Climate ADAPTER_CLIMATE = new Landscape.Climate(0.5, 0.5);

    private final Path path;
    private final String identity;
    private final double originX, originZ, spacingX, spacingZ, coreSea;
    private final int columns, rows, minX, minZ, maxX, maxZ;
    private final double[] elevation;
    private final byte[] landforms;

    public MetricProcessedTerrainSource(Path path, long seed, String expectedIdentity) {
        this.path = path;
        try {
            long fileSize = Files.size(path);
            if (!Files.isRegularFile(path) || fileSize < 8 + 4 + 8 + 128 + 40 + 24 + 32
                    || fileSize > 8 + 4 + 8 + 128 + 40 + 24 + (long) MAX_SAMPLES * 9 + 32) {
                throw new IOException("Metric snapshot is incomplete");
            }
            byte[] bytes = Files.readAllBytes(path);
            byte[] body = Arrays.copyOf(bytes, bytes.length - 32);
            if (!MessageDigest.isEqual(sha256(body), Arrays.copyOfRange(bytes, body.length, bytes.length))) {
                throw new IOException("Metric snapshot checksum mismatch");
            }
            try (DataInputStream input = new DataInputStream(new ByteArrayInputStream(body))) {
                if (!Arrays.equals(input.readNBytes(8), MAGIC) || input.readInt() != 1 || input.readLong() != seed) {
                    throw new IOException("Metric snapshot version or seed mismatch");
                }
                identity = new String(input.readNBytes(64), java.nio.charset.StandardCharsets.US_ASCII);
                if (!identity.matches("[0-9a-f]{64}") || (!expectedIdentity.isBlank() && !expectedIdentity.equals(identity))) {
                    throw new IOException("Metric snapshot identity mismatch");
                }
                String sourceContentId = new String(input.readNBytes(64), java.nio.charset.StandardCharsets.US_ASCII);
                if (!sourceContentId.matches("[0-9a-f]{64}")) {
                    throw new IOException("Invalid source content identity");
                }
                byte[] content = new byte[body.length - 64];
                System.arraycopy(body, 0, content, 0, 20);
                System.arraycopy(body, 84, content, 20, body.length - 84);
                if (!identity.equals(hex(sha256(content)))) {
                    throw new IOException("Metric snapshot identity does not match content");
                }
                originX = input.readDouble();
                originZ = input.readDouble();
                spacingX = input.readDouble();
                spacingZ = input.readDouble();
                coreSea = input.readDouble();
                columns = input.readInt();
                rows = input.readInt();
                minX = input.readInt();
                minZ = input.readInt();
                maxX = input.readInt();
                maxZ = input.readInt();
                long count = (long) columns * rows;
                if (columns < 2 || rows < 2 || count > MAX_SAMPLES || count <= 0
                        || body.length != 8 + 4 + 8 + 128 + 40 + 24 + count * 9
                        || !Double.isFinite(originX) || !Double.isFinite(originZ)
                        || !Double.isFinite(spacingX) || !Double.isFinite(spacingZ)
                        || !Double.isFinite(coreSea) || spacingX <= 0 || spacingZ <= 0
                        || minX >= maxX || minZ >= maxZ || Math.floorMod(minX, 64) != 0
                        || Math.floorMod(minZ, 64) != 0 || Math.floorMod(maxX, 64) != 0
                        || Math.floorMod(maxZ, 64) != 0 || minX < originX || minZ < originZ
                        || !Double.isFinite(originX + (columns - 1) * spacingX)
                        || !Double.isFinite(originZ + (rows - 1) * spacingZ)
                        || maxX > originX + (columns - 1) * spacingX
                        || maxZ > originZ + (rows - 1) * spacingZ) {
                    throw new IOException("Invalid finite metric grid");
                }
                elevation = new double[(int) count];
                for (int i = 0; i < elevation.length; i++) {
                    elevation[i] = input.readDouble();
                    double gameY = elevation[i] - coreSea + 62;
                    if (!Double.isFinite(gameY) || gameY < -64 || gameY > 1022) {
                        throw new IOException("Metric elevation exceeds Minecraft build height");
                    }
                }
                landforms = input.readNBytes((int) count);
                if (landforms.length != count) {
                    throw new IOException("Missing landform labels");
                }
                for (byte label : landforms) {
                    if (label < 0 || label > 3) {
                        throw new IOException("Invalid landform label");
                    }
                }
            }
        } catch (IOException failure) {
            throw new IllegalStateException("Cannot read prepared metric terrain " + path, failure);
        }
    }

    @Override public String identity() { return identity; }
    public String recipe() { return RECIPE; }

    @Override public Terrain.Column sample(double x, double z) {
        if (!Double.isFinite(x) || !Double.isFinite(z) || x < minX || z < minZ || x >= maxX || z >= maxZ) {
            throw new IllegalArgumentException("Outside prepared finite metric world");
        }
        double gridX = (x - originX) / spacingX;
        double gridZ = (z - originZ) / spacingZ;
        int ix = (int) Math.floor(gridX);
        int iz = (int) Math.floor(gridZ);
        if (ix < 0 || iz < 0 || ix >= columns - 1 || iz >= rows - 1) {
            throw new IllegalStateException("Missing interpolation neighbors");
        }
        double fx = gridX - ix;
        double fz = gridZ - iz;
        int offset = iz * columns + ix;
        double upper = elevation[offset] * (1 - fx) + elevation[offset + 1] * fx;
        double lower = elevation[offset + columns] * (1 - fx) + elevation[offset + columns + 1] * fx;
        double height = (upper * (1 - fz) + lower * fz) - coreSea + 62;
        // These four categories only select Minecraft biomes; the source contains no climate field.
        Landform type = Landform.values()[landforms[offset]];
        Landscape.Base base = new Landscape.Base(height, type, ADAPTER_CLIMATE, 0);
        return new Terrain.Column(height, Double.NaN, base);
    }

    @Override public Path prepareRegion(int regionX, int regionZ) {
        throw new UnsupportedOperationException("Metric world is prepared only by explicit Python export");
    }

    @Override public void prepareBounds(int minWorldX, int minWorldZ, int maxWorldXInclusive, int maxWorldZInclusive) {
        if (minWorldX < minX || minWorldZ < minZ || maxWorldXInclusive >= maxX || maxWorldZInclusive >= maxZ
                || minWorldX > maxWorldXInclusive || minWorldZ > maxWorldZInclusive) {
            throw new IllegalArgumentException("Outside prepared finite metric world");
        }
    }

    private static byte[] sha256(byte[] body) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(body);
        } catch (NoSuchAlgorithmException failure) {
            throw new IllegalStateException(failure);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(Character.forDigit((value >>> 4) & 15, 16));
            result.append(Character.forDigit(value & 15, 16));
        }
        return result.toString();
    }
}
