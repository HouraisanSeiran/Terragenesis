package com.remotemountains.vdm;

import com.remotemountains.core.*;
import java.util.*;

/** Chunk-independent VDM conversion and rasterization, with a halo wider than lateral motion. */
public final class GeneratedVdmSource implements BaseTerrainSource {
    private final BaseTerrainSource base;
    private final VdmBuilder builder;
    private final VdmVoxelizer voxelizer=new VdmVoxelizer();
    private final String recipe;
    private final TerrainScale scale;
    private final com.remotemountains.cliff.CliffPipeline.Result cliff;
    private final Map<Long,DensityColumn[]> cache=new LinkedHashMap<>(32,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,DensityColumn[]> e){return size()>64;}
    };
    public GeneratedVdmSource(BaseTerrainSource base){this(base,0,CliffSculptor.RECIPE);}
    public GeneratedVdmSource(BaseTerrainSource base,long seed,String recipe){
        this(base,seed,recipe,TerrainScale.LEGACY);
    }
    public GeneratedVdmSource(BaseTerrainSource base,long seed,String recipe,TerrainScale scale){
        this.scale=scale;
        this.base=base;this.recipe=recipe;
        if(CliffSculptor.RECIPE.equals(recipe)){
            cliff=null;builder=new VdmBuilder(base,new CliffSculptor());
        }else if(com.remotemountains.cliff.CliffSettings.RECIPE.equals(recipe)){
            cliff=new com.remotemountains.cliff.CliffPipeline().build(base,
                com.remotemountains.cliff.CliffSettings.demo(seed),com.remotemountains.cliff.CliffPipeline.Stage.ERODED);
            builder=new VdmBuilder(base,new com.remotemountains.cliff.CliffVdmModifier(cliff),2,64);
        }else if(com.remotemountains.cliff.RegionalCliffLayout.GLOBAL_RECIPE.equals(recipe)
                ||com.remotemountains.cliff.RegionalCliffLayout.DEMO_RECIPE.equals(recipe)){
            boolean demo=com.remotemountains.cliff.RegionalCliffLayout.DEMO_RECIPE.equals(recipe);
            var modifier=new com.remotemountains.cliff.RegionalCliffModifier(base,seed,demo);
            cliff=demo?modifier.patch(new com.remotemountains.cliff.RegionalCliffLayout(seed,true).exhibits().getFirst()):null;
            builder=new VdmBuilder(base,modifier,2,64);
        }else if(com.remotemountains.watershedcliff.WatershedCliffModifier.RECIPE.equals(recipe)
                ||com.remotemountains.watershed.WatershedTerrainSource.RECIPE_V2.equals(recipe)){
            var modifier=new com.remotemountains.watershedcliff.WatershedCliffModifier(base,seed);
            cliff=modifier.result();
            builder=new VdmBuilder(base,modifier,2,64);
        }else if("watershed-vdm-canyon-v2".equals(recipe)||"watershed-vdm-canyon-single-v2".equals(recipe)){
            var modifier=new com.remotemountains.canyon.CanyonCliffModifier(base,seed,"watershed-vdm-canyon-v2".equals(recipe));
            cliff=modifier.legacy().result();
            builder=new VdmBuilder(base,modifier,2,64);
        }else throw new IllegalArgumentException("Unsupported VDM recipe: "+recipe);
    }
    public String identity(){return base.identity();}
    public String recipe(){return recipe;}
    public com.remotemountains.cliff.CliffPipeline.Result cliff(){return cliff;}
    public synchronized Terrain.Column sample(double x,double z){
        int ix=(int)Math.floor(x),iz=(int)Math.floor(z),tx=Math.floorDiv(ix,64),tz=Math.floorDiv(iz,64);
        long key=((long)tx<<32)^(tz&0xffffffffL);
        DensityColumn[] columns=cache.computeIfAbsent(key,k->{
            int localX=Math.floorDiv(tx,scale.factor())*64,localZ=Math.floorDiv(tz,scale.factor())*64;
            return voxelizer.rasterize(builder.build(localX,localZ,64).scaled(scale.factor()),tx*64,tz*64,64);
        });
        DensityColumn d=columns[Math.floorMod(iz,64)*64+Math.floorMod(ix,64)];
        var c=base.sample(scale.local(ix),scale.local(iz));
        var info=new Landscape.Base(d.top(),c.base().type(),c.base().climate(),c.base().landmark());
        return new Terrain.Column(d.top(),scale.height(c.water()),info,d);
    }
}
