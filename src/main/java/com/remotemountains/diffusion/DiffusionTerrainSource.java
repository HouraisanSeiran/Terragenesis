package com.remotemountains.diffusion;

import com.remotemountains.core.*;

/** Every height comes from learned model output. Region labels do not overwrite that height. */
public final class DiffusionTerrainSource implements BaseTerrainSource {
    private final DiffusionClient client;
    private final Regions regions;
    private final boolean raw;
    public DiffusionTerrainSource(long seed,String expectedIdentity){this(seed,expectedIdentity,false);}
    public DiffusionTerrainSource(long seed,String expectedIdentity,boolean raw){this(seed,expectedIdentity,raw,"geographic_v1");}
    public DiffusionTerrainSource(long seed,String expectedIdentity,boolean raw,String profile){
        client=new DiffusionClient(seed,expectedIdentity,profile);regions=new Regions(seed);this.raw=raw;
    }
    public String identity(){return client.identity();}
    public Terrain.Column sample(double x,double z){
        var result=raw?client.sampleRaw(x,z):client.sample(x,z);
        var climate=new Landscape.Climate(Noise.clamp((result.temperature()+12)/45,0,1),Noise.clamp(result.precipitation()/2200,0,1));
        var base=new Landscape.Base(result.height(),regions.at(x,z).primary().type(),climate,0);
        return new Terrain.Column(result.height(),result.water(),base);
    }
}
