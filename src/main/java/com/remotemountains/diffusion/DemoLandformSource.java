package com.remotemountains.diffusion;

import com.remotemountains.core.*;

/** Versioned finite exhibit. The raw baked diffusion sample remains unchanged. */
public final class DemoLandformSource implements BaseTerrainSource {
    public static final String PREFIX="demo-landforms-v1:";
    public static final String NATURAL_PREFIX="demo-landforms-perlin-v2:";
    private final BakedTerrainSource base;
    private final DemoLandformField field;
    private final String prefix;
    public DemoLandformSource(long seed,String identity) {
        this(seed,identity,false);
    }
    public DemoLandformSource(long seed,String identity,boolean natural) {
        prefix=natural?NATURAL_PREFIX:PREFIX;
        if(!identity.isEmpty()&&!identity.startsWith(prefix))throw new IllegalStateException("Saved world terrain recipe differs: "+prefix);
        base=new BakedTerrainSource(seed,identity.isEmpty()?"":identity.substring(prefix.length()));
        field=new DemoLandformField(seed,natural);
    }
    public String identity(){return prefix+base.identity();}
    public Terrain.Column sample(double x,double z) {
        Terrain.Column c=base.sample(x,z);
        if(x < -256 || x > 768 || z < -256 || z > 768)return c;
        double h=field.apply(x,z,c.height());
        return new Terrain.Column(h,h<72?72:Double.NaN,
            new Landscape.Base(h,field.type(x,z),c.base().climate(),0));
    }
}
