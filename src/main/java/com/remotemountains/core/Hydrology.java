package com.remotemountains.core;

import java.util.*;
import static com.remotemountains.core.Noise.*;

/** Regional priority-flood tributaries connected to shared, world-coordinate trunk rivers.
 * Uses a bounded symmetric metric nearest-neighbor graph with stable world nodes.
 * This Java prototype graph is distinct from the Python world's Delaunay graph.
 * This is a finite catchment approximation; it is not a global water simulation.
 */
public final class Hydrology {
    public static final String ALGORITHM="prototype-world-jittered-symmetric-knn6-v2";
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
        for(int dz=-4;dz<=4;dz++)for(int dx=-4;dx<=4;dx++){
            int cx=gx+dx,cz=gz+dz;if(cx<0||cz<0||cx>=N||cz>=N)continue;
            int i=cz*N+cx,j=t.parent[i];if(j<0||t.flow[i]<20)continue;
            double ax=t.nodeX[i],bx=t.nodeX[j],az=t.nodeZ[i],bz=t.nodeZ[j];
            double px=x,pz=z,den=(bx-ax)*(bx-ax)+(bz-az)*(bz-az);
            double u=clamp(((px-ax)*(bx-ax)+(pz-az)*(bz-az))/den,0,1);
            double d=Math.hypot(px-lerp(ax,bx,u),pz-lerp(az,bz,u));
            double width=3+Math.min(12,Math.sqrt(t.flow[i])*.32);
            double localX=lx*STEP,localZ=lz*STEP;
            double edge=Math.min(Math.min(localX,SIZE-localX),Math.min(localZ,SIZE-localZ));
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
        final double[] nodeX=new double[N*N],nodeZ=new double[N*N];
        final int[][] neighbors=new int[N*N][];
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
        buildGraph(t,tx,tz);
        PriorityQueue<Integer> q=new PriorityQueue<>(Comparator.<Integer>comparingDouble(i->t.filled[i]).thenComparingInt(i->i));
        for(int z=0;z<N;z++)for(int x=0;x<N;x++){
            int i=z*N+x;double wx=t.nodeX[i],wz=t.nodeZ[i];
            Landscape.Base b=land.base(wx,wz);double blend=trunkBlend(wx,wz);
            t.raw[i]=lerp(b.height(),68,blend);t.filled[i]=t.raw[i];
            t.flow[i]=.2+b.climate().rain()*1.8;t.rain+=t.flow[i];
            // Avoid protected landmarks when an equally low drainage route exists.
            t.filled[i]+=b.landmark()*8;
            if(trunkDistance(wx,wz)<STEP*.72){seen[i]=true;t.raw[i]=68;t.filled[i]=68;q.add(i);}
        }
        int count=0;
        while(!q.isEmpty()){
            int i=q.remove();t.order[count++]=i;
            for(int j:t.neighbors[i]){
                if(seen[j])continue;seen[j]=true;t.parent[j]=i;
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

    private static long mix(long value){
        value=(value^(value>>>30))*0xbf58476d1ce4e5b9L;
        value=(value^(value>>>27))*0x94d049bb133111ebL;
        return value^(value>>>31);
    }

    private static double fraction(long key){return (mix(key)>>>11)*0x1.0p-53;}

    private void buildGraph(Tile tile,int tx,int tz){
        List<SortedSet<Integer>> adjacent=new ArrayList<>(N*N);
        for(int z=0;z<N;z++)for(int x=0;x<N;x++){
            int node=z*N+x;
            long worldX=(long)tx*(N-1)+x,worldZ=(long)tz*(N-1)+z;
            long key=mix(worldX^0x632be59bd9b4e019L)^mix(worldZ^0x9e3779b97f4a7c15L)^land.seed;
            tile.nodeX[node]=(worldX+.7*(fraction(key^0xd1b54a32d192ed03L)-.5))*STEP;
            tile.nodeZ[node]=(worldZ+.7*(fraction(key^0xabc98388fb8fac03L)-.5))*STEP;
            adjacent.add(new TreeSet<>());
        }
        // Six nearest metric nodes are selected from a bounded support window.
        // Symmetrization preserves junction identity and flood connectivity.
        for(int z=0;z<N;z++)for(int x=0;x<N;x++){
            int node=z*N+x;
            int[] nearest=new int[6];Arrays.fill(nearest,-1);
            double[] distances=new double[6];Arrays.fill(distances,Double.POSITIVE_INFINITY);
            for(int nz=Math.max(0,z-3);nz<=Math.min(N-1,z+3);nz++){
                for(int nx=Math.max(0,x-3);nx<=Math.min(N-1,x+3);nx++){
                    int candidate=nz*N+nx;
                    if(candidate==node)continue;
                    double dx=tile.nodeX[candidate]-tile.nodeX[node],dz=tile.nodeZ[candidate]-tile.nodeZ[node];
                    double distance=dx*dx+dz*dz;
                    for(int rank=0;rank<nearest.length;rank++){
                        if(distance<distances[rank]||(distance==distances[rank]&&candidate<nearest[rank])){
                            for(int shift=nearest.length-1;shift>rank;shift--){
                                distances[shift]=distances[shift-1];nearest[shift]=nearest[shift-1];
                            }
                            distances[rank]=distance;nearest[rank]=candidate;
                            break;
                        }
                    }
                }
            }
            for(int candidate:nearest)if(candidate>=0){
                adjacent.get(node).add(candidate);adjacent.get(candidate).add(node);
            }
        }
        for(int node=0;node<N*N;node++)tile.neighbors[node]=adjacent.get(node).stream().mapToInt(Integer::intValue).toArray();
    }
}
