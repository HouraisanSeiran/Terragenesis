package com.remotemountains.region;

import com.remotemountains.core.*;
import com.remotemountains.vdm.*;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.function.*;

/** Disk-first region reader. A missing region alone initializes the producer. */
public final class RegionTerrainSource implements BaseTerrainSource {
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
    public synchronized RegionArtifact prepareRegion(int rx,int rz){return region(rx,rz);}
    public synchronized Terrain.Column sample(double x,double z){
        int wx=(int)Math.floor(x),wz=(int)Math.floor(z),width=config.worldWidth();
        int rx=Math.floorDiv(wx,width),rz=Math.floorDiv(wz,width);
        RegionArtifact artifact=region(rx,rz);
        long key=((long)Math.floorDiv(wx,16)<<32)^(Math.floorDiv(wz,16)&0xffffffffL);
        DensityColumn[] density=tiles.computeIfAbsent(key,k->{
            int ox=Math.floorDiv(wx,16)*16,oz=Math.floorDiv(wz,16)*16;
            // The saved map contains all triangles whose lateral motion can reach this chunk.
            long regionKey=((long)rx<<32)^(rz&0xffffffffL);
            VectorDisplacementMap map=scaled.computeIfAbsent(regionKey,rk->artifact.mesh().scaled(3));
            return new VdmVoxelizer().rasterize(map,ox,oz,16,(RegionConfig.HALO-RegionConfig.SPACING)*3.0);
        });
        DensityColumn d=density[Math.floorMod(wz,16)*16+Math.floorMod(wx,16)];
        Terrain.Column c=artifact.sampleBase(wx/3.0,wz/3.0);
        var info=new Landscape.Base(d.top(),c.base().type(),c.base().climate(),c.base().landmark());
        return new Terrain.Column(d.top(),Double.isNaN(c.water())?Double.NaN:TerrainScale.TALL.height(c.water()),info,d);
    }
    private RegionArtifact region(int rx,int rz){
        long key=((long)rx<<32)^(rz&0xffffffffL);
        RegionArtifact existing=regions.get(key);if(existing!=null)return existing;
        try{
            RegionArtifact artifact;
            if(Files.exists(RegionArtifact.path(directory,rx,rz))){
                if(sourceId.isBlank())throw new IOException("Region source identity is required for offline reading");
                artifact=RegionArtifact.read(directory,seed,sourceId,recipe,config,rx,rz);
            }else{
                if(Boolean.getBoolean("remotemountains.regionOffline"))
                    throw new IOException("Missing offline region "+rx+","+rz+" in "+directory);
                if(base==null)base=baseFactory.get();
                String actual=base.identity();
                if(!sourceId.isBlank()&&!sourceId.equals(actual))throw new IOException("Region source identity changed");
                if(sourceId.isBlank())sourceId=actual;
                Files.createDirectories(directory);
                Path manifest=directory.resolve("dataset.id");
                if(!Files.exists(manifest)){
                    Path temp=Files.createTempFile(directory,"dataset-",".tmp");
                    try{
                        Files.writeString(temp,seed+"\n"+sourceId+"\n"+recipe+"\n"+config.chunks()+"\n"+RegionArtifact.ALGORITHM+":"+config.processing()+"\n");
                        Files.move(temp,manifest,StandardCopyOption.ATOMIC_MOVE);
                    }finally{Files.deleteIfExists(temp);}
                }
                if(modifier==null)modifier=modifierFactory.apply(base);
                artifact=RegionArtifact.prepare(directory,seed,actual,recipe,config,rx,rz,base,modifier);
            }
            regions.put(key,artifact);return artifact;
        }catch(IOException e){throw new IllegalStateException("Cannot load terrain region "+rx+","+rz,e);}
    }
}
