package com.remotemountains.core;

import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Behavioral regression suite, executed by both local and Gradle builds. */
public final class CoreVerification {
    private static int assertions;
    private static void require(boolean ok,String message){assertions++;if(!ok)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception{
        long started=System.nanoTime();
        Noise n=new Noise(773);Noise other=new Noise(774);
        require(n.at(-.1,5,91)==new Noise(773).at(-.1,5,91),"noise seed repeat");
        require(n.at(-.1,5,91)!=other.at(-.1,5,91),"noise seed diversity");
        require(Math.abs(n.at(-1e-8,5,91)-n.at(1e-8,5,91))<1e-6,"negative coordinate continuity");
        Landscape land=new Landscape(20260927L);boolean[] types=new boolean[4],climates=new boolean[4];
        double biggestStep=0;
        for(int rz=-3;rz<=3;rz++)for(int rx=-3;rx<=3;rx++){
            Regions.Region r=land.regions.region(rx,rz);types[r.type().ordinal()]=true;
            require(land.regions.at(r.x(),r.z()).primary().equals(r),"landmark anchor belongs to its own region");
            double min=Double.POSITIVE_INFINITY,max=Double.NEGATIVE_INFINITY;
            for(int z=-400;z<=400;z+=40)for(int x=-400;x<=400;x+=40){
                Landscape.Base b=land.base(r.x()+x,r.z()+z);min=Math.min(min,b.height());max=Math.max(max,b.height());
                require(Double.isFinite(b.height())&&b.height()>=68&&b.height()<=300,"world height range");
                climates[b.climate().variant()]=true;
            }
            require(max-min>65,"landmark must retain substantial local relief: "+r.type());
        }
        for(boolean present:types)require(present,"all four landforms present");
        for(boolean present:climates)require(present,"all four climates present");
        for(int x=-7000;x<7000;x+=7){
            double a=land.base(x,1273).height(),b=land.base(x+.001,1273).height();
            biggestStep=Math.max(biggestStep,Math.abs(a-b));
        }
        require(biggestStep<.1,"no height steps at region borders");
        try(Terrain t=Terrain.proceduralPrototype(20260927L);Terrain again=Terrain.proceduralPrototype(20260927L)){
            Hydrology.Audit audit=t.hydrology.tile(0,0).audit();
            require(audit.channels()>20,"catchment contains tributaries");
            require(Math.abs(audit.rain()-audit.outletFlow())<1e-7,"rainfall mass conservation");
            require(audit.downhill(),"channel beds descend downstream");
            int[][] points={{0,0},{-1,-1},{4096,1511},{4095,1511},{-4096,-27},{2301,1711}};
            for(int[] p:points){
                Terrain.Column c=t.sample(p[0],p[1]),d=again.sample(p[0],p[1]);
                require(c.equals(d),"generation independent of query order");
                require(!Double.isFinite(c.water())||c.water()>=c.height(),"water above bed");
                require(t.solid(p[0],-60,p[1],c),"solid underground floor");
            }
            for(int z=-1600;z<=1600;z+=64){
                double a=t.sample(4096-.001,z).height(),b=t.sample(4096+.001,z).height();
                require(Math.abs(a-b)<.1,"catchment border continuity");
            }
            CompletableFuture<Terrain.Column[]> a=t.tile(-1,-1),b=t.tile(-1,-1);
            require(a==b,"concurrent tile requests coalesce");
            Terrain.Column[] tile=a.get(45,TimeUnit.SECONDS);
            require(tile[63*64+63].equals(t.sample(-1,-1)),"negative tile maps world coordinates correctly");
            boolean cave=false;
            Terrain.Column c=t.sample(517,911);
            for(int y=-40;y<70;y++)if(!t.solid(517,y,911,c)&&y<c.height()-6)cave=true;
            // Spatial volume scan, because a single column need not intersect a cave.
            for(int x=500;x<650&&!cave;x+=5)for(int y=-40;y<65;y+=3)
                cave|=land.caves.contains(x,y,911,c.base(),c.height(),Double.NaN);
            require(cave,"3D cave volume exists");
        }
        double seconds=(System.nanoTime()-started)/1e9;
        Files.createDirectories(Path.of("verification"));
        Files.writeString(Path.of("verification/core-results.json"),"{\"assertions\":"+assertions+",\"seconds\":"+seconds+",\"max_region_step_per_0_001_blocks\":"+biggestStep+",\"passed\":true}\n");
        System.out.println("PASS: "+assertions+" assertions in "+String.format(Locale.ROOT,"%.2f",seconds)+"s");
    }
}
