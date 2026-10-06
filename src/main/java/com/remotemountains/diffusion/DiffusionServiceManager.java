package com.remotemountains.diffusion;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.StandardOpenOption;

/** Starts the bundled Python service against a prepared, local model runtime. */
public final class DiffusionServiceManager {
    public enum Stage { NOT_STARTED, DOWNLOADING, INSTALLING, STARTING, READY, FAILED }
    public record InstallationStatus(Stage stage, String message, String failure) {}
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    private static volatile Process owned;
    private static volatile String ownedProfile;
    private static volatile Process installing;
    private static volatile boolean closing;
    private static final Object PROCESS_LOCK = new Object();
    private static volatile InstallationStatus status = new InstallationStatus(Stage.NOT_STARTED, "Preparing terrain service", null);
    private static CompletableFuture<Void> installTask;
    private static final ThreadLocal<Boolean> INSTALLING = ThreadLocal.withInitial(() -> false);

    static { Runtime.getRuntime().addShutdownHook(new Thread(DiffusionServiceManager::shutdownAll, "terrain-service-shutdown")); }

    private DiffusionServiceManager() {}

    public static InstallationStatus status() { return status; }

    public static synchronized CompletableFuture<Void> startFirstRunInstall() {
        if (Boolean.getBoolean("remotemountains.disableAutoBootstrap")) return CompletableFuture.completedFuture(null);
        try {
            if (installTask != null) {
                if (!installTask.isDone() || installTask.isCompletedExceptionally() || ManagedTerrainInstallation.installed(home())) return installTask;
                installTask = null;
            }
            if (ManagedTerrainInstallation.installed(home())) { status = new InstallationStatus(Stage.READY, "Terrain service is installed", null); return CompletableFuture.completedFuture(null); }
        } catch (RuntimeException ex) {
            status = new InstallationStatus(Stage.FAILED, "Terrain installation failed", ex.getMessage());
            return CompletableFuture.failedFuture(ex);
        }
        installTask = CompletableFuture.runAsync(() -> {
            try {
                INSTALLING.set(true);
                Path root = home(); Files.createDirectories(root);
                try (FileChannel channel = FileChannel.open(root.resolve(".install.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
                     FileLock lock = channel.lock()) {
                if (ManagedTerrainInstallation.installed(root)) { status = new InstallationStatus(Stage.READY, "Terrain service is installed", null); return; }
                status = new InstallationStatus(Stage.DOWNLOADING, "Downloading terrain runtime and model (several GB)", null);
                DiffusionBootstrapAssets.install(root);
                Path python = PortablePythonInstaller.install(root);
                status = new InstallationStatus(Stage.INSTALLING, "Installing terrain dependencies and model (several GB)", null);
                ProcessBuilder setup = new ProcessBuilder(python.toString(), "-X", "utf8", "-B", root.resolve("tools/bootstrap_diffusion.py").toString(), "--home", root.toString());
                setup.directory(root.toFile()); setup.redirectErrorStream(true); setup.redirectOutput(ProcessBuilder.Redirect.appendTo(root.resolve("terrain-install.log").toFile()));
                Process process;
                synchronized (PROCESS_LOCK) {
                    if (closing) throw new IllegalStateException("Game is closing during terrain installation");
                    process = setup.start();
                    installing = process;
                }
                try {
                    if (process.waitFor() != 0) throw new IllegalStateException("Terrain installation failed. See " + root.resolve("terrain-install.log"));
                } finally { synchronized (PROCESS_LOCK) { if (installing == process) installing = null; } }
                if (closing) throw new IllegalStateException("Game closed during terrain installation");
                status = new InstallationStatus(Stage.STARTING, "Starting terrain service and checking the model", null);
                ensureService("", "geographic_v2");
                ManagedTerrainInstallation.markReady(root);
                status = new InstallationStatus(Stage.READY, "Terrain service ready", null);
                }
            } catch (Exception ex) { status = new InstallationStatus(Stage.FAILED, "Terrain installation failed", ex.getMessage()); throw new CompletionException(ex); }
            finally { INSTALLING.remove(); }
        });
        return installTask;
    }

    public static synchronized CompletableFuture<Void> retryFirstRunInstall() { if (installTask != null && !installTask.isDone()) return installTask; installTask = null; return startFirstRunInstall(); }

    public static void ensureAvailable(String expectedIdentity) {
        ensureAvailable(expectedIdentity, "geographic_v1");
    }

    public static void ensureAvailable(String expectedIdentity, String profile) {
        CompletableFuture<Void> task = startFirstRunInstall();
        if (INSTALLING.get()) task = CompletableFuture.completedFuture(null);
        try { task.join(); } catch (CompletionException ex) { throw new IllegalStateException("Terrain installation failed", ex.getCause()); }
        ensureService(expectedIdentity, profile);
    }

    private static synchronized void ensureService(String expectedIdentity, String profile) {
        if (!profile.equals("geographic_v1") && !profile.equals("geographic_v2"))
            throw new IllegalArgumentException("Unsupported terrain profile: " + profile);
        URI endpoint = endpoint();
        String identity = health(endpoint);
        if (identity != null && !profileMatches(endpoint, profile)) {
            if (owned == null) throw new IllegalStateException("An external terrain service uses a different model profile");
            shutdown();
            for (int i = 0; i < 20 && (identity = health(endpoint)) != null; i++) {
                try { Thread.sleep(250); }
                catch (InterruptedException ex) { Thread.currentThread().interrupt(); throw new IllegalStateException("Terrain service switch interrupted", ex); }
            }
            if (identity != null) throw new IllegalStateException("Previous terrain service did not stop for profile switch");
        }
        if (identity == null) {
            if (owned != null && owned.isAlive()) throw new IllegalStateException("The managed terrain service is running but not healthy. See its log in the terrain home folder.");
            Path home = home();
            if (!Files.isDirectory(home)) throw new IllegalStateException("Terrain home does not exist: " + home);
            Path python = home.resolve("python/python.exe");
            if (!Files.isRegularFile(python)) python = home.resolve("runtime/venv/Scripts/python.exe");
            if (!Files.isRegularFile(python)) python = home.resolve("runtime/venv/bin/python");
            if (!Files.isRegularFile(python)) throw new IllegalStateException("Terrain runtime is missing in " + home);
            if (!Files.isRegularFile(home.resolve("models/terrain-diffusion-30m/manifest.json")) || !Files.isRegularFile(home.resolve("runtime/upstream.json")))
                throw new IllegalStateException("Terrain model files are missing in " + home + ". Prepare the model before opening this world.");
            if (endpoint.getPort() < 1 || !"127.0.0.1".equals(endpoint.getHost()))
                throw new IllegalStateException("Automatic terrain startup requires a loopback port");
            Path service = DiffusionServiceSources.install(home);
            String mode = profile;
            ProcessBuilder builder = new ProcessBuilder(List.of(python.toString(), "-X", "utf8", "-B", "-c",
                "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=['diffusion','--port',sys.argv[2],'--conditioning-mode',sys.argv[3]];runpy.run_module('diffusion',run_name='__main__')",
                service.toString(), Integer.toString(endpoint.getPort()), mode));
            builder.directory(home.toFile());
            builder.environment().put("REMOTEMOUNTAINS_DIFFUSION_HOME", home.toString());
            builder.environment().put("PYTHONPATH", service.toString());
            builder.environment().put("PYTHONDONTWRITEBYTECODE", "1");
            builder.redirectErrorStream(true);
            builder.redirectOutput(ProcessBuilder.Redirect.appendTo(home.resolve("terrain-service.log").toFile()));
            Process serviceProcess;
            try {
                synchronized (PROCESS_LOCK) {
                    if (closing) throw new IllegalStateException("Game is closing during terrain startup");
                    serviceProcess = builder.start();
                    owned = serviceProcess;
                    ownedProfile = profile;
                }
            }
            catch (IOException ex) { throw new IllegalStateException("Could not start the local terrain service. See " + home, ex); }
            long deadline = System.nanoTime() + Duration.ofMinutes(3).toNanos();
            try {
                while ((identity = health(endpoint)) == null && System.nanoTime() < deadline) {
                    if (closing || !serviceProcess.isAlive()) throw new IllegalStateException("Terrain service stopped during startup. See " + home.resolve("terrain-service.log"));
                    try { Thread.sleep(500); }
                    catch (InterruptedException ex) { Thread.currentThread().interrupt(); throw new IllegalStateException("Terrain service startup interrupted", ex); }
                }
                if (identity == null) throw new IllegalStateException("Terrain service did not become ready within three minutes. See " + home.resolve("terrain-service.log"));
                if (!profileMatches(endpoint, profile)) throw new IllegalStateException("Terrain service started with the wrong model profile");
            } catch (RuntimeException ex) {
                shutdown();
                throw ex;
            }
        }
        if (expectedIdentity != null && !expectedIdentity.isEmpty() && !expectedIdentity.equals(identity)) {
            if (owned != null) shutdown();
            throw new IllegalStateException("This world needs a different terrain model. Restore its original model and settings; terrain was not substituted.");
        }
    }

    public static void shutdown() {
        synchronized (PROCESS_LOCK) {
            Process service = owned;
            if (service != null) { service.destroy(); owned = null; ownedProfile = null; }
        }
    }

    private static void shutdownAll() {
        synchronized (PROCESS_LOCK) {
            closing = true;
            Process setup = installing;
            if (setup != null) {
                setup.descendants().forEach(ProcessHandle::destroy);
                setup.destroy();
                installing = null;
            }
        }
        shutdown();
    }

    private static URI endpoint() {
        URI uri = URI.create(System.getProperty("remotemountains.diffusionUrl", "http://127.0.0.1:19802"));
        if (!"http".equals(uri.getScheme()) || !"127.0.0.1".equals(uri.getHost()) || uri.getUserInfo() != null)
            throw new IllegalArgumentException("Terrain endpoint must use loopback HTTP");
        return uri;
    }

    private static String health(URI endpoint) {
        try {
            HttpResponse<Void> response = HTTP.send(HttpRequest.newBuilder(endpoint.resolve("/health"))
                .timeout(Duration.ofSeconds(2)).GET().build(), HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() != 200) return null;
            String identity = response.headers().firstValue("X-Terrain-Identity").orElse("");
            String spacing = response.headers().firstValue("X-Blocks-Per-Pixel").orElse("");
            if (!identity.matches("[0-9a-f]{64}") || !spacing.matches("(?:[1-9]|1[0-6])"))
                throw new IllegalStateException("Another service occupies the terrain port but has an invalid terrain protocol");
            return identity;
        } catch (IOException ex) { return null; }
        catch (InterruptedException ex) { Thread.currentThread().interrupt(); throw new IllegalStateException("Terrain health check interrupted", ex); }
    }

    private static boolean profileMatches(URI endpoint, String profile) {
        try {
            HttpResponse<Void> response = HTTP.send(HttpRequest.newBuilder(endpoint.resolve("/health"))
                .timeout(Duration.ofSeconds(2)).GET().build(), HttpResponse.BodyHandlers.discarding());
            String actual = response.headers().firstValue("X-Terrain-Profile").orElse("geographic_v1");
            return response.statusCode() == 200 && actual.equals(profile);
        } catch (IOException ex) { return false; }
        catch (InterruptedException ex) { Thread.currentThread().interrupt(); throw new IllegalStateException("Terrain profile check interrupted", ex); }
    }

    private static Path home() {
        String configured = System.getProperty("remotemountains.diffusionHome");
        if (configured == null || configured.isBlank()) configured = System.getenv("REMOTEMOUNTAINS_DIFFUSION_HOME");
        if (configured == null || configured.isBlank()) configured = config().getProperty("home");
        if (configured == null || configured.isBlank()) configured = net.fabricmc.loader.api.FabricLoader.getInstance().getGameDir().resolve("Terragenesis").toString();
        return Path.of(configured).toAbsolutePath().normalize();
    }

    public static Path homePath() { return home(); }
    

    private static String conditioningMode() {
        String mode = System.getProperty("remotemountains.conditioningMode");
        if (mode == null || mode.isBlank()) mode = config().getProperty("conditioningMode", "geographic_v1");
        if (!mode.equals("geographic_v1") && !mode.equals("legacy_worldclim"))
            throw new IllegalStateException("Unsupported terrain conditioning mode: " + mode);
        return mode;
    }

    private static Properties config() {
        Properties properties = new Properties();
        Path config = net.fabricmc.loader.api.FabricLoader.getInstance().getConfigDir().resolve("remotemountains-diffusion.properties");
        if (!Files.isRegularFile(config)) return properties;
        try (var input = Files.newBufferedReader(config, StandardCharsets.UTF_8)) { properties.load(input); }
        catch (IOException ex) { throw new IllegalStateException("Cannot read terrain configuration " + config, ex); }
        return properties;
    }

}

