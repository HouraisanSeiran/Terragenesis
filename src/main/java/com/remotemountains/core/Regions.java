package com.remotemountains.core;

import java.util.*;
import static com.remotemountains.core.Noise.*;

/** Jittered sites with compact blending; sites are also protected landmark anchors. */
public final class Regions {
    public static final int SPACING=2560;
    public record Region(int gridX,int gridZ,double x,double z,long key,Landform type,double angle) {}
    public record Blend(Region primary,Region[] regions,double[] weights) {}
    private final long seed;
    private final Noise warp;
    private final Map<Long,Region> cache=Collections.synchronizedMap(new LinkedHashMap<>(128,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,Region> e){return size()>512;}
    });
    public Regions(long seed){this.seed=seed;warp=new Noise(seed^87321);}
    public Region region(int x,int z){
        long id=((long)x<<32)^(z&0xffffffffL);
        return cache.computeIfAbsent(id,k->{
            long h=hash(seed,x,z);
            return new Region(x,z,(x+.5+(unit(h)-.5)*.30)*SPACING,
                (z+.5+(unit(h+1)-.5)*.30)*SPACING,h,
                Landform.values()[(int)(mix(h+2)&3)],unit(h+3)*Math.PI*2);
        });
    }
    public Blend at(double x,double z){
        double wx=x+110*warp.at(x/1300,z/1300),wz=z+110*warp.at(x/1300+51,z/1300-27);
        int gx=(int)Math.floor(wx/SPACING),gz=(int)Math.floor(wz/SPACING);
        Region[] candidates=new Region[25];double[] distance=new double[25];int n=0,best=0;
        for(int dz=-2;dz<=2;dz++)for(int dx=-2;dx<=2;dx++){
            Region r=region(gx+dx,gz+dz);candidates[n]=r;
            distance[n]=Math.hypot(wx-r.x,wz-r.z);
            if(distance[n]<distance[best])best=n;n++;
        }
        double min=distance[best],total=0;double[] w=new double[n];
        for(int i=0;i<n;i++){w[i]=1-smooth(0,440,distance[i]-min);total+=w[i];}
        for(int i=0;i<n;i++)w[i]/=total;
        return new Blend(candidates[best],candidates,w);
    }
}
