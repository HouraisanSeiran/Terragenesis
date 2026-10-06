package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import com.remotemountains.vdm.DensityColumn;
import com.remotemountains.vdm.VdmBuilder;
import com.remotemountains.vdm.VdmVoxelizer;
import java.util.LinkedHashMap;
import java.util.Map;

/** Runtime mesh rasterization from checked height and displacement assets. */
public final class PreparedVdmSource implements BaseTerrainSource {
    public static final String RECIPE="watershed-vdm-prepared-v1";
    private final PreparedTerrainSource base;
    private final TerrainScale scale;
    private final VdmBuilder builder;
    private final VdmVoxelizer voxelizer=new VdmVoxelizer();
    private final Map<Long,DensityColumn[]> cache=new LinkedHashMap<>(32,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,DensityColumn[]> e){return size()>64;}
    };
    public PreparedVdmSource(PreparedTerrainSource base,TerrainScale scale){
        this.base=base;this.scale=scale;
        this.builder=new VdmBuilder(base,base.artifact().modifier(),2,64);
    }
    @Override public String identity(){return base.identity();}
    public String recipe(){return RECIPE;}
    @Override public synchronized Terrain.Column sample(double x,double z){
        int ix=(int)Math.floor(x),iz=(int)Math.floor(z);
        int tx=Math.floorDiv(ix,64),tz=Math.floorDiv(iz,64);
        long key=((long)tx<<32)^(tz&0xffffffffL);
        DensityColumn[] columns=cache.computeIfAbsent(key,k->{
            int localX=Math.floorDiv(tx,scale.factor())*64;
            int localZ=Math.floorDiv(tz,scale.factor())*64;
            return voxelizer.rasterize(builder.build(localX,localZ,64).scaled(scale.factor()),
                tx*64,tz*64,64);
        });
        DensityColumn density=columns[Math.floorMod(iz,64)*64+Math.floorMod(ix,64)];
        Terrain.Column c=base.sample(scale.local(ix),scale.local(iz));
        Landscape.Base old=c.base();
        Landscape.Base surface=new Landscape.Base(density.top(),old.type(),old.climate(),old.landmark());
        return new Terrain.Column(density.top(),scale.height(c.water()),surface,density);
    }
}
