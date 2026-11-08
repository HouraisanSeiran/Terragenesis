package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainPreparation;
import com.remotemountains.core.TerrainScale;
import com.remotemountains.vdm.DensityColumn;
import com.remotemountains.vdm.SurfaceModifier;
import com.remotemountains.vdm.VectorDisplacementMap;
import com.remotemountains.vdm.VdmVoxelizer;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

/** Disk-first region reader with explicit preparation of missing artifacts. */
public final class RegionTerrainSource implements BaseTerrainSource, TerrainPreparation {
    public static final String RECIPE="regional-xyz-vdm-v1";
    private final Path directory;
    private final long seed;
    private volatile String sourceId;
    private final String recipe;
    private final RegionConfig config;
    private final Supplier<BaseTerrainSource> baseFactory;
    private final Function<BaseTerrainSource,SurfaceModifier> modifierFactory;
    private BaseTerrainSource base;
    private SurfaceModifier modifier;
    private final Object cacheLock = new Object();
    private final Object preparationLock = new Object();
    private final Map<Long, CompletableFuture<RegionArtifact>> preparations = new HashMap<>();
    private final Map<Long,RegionArtifact> regions=new LinkedHashMap<>(8,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,RegionArtifact> entry){return size()>8;}
    };
    private final Map<Long,DensityColumn[]> tiles=new LinkedHashMap<>(8,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,DensityColumn[]> entry){return size()>48;}
    };
    private final Map<Long,VectorDisplacementMap> scaled=new LinkedHashMap<>(8,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,VectorDisplacementMap> entry){return size()>8;}
    };
    public RegionTerrainSource(Path directory,long seed,String sourceId,String recipe,RegionConfig config,
            Supplier<BaseTerrainSource> baseFactory,Function<BaseTerrainSource,SurfaceModifier> modifierFactory){
        this.directory=directory.resolve("seed-"+seed).resolve(recipe+"-"+config.chunks()+"-"+config.processing());
        this.seed=seed;this.sourceId=sourceId;this.recipe=recipe;this.config=config;
        this.baseFactory=baseFactory;this.modifierFactory=modifierFactory;
        Path manifest=this.directory.resolve("dataset.id");
        if(Files.exists(manifest))try{
            String[] lines=Files.readString(manifest).split("\\R");
            if(lines.length!=5||!lines[0].equals(Long.toString(seed))||!lines[2].equals(recipe)
                    ||!lines[3].equals(Integer.toString(config.chunks()))||!lines[4].equals(RegionArtifact.ALGORITHM+":"+config.processing())
                    ||(!sourceId.isBlank()&&!sourceId.equals(lines[1])))
                throw new IllegalStateException("Region dataset identity mismatch");
            this.sourceId=lines[1];
        }catch(IOException e){throw new IllegalStateException("Cannot read region dataset identity",e);}
    }
    public String identity(){return sourceId;}
    public String recipe(){return recipe;}
    public RegionConfig config(){return config;}
    public Path directory(){return directory;}
    @Override public Path prepareRegion(int rx, int rz) {
        region(rx, rz, true);
        return RegionArtifact.path(directory, rx, rz);
    }
    @Override public void prepareBounds(int minWorldX, int minWorldZ,
            int maxWorldXInclusive, int maxWorldZInclusive) {
        if (maxWorldXInclusive < minWorldX || maxWorldZInclusive < minWorldZ) {
            throw new IllegalArgumentException("Invalid preparation bounds");
        }
        int width = config.worldWidth();
        for (int rz = Math.floorDiv(minWorldZ, width); rz <= Math.floorDiv(maxWorldZInclusive, width); rz++) {
            for (int rx = Math.floorDiv(minWorldX, width); rx <= Math.floorDiv(maxWorldXInclusive, width); rx++) {
                prepareRegion(rx, rz);
            }
        }
    }
    public Terrain.Column sample(double x,double z){
        int wx=(int)Math.floor(x),wz=(int)Math.floor(z),width=config.worldWidth();
        int rx=Math.floorDiv(wx,width),rz=Math.floorDiv(wz,width);
        RegionArtifact artifact=region(rx,rz,false);
        long key=((long)Math.floorDiv(wx,16)<<32)^(Math.floorDiv(wz,16)&0xffffffffL);
        DensityColumn[] density;
        synchronized (cacheLock) {
            density = tiles.get(key);
        }
        if (density == null) {
            int ox=Math.floorDiv(wx,16)*16,oz=Math.floorDiv(wz,16)*16;
            // The saved map contains all triangles whose lateral motion can reach this chunk.
            long regionKey=((long)rx<<32)^(rz&0xffffffffL);
            VectorDisplacementMap map;
            synchronized (cacheLock) {
                map = scaled.get(regionKey);
            }
            if (map == null) {
                map = artifact.mesh().scaled(3);
                synchronized (cacheLock) {
                    scaled.put(regionKey, map);
                }
            }
            density=new VdmVoxelizer().rasterize(map,ox,oz,16,(RegionConfig.HALO-RegionConfig.SPACING)*3.0);
            synchronized (cacheLock) {
                tiles.put(key, density);
            }
        }
        DensityColumn d=density[Math.floorMod(wz,16)*16+Math.floorMod(wx,16)];
        Terrain.Column c=artifact.sampleBase(wx/3.0,wz/3.0);
        var info=new Landscape.Base(d.top(),c.base().type(),c.base().climate(),c.base().landmark());
        return new Terrain.Column(d.top(),Double.isNaN(c.water())?Double.NaN:TerrainScale.TALL.height(c.water()),info,d);
    }
    private RegionArtifact region(int rx, int rz, boolean allowPreparation) {
        long key = ((long) rx << 32) ^ (rz & 0xffffffffL);
        CompletableFuture<RegionArtifact> future;
        boolean owner = false;
        synchronized (cacheLock) {
            RegionArtifact existing = regions.get(key);
            if (existing != null) {
                return existing;
            }
            future = preparations.get(key);
            if (future == null) {
                if (!allowPreparation && !Files.exists(RegionArtifact.path(directory, rx, rz))) {
                    throw missingRegion(rx, rz);
                }
                future = new CompletableFuture<>();
                preparations.put(key, future);
                owner = true;
            }
        }
        if (!owner) {
            try {
                return future.join();
            } catch (CompletionException failure) {
                throw new IllegalStateException("Cannot load terrain region " + rx + "," + rz, failure.getCause());
            }
        }
        try {
            RegionArtifact artifact = loadOrPrepare(rx, rz, allowPreparation);
            synchronized (cacheLock) {
                regions.put(key, artifact);
            }
            future.complete(artifact);
            return artifact;
        } catch (Throwable failure) {
            future.completeExceptionally(failure);
            if (failure instanceof Error error) {
                throw error;
            }
            if (failure instanceof IllegalStateException state) {
                throw state;
            }
            throw new IllegalStateException("Cannot load terrain region " + rx + "," + rz, failure);
        } finally {
            synchronized (cacheLock) {
                preparations.remove(key, future);
            }
        }
    }

    private IllegalStateException missingRegion(int rx, int rz) {
        String state = Boolean.getBoolean("remotemountains.regionOffline")
                ? "Missing offline region " : "Missing prepared region ";
        return new IllegalStateException("Cannot load terrain region " + rx + "," + rz,
                new IOException(state + rx + "," + rz + " in " + directory));
    }

    private RegionArtifact loadOrPrepare(int rx, int rz, boolean allowPreparation) throws IOException {
        Path file = RegionArtifact.path(directory, rx, rz);
        if (Files.exists(file)) {
            if (sourceId.isBlank()) {
                throw new IOException("Region source identity is required for offline reading");
            }
            return RegionArtifact.read(directory, seed, sourceId, recipe, config, rx, rz);
        }
        if (!allowPreparation || Boolean.getBoolean("remotemountains.regionOffline")) {
            throw missingRegion(rx, rz);
        }
        synchronized (preparationLock) {
            if (Files.exists(file)) {
                return RegionArtifact.read(directory, seed, sourceId, recipe, config, rx, rz);
            }
            if (base == null) {
                base = baseFactory.get();
            }
            String actual = base.identity();
            if (!sourceId.isBlank() && !sourceId.equals(actual)) {
                throw new IOException("Region source identity changed");
            }
            if (actual.isBlank()) {
                throw new IOException("Region source identity is blank");
            }
            sourceId = actual;
            Files.createDirectories(directory);
            writeManifest();
            if (modifier == null) {
                modifier = modifierFactory.apply(base);
            }
            return RegionArtifact.prepare(directory, seed, actual, recipe, config, rx, rz, base, modifier);
        }
    }

    private void writeManifest() throws IOException {
        Path manifest = directory.resolve("dataset.id");
        if (Files.exists(manifest)) {
            return;
        }
        Path temp = Files.createTempFile(directory, "dataset-", ".tmp");
        try {
            Files.writeString(temp, seed + "\n" + sourceId + "\n" + recipe + "\n" + config.chunks()
                    + "\n" + RegionArtifact.ALGORITHM + ":" + config.processing() + "\n");
            Files.move(temp, manifest, StandardCopyOption.ATOMIC_MOVE);
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
