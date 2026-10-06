package com.remotemountains.vdm;

import com.remotemountains.core.*;
import java.util.*;
import java.nio.file.*;

/** Finite-map research bridge. Queries outside exported mesh coverage fail explicitly. */
public final class VdmTerrainSource implements BaseTerrainSource {
    public static final String RECIPE="direct-vdm-file-v1";
    private static final int WIDTH=64;
    private final BaseTerrainSource base;
    private final VectorDisplacementMap map;
    private final String identity;
    private final VdmVoxelizer voxelizer=new VdmVoxelizer();
    private final Map<Long,DensityColumn[]> cache=new LinkedHashMap<>(32,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,DensityColumn[]> e){return size()>32;}
    };
    public VdmTerrainSource(BaseTerrainSource base){
        this.base=base;
        String filename=System.getProperty("remotemountains.vdmFile","");
        if(filename.isBlank())throw new IllegalStateException("Direct VDM required: configure -Dremotemountains.vdmFile=<displacement.rmdv>. No height-map substitute is enabled.");
        try{
            Path path=Path.of(filename);map=VdmFile.read(path);
            identity=java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        }catch(Exception e){throw new IllegalStateException("Cannot load direct VDM export",e);}
    }
    public String identity(){return base.identity();}
    public String vdmIdentity(){return identity;}
    public boolean covers(double x,double z){return map.covers(x,z);}
    public synchronized Terrain.Column sample(double x,double z){
        int ix=(int)Math.floor(x),iz=(int)Math.floor(z),tx=Math.floorDiv(ix,WIDTH),tz=Math.floorDiv(iz,WIDTH);
        long key=((long)tx<<32)^(tz&0xffffffffL);
        DensityColumn[] columns=cache.computeIfAbsent(key,k->voxelizer.rasterize(map,tx*WIDTH,tz*WIDTH,WIDTH));
        DensityColumn density=columns[Math.floorMod(iz,WIDTH)*WIDTH+Math.floorMod(ix,WIDTH)];
        Terrain.Column c=base.sample(x,z);
        return new Terrain.Column(density.top(),c.water(),c.base(),density);
    }
}
