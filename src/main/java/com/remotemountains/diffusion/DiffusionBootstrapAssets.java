package com.remotemountains.diffusion;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;

final class DiffusionBootstrapAssets {
    private static final List<String> ROOT_FILES = List.of(
        "tools/bootstrap_diffusion.py",
        "bootstrap-assets/requirements-lock.txt",
        "bootstrap-assets/model-manifest.json",
        "bootstrap-assets/upstream-manifest.json"
    );

    private DiffusionBootstrapAssets() {}

    static void install(Path home) throws IOException {
        for (String name : ROOT_FILES) copy(home, name);
        // The upstream manifest lists exactly the Python files bundled into the mod JAR.
        Path manifest = home.resolve("bootstrap-assets/upstream-manifest.json");
        JsonObject source = JsonParser.parseString(Files.readString(manifest)).getAsJsonObject();
        String prefix = source.get("source").getAsString() + "/";
        JsonObject files = source.getAsJsonObject("files");
        if (files == null || files.isEmpty()) throw new IOException("Bundled terrain manifest has no files");
        for (String name : files.keySet()) copy(home, prefix + name);
    }

    private static void copy(Path home, String relative) throws IOException {
        Path target = home.resolve(relative).normalize();
        if (!target.startsWith(home)) throw new IOException("Unsafe bundled terrain asset path: " + relative);
        try (InputStream input = DiffusionBootstrapAssets.class.getResourceAsStream("/remotemountains-service/" + relative)) {
            if (input == null) throw new IOException("Mod is missing bundled terrain asset: " + relative);
            Files.createDirectories(target.getParent());
            Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
