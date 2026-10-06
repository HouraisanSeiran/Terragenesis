package com.remotemountains.core;

import java.util.*;
import static com.remotemountains.core.Noise.*;

/** Regional priority-flood tributaries connected to shared, world-coordinate trunk rivers.
 * Inspired by the D8/fill/accumulate workflow in the user's Trae terrain project.
 * This is a finite catchment approximation; it is not a global water simulation.
 */
public final class Hydrology {
    public static final int SIZE=4096, STEP=64, N=65;
    public record Water(double incision,double surface,double strength) {}
    public record Audit(int cells,int channels,double rain,double outletFlow,boolean downhill) {}
    private final Landscape land;
    private final Noise noise;
    private final Map<Long,Tile> cache=new LinkedHashMap<>(16,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,Tile> e){return size()>24;}
    };
    public Hydrology(Landscape land){this.land=land;noise=new Noise(land.seed^572399);}
    public double trunkDistance(double x,double z){
        double shift=360*noise.at(z/2700,7)+190*Math.sin(z/2100);
        double p=(x-shift)/3072;
        return Math.abs(p-Math.rint(p))*3072;
    }
    public double trunkBlend(double x,double z){return 1-smooth(12,105,trunkDistance(x,z));}
    public Water sample(double x,double z,double raw){
        double trunk=trunkBlend(x,z),incision=Math.max(0,raw-68)*trunk;
        double water=trunkDistance(x,z)<16?72:Double.NaN,strength=trunk;
        int tx=(int)Math.floor(x/SIZE),tz=(int)Math.floor(z/SIZE);Tile t=tile(tx,tz);
        double lx=(x-tx*(double)SIZE)/STEP,lz=(z-tz*(double)SIZE)/STEP;
        int gx=(int)lx,gz=(int)lz;
        // Rivers are line segments, not a bilinearly blurred raster, so narrow channels stay connected.
        for(int dz=-2;dz<=2;dz++)for(int dx=-2;dx<=2;dx++){
            int cx=gx+dx,cz=gz+dz;if(cx<0||cz<0||cx>=N||cz>=N)continue;
            int i=cz*N+cx,j=t.parent[i];if(j<0||t.flow[i]<20)continue;
            double ax=cx*STEP,bx=(j%N)*STEP,az=cz*STEP,bz=(j/N)*STEP;
            double px=lx*STEP,pz=lz*STEP,den=(bx-ax)*(bx-ax)+(bz-az)*(bz-az);
            double u=clamp(((px-ax)*(bx-ax)+(pz-az)*(bz-az))/den,0,1);
            double d=Math.hypot(px-lerp(ax,bx,u),pz-lerp(az,bz,u));
            double width=3+Math.min(12,Math.sqrt(t.flow[i])*.32);
            double edge=Math.min(Math.min(px,SIZE-px),Math.min(pz,SIZE-pz));
            double fade=smooth(0,160,edge);
            double influence=(1-smooth(width,width+32,d))*fade;
            double bed=lerp(t.bed[i],t.bed[j],u);
            double cut=Math.max(0,raw-bed)*influence;
            if(cut>incision){incision=cut;strength=influence;
                water=d<width&&fade>.98?bed+2:Double.NaN;}
        }
        return new Water(incision,water,strength);
    }
    public synchronized Tile tile(int x,int z){
        long k=((long)x<<32)^(z&0xffffffffL);
        return cache.computeIfAbsent(k,key->build(x,z));
    }
    public synchronized int cacheSize(){return cache.size();}
    public static final class Tile {
        final double[] raw=new double[N*N],bed=new double[N*N],filled=new double[N*N],flow=new double[N*N];
        final int[] parent=new int[N*N],order=new int[N*N];
        double rain;
        public Audit audit(){
            int channels=0;double out=0;boolean downhill=true;
            for(int i=0;i<parent.length;i++){
                if(parent[i]<0)out+=flow[i];
                else if(flow[i]>=20){channels++;if(bed[i]+1e-8<bed[parent[i]])downhill=false;}
            }
            return new Audit(N*N,channels,rain,out,downhill);
        }
    }
    private Tile build(int tx,int tz){
        Tile t=new Tile();boolean[] seen=new boolean[N*N];Arrays.fill(t.parent,-1);
        PriorityQueue<Integer> q=new PriorityQueue<>(Comparator.<Integer>comparingDouble(i->t.filled[i]).thenComparingInt(i->i));
        for(int z=0;z<N;z++)for(int x=0;x<N;x++){
            int i=z*N+x;double wx=tx*(double)SIZE+x*STEP,wz=tz*(double)SIZE+z*STEP;
            Landscape.Base b=land.base(wx,wz);double blend=trunkBlend(wx,wz);
            t.raw[i]=lerp(b.height(),68,blend);t.filled[i]=t.raw[i];
            t.flow[i]=.2+b.climate().rain()*1.8;t.rain+=t.flow[i];
            // Avoid protected landmarks when an equally low drainage route exists.
            t.filled[i]+=b.landmark()*8;
            if(trunkDistance(wx,wz)<STEP*.72){seen[i]=true;t.raw[i]=68;t.filled[i]=68;q.add(i);}
        }
        int count=0;
        while(!q.isEmpty()){
            int i=q.remove();t.order[count++]=i;int x=i%N,z=i/N;
            for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){
                int nx=x+dx,nz=z+dz;if((dx==0&&dz==0)||nx<0||nz<0||nx>=N||nz>=N)continue;
                int j=nz*N+nx;if(seen[j])continue;seen[j]=true;t.parent[j]=i;
                t.filled[j]=Math.max(t.filled[j],t.filled[i]+.015);q.add(j);
            }
        }
        if(count!=N*N)throw new IllegalStateException("Catchment has no river outlet");
        for(int k=count-1;k>=0;k--){int i=t.order[k],j=t.parent[i];if(j>=0)t.flow[j]+=t.flow[i];}
        for(int i=0;i<N*N;i++)t.bed[i]=t.parent[i]<0?68:Math.max(69,t.raw[i]-(2+Math.min(14,Math.sqrt(t.flow[i]))));
        // Breach depressions downstream, rather than allowing water to run uphill.
        for(int k=count-1;k>=0;k--){int i=t.order[k],j=t.parent[i];if(j>=0&&t.flow[i]>=20)t.bed[j]=Math.min(t.bed[j],t.bed[i]-.015);}
        return t;
    }
}
