package com.remotemountains.cliff;

import com.remotemountains.core.*;
import java.util.*;

/** Seeded region anchors, never chunk-local randomness. Sites are over 1,700 blocks apart. */
public final class RegionalCliffLayout {
    public static final String GLOBAL_RECIPE="diffusion-vdm-regional-cliffs-v3";
    public static final String DEMO_RECIPE="diffusion-vdm-demo-cliffs-v3";
    private final Regions regions;
    private final long seed;
    private final boolean demo;
    public RegionalCliffLayout(long seed,boolean demo){this.seed=seed;this.demo=demo;regions=new Regions(seed);}
    public CliffPlacement region(int x,int z){
        var r=regions.region(x,z);double angle=switch(r.type()){
            case INSELBERG -> 64+8*Noise.unit(r.key()+80);
            case RIFT -> 78+10*Noise.unit(r.key()+80);
            case KARST -> 72+10*Noise.unit(r.key()+80);
            case PILLARS -> 83+7*Noise.unit(r.key()+80);
        };
        int lean=r.type()==Landform.KARST&&Noise.unit(r.key()+81)<.3?-1:1;
        return new CliffPlacement(r.key(),r.x(),r.z(),r.angle(),
            new CliffSettings(Noise.mix(seed^r.key()),angle,lean,192,.105));
    }
    public List<CliffPlacement> exhibits(){return List.of(
        new CliffPlacement(0,256,256,0,CliffSettings.demo(seed)),
        new CliffPlacement(1,512,0,.75,new CliffSettings(seed^718,90,1,192,.105)),
        new CliffPlacement(2,0,512,-.65,new CliffSettings(seed^919,68,-1,192,.105)));
    }
    public List<CliffPlacement> near(double x,double z){
        if(demo)return exhibits();
        int gx=(int)Math.floor(x/Regions.SPACING),gz=(int)Math.floor(z/Regions.SPACING);
        // The compact 179-block radius stays inside its jittered region grid cell.
        return List.of(region(gx,gz));
    }
}
