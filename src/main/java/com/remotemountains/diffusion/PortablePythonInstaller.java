package com.remotemountains.diffusion;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class PortablePythonInstaller {
    private static final URI PYTHON_URL = URI.create("https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip");
    static final String SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b";
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(20))
        .followRedirects(HttpClient.Redirect.NORMAL).build();

    private PortablePythonInstaller() {}

    static Path install(Path home) throws IOException, InterruptedException {
        if (!System.getProperty("os.name", "").toLowerCase().contains("win"))
            throw new IllegalStateException("Automatic terrain runtime installation currently supports Windows x64 only");
        String arch = System.getProperty("os.arch", "").toLowerCase();
        if (!arch.equals("amd64") && !arch.equals("x86_64"))
            throw new IllegalStateException("Automatic terrain runtime installation requires Windows x64");
        Path python = home.resolve("python/python.exe");
        Path pth = home.resolve("python/python311._pth");
        Path ready = home.resolve("python/.portable-ready");
        if (Files.isRegularFile(python) && Files.isRegularFile(home.resolve("python/python311.dll"))
                && Files.isRegularFile(home.resolve("python/python311.zip")) && Files.isRegularFile(pth)
                && Files.isRegularFile(ready) && Files.readString(ready).equals(SHA256 + "\n")
                && Files.readAllLines(pth).stream().anyMatch("import site"::equals)) return python;
        Files.createDirectories(home.resolve("runtime/downloads"));
        Path archive = home.resolve("runtime/downloads/python-3.11.9-embed-amd64.zip");
        if (!Files.isRegularFile(archive) || !SHA256.equals(sha256(archive))) {
            Path partial = archive.resolveSibling(archive.getFileName() + ".part");
            Files.deleteIfExists(partial);
            HttpRequest request = HttpRequest.newBuilder(PYTHON_URL).timeout(Duration.ofMinutes(15)).GET().build();
            HttpResponse<Path> response = HTTP.send(request, HttpResponse.BodyHandlers.ofFile(partial));
            if (response.statusCode() != 200) throw new IOException("Python download failed: HTTP " + response.statusCode());
            if (!SHA256.equals(sha256(partial))) {
                Files.deleteIfExists(partial);
                throw new IOException("Python download checksum mismatch");
            }
            Files.move(partial, archive, StandardCopyOption.REPLACE_EXISTING);
        }
        Path root = home.resolve("python");
        Files.createDirectories(root);
        try (InputStream input = Files.newInputStream(archive); ZipInputStream zip = new ZipInputStream(input)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                Path target = root.resolve(entry.getName()).normalize();
                if (!target.startsWith(root)) throw new IOException("Unsafe Python archive entry: " + entry.getName());
                if (entry.isDirectory()) Files.createDirectories(target);
                else {
                    Files.createDirectories(target.getParent());
                    Files.copy(zip, target, StandardCopyOption.REPLACE_EXISTING);
                }
                zip.closeEntry();
            }
        }
        if (!Files.isRegularFile(python) || !Files.isRegularFile(pth)) throw new IOException("Incomplete Python archive");
        String contents = Files.readString(pth);
        Files.writeString(pth, contents.replace("#import site", "import site") + "\nLib/site-packages\n");
        if (!Files.readAllLines(pth).stream().anyMatch("import site"::equals)) throw new IOException("Python site packages are disabled");
        Path pending = home.resolve("python/.portable-ready.part");
        Files.writeString(pending, SHA256 + "\n");
        Files.move(pending, ready, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        return python;
    }

    private static String sha256(Path file) throws IOException {
        try (InputStream input = Files.newInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            for (int count; (count = input.read(buffer)) != -1;) digest.update(buffer, 0, count);
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
}
