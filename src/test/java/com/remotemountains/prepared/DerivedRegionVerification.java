package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

/** Offline integration of immutable tuned input, derived cache, and seams. */
public final class DerivedRegionVerification {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory(Path.of("verification", "regions"), "derived-");
        RegionConfig config = new RegionConfig(3, "none_v1");
        near(DerivedRegionArtifact.coastalWater(new float[] {62, Float.NaN, 62, Float.NaN}, 2, 0, .5, .5), 62, 0);
        AtomicInteger calls = new AtomicInteger();
        BaseTerrainSource model = new BaseTerrainSource() {
            public String identity() { return "synthetic-derived-v1"; }
            public Terrain.Column sample(double x, double z) {
                calls.incrementAndGet();
                double h = 72 + 8 * Math.sin(x / 13) + 3 * Math.cos(z / 17);
                double water = h < 73 ? 72 : Double.NaN;
                return new Terrain.Column(h, water,
                    new Landscape.Base(h, Landform.KARST, new Landscape.Climate(.4, .6), 0));
            }
        };
        var tuned = new RawRegionTerrainSource(root, 17, model.identity(),
            RawRegionTerrainSource.TUNED_RECIPE, config, () -> model);
        tuned.prepareRegion(0, 0);
        tuned.sample(0, 0);
        byte[] rawBefore = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(RawRegionArtifact.path(tuned.directory(), 0, 0)));
        var source = new DerivedRegionTerrainSource(root, 17, "", config, () -> tuned);
        var missing = new DerivedRegionTerrainSource(root, 17, model.identity(), config,
            () -> { throw new AssertionError("Read-only miss invoked raw source"); });
        try {
            missing.sample(200, 0);
            throw new AssertionError("Normal-mode missing derived region accepted");
        } catch (IllegalStateException expected) {
            if (expected.getCause() == null || !expected.getCause().getMessage().contains("Missing prepared derived region"))
                throw expected;
        }
        Path left = source.prepareRegion(-1, 0), right = source.prepareRegion(0, 0);
        if (!source.identity().equals(model.identity())) throw new AssertionError("Blank identity was not resolved");
        if (calls.get() == 0 || source.directory().equals(tuned.directory()))
            throw new AssertionError("Derived source did not use isolated tuned input");
        var a = DerivedRegionArtifact.read(source.directory(), 17, model.identity(), 48, -1, 0);
        var b = DerivedRegionArtifact.read(source.directory(), 17, model.identity(), 48, 0, 0);
        for (int z = 0; z < 48; z++) {
            near(a.sample(48, z).height(), b.sample(0, z).height(), .0001);
        }
        if (!MessageDigest.isEqual(rawBefore, MessageDigest.getInstance("SHA-256").digest(
                Files.readAllBytes(RawRegionArtifact.path(tuned.directory(), 0, 0)))))
            throw new AssertionError("Derived preparation changed tuned input");
        try {
            new DerivedRegionTerrainSource(root, 17, "wrong-model", config, () -> tuned);
            throw new AssertionError("Mismatched model identity accepted");
        } catch (IllegalStateException expected) {
            if (!expected.getMessage().contains("identity")) throw expected;
        }
        var offline = new DerivedRegionTerrainSource(root, 17, model.identity(), config,
            () -> { throw new AssertionError("Offline derived read invoked raw source"); });
        System.setProperty("remotemountains.regionOffline", "true");
        try {
            near(offline.sample(-1, 0).height(), source.sample(-1, 0).height(), .0001);
            try { offline.sample(200, 0); throw new AssertionError("Missing derived region accepted"); }
            catch (IllegalStateException expected) {
                if (expected.getCause() == null || !expected.getCause().getMessage().contains("Missing offline derived region"))
                    throw expected;
            }
        } finally { System.clearProperty("remotemountains.regionOffline"); }
        byte[] valid = Files.readAllBytes(left);
        byte[] malformed = valid.clone();
        ByteArrayInputStream headerBytes = new ByteArrayInputStream(malformed);
        try (DataInputStream header = new DataInputStream(headerBytes)) {
            header.readInt(); header.readInt(); header.readLong();
            header.readUTF(); header.readUTF(); header.readUTF();
            for (int i = 0; i < 6; i++) header.readInt();
            header.skipNBytes(32);
            int storedHeightOffset = malformed.length - headerBytes.available() + Float.BYTES;
            ByteBuffer.wrap(malformed).putFloat(storedHeightOffset, Float.NaN);
        }
        byte[] checksum = MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(malformed, malformed.length - 32));
        System.arraycopy(checksum, 0, malformed, malformed.length - checksum.length, checksum.length);
        Files.write(left, malformed);
        try {
            DerivedRegionArtifact.read(source.directory(), 17, model.identity(), 48, -1, 0);
            throw new AssertionError("Non-finite stored height accepted");
        } catch (java.io.IOException expected) {
            if (!expected.getMessage().contains("VDM")) throw expected;
        }
        byte[] bytes = valid.clone();
        bytes[bytes.length - 1] ^= 1;
        Files.write(left, bytes);
        try {
            DerivedRegionArtifact.read(source.directory(), 17, model.identity(), 48, -1, 0);
            throw new AssertionError("Corrupt derived region accepted");
        } catch (java.io.IOException expected) {
            if (!expected.getMessage().contains("checksum")) throw expected;
        }
        if (!Files.exists(right)) throw new AssertionError("Missing positive derived region");
        System.out.println("PASS derived cache, immutable raw input, seam, offline reload, stored height, checksum");
    }

    private static void near(double actual, double expected, double tolerance) {
        if (!Double.isFinite(actual) || Math.abs(actual - expected) > tolerance)
            throw new AssertionError(actual + " != " + expected);
    }
}
