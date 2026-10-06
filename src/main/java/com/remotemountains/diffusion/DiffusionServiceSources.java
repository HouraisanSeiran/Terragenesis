package com.remotemountains.diffusion;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class DiffusionServiceSources {
    private static final String[] SOURCES = {"__init__.py", "__main__.py", "backend.py", "config.py", "geography.py", "geography_v2.py", "geographic_noise.py", "paths.py", "preview.py", "service.py", "store.py"};

    private DiffusionServiceSources() {}

    static Path install(Path home) {
        Path root = home.resolve("service-0.12.0");
        Path packageDir = root.resolve("diffusion");
        try {
            Files.createDirectories(packageDir);
            for (String name : SOURCES) {
                try (InputStream stream = DiffusionServiceSources.class.getResourceAsStream("/remotemountains-service/diffusion/" + name)) {
                    if (stream == null) throw new IllegalStateException("Mod is missing bundled terrain service source: " + name);
                    Files.copy(stream, packageDir.resolve(name), StandardCopyOption.REPLACE_EXISTING);
                }
            }
        } catch (IOException ex) { throw new IllegalStateException("Could not install terrain service into " + root, ex); }
        return root;
    }
}
