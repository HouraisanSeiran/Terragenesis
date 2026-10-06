package com.remotemountains.diffusion;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class ManagedTerrainInstallation {
    static final String VERSION = "terrain-install-v1\n";

    private ManagedTerrainInstallation() {}

    static boolean installed(Path home) {
        try {
            if (!VERSION.equals(Files.readString(home.resolve(".install-ready"), StandardCharsets.UTF_8))
                || !Files.isRegularFile(home.resolve("python/.portable-ready"))
                || !Files.isRegularFile(home.resolve("runtime/upstream.json"))) return false;
            for (String file : new String[] {"python/python.exe", "python/python311.dll", "python/python311.zip", "python/python311._pth"})
                if (!Files.isRegularFile(home.resolve(file))) return false;
            if (!Files.readString(home.resolve("python/.portable-ready")).equals(PortablePythonInstaller.SHA256 + "\n")
                || Files.readAllLines(home.resolve("python/python311._pth")).stream().noneMatch("import site"::equals)) return false;
            Path model = home.resolve("models/terrain-diffusion-30m");
            JsonObject manifest = JsonParser.parseString(Files.readString(model.resolve("manifest.json"))).getAsJsonObject();
            for (var entry : manifest.getAsJsonObject("files").entrySet()) {
                Path file = model.resolve(entry.getKey()).normalize();
                if (!file.startsWith(model) || Files.size(file) != entry.getValue().getAsJsonObject().get("bytes").getAsLong()) return false;
            }
            JsonObject upstream = JsonParser.parseString(Files.readString(home.resolve("bootstrap-assets/upstream-manifest.json"))).getAsJsonObject();
            Path source = home.resolve(upstream.get("source").getAsString()).normalize();
            for (var entry : upstream.getAsJsonObject("files").entrySet()) {
                Path file = source.resolve(entry.getKey()).normalize();
                if (!file.startsWith(source) || Files.size(file) != entry.getValue().getAsJsonObject().get("bytes").getAsLong()) return false;
            }
            return true;
        } catch (Exception ex) { return false; }
    }

    static void markReady(Path home) throws IOException {
        Path part = home.resolve(".install-ready.part");
        Files.writeString(part, VERSION, StandardCharsets.UTF_8);
        Files.move(part, home.resolve(".install-ready"), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }
}
