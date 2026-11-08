package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainPreparation;
import com.remotemountains.region.RawRegionTerrainSource;
import com.remotemountains.region.RegionArtifact;
import com.remotemountains.region.RegionConfig;
import com.remotemountains.region.RegionLandformLayout;
import com.remotemountains.region.RegionTerrainSource;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.VdmBuilder;
import com.remotemountains.vdm.VdmVoxelizer;
import com.remotemountains.vdm.SurfaceModifier;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Coordinate, persistence, and concurrency contracts for prepared regions. */
public final class RegionVerification {
    private static final long SEED=78123;
    private static final String SOURCE="synthetic-regions-v1", RECIPE="test-xyz-v1";
    private static final RegionConfig CONFIG=new RegionConfig(3,"none_v1");

    private RegionVerification(){}

    public static void main(String[] args)throws Exception{
        if(args.length>0){
            if(args.length!=3)throw new IllegalArgumentException("Usage: RegionVerification <region-root> <seed> <source-identity>");
            offlineArtifactCheck(Path.of(args[0]),Long.parseLong(args[1]),args[2]);
            return;
        }
        logicalLayoutCheck();
        coordinateAndPersistenceChecks();
        blankIdentityOfflineCheck();
        concurrentPreparationCheck();
        preparationBoundaryChecks(false);
        preparationBoundaryChecks(true);
        System.out.println("Region verification passed");
    }

    private static void offlineArtifactCheck(Path root,long seed,String sourceIdentity){
        RegionTerrainSource loaded=new RegionTerrainSource(root,seed,sourceIdentity,
            RegionTerrainSource.RECIPE,RegionConfig.DEFAULT,
            ()->{throw new AssertionError("offline model invoked");},
            ignored->{throw new AssertionError("offline modifier invoked");});
        String previous=System.getProperty("remotemountains.regionOffline");
        try{
            System.setProperty("remotemountains.regionOffline","true");
            for(int[] point:new int[][]{{0,0},{15,15},{383,383}}){
                Terrain.Column c=loaded.sample(point[0],point[1]);
                check(Double.isFinite(c.height())&&c.density()!=null,"invalid offline model region");
            }
            System.out.println("Offline model region verified: "+loaded.identity());
        }finally{
            if(previous==null)System.clearProperty("remotemountains.regionOffline");
            else System.setProperty("remotemountains.regionOffline",previous);
        }
    }

    private static void blankIdentityOfflineCheck()throws Exception{
        Path dir=tempDirectory("regions-blank-id-");
        RegionTerrainSource created=new RegionTerrainSource(dir,SEED,"",RECIPE,CONFIG,
            ()->base(new AtomicInteger()),ignored->modifier(new AtomicInteger()));
        created.prepareBounds(4,5,4,5);
        created.sample(4,5);
        check(SOURCE.equals(created.identity()),"first region did not bind source identity");
        check(Files.exists(created.directory().resolve("dataset.id")),"missing dataset identity manifest");
        String previous=System.getProperty("remotemountains.regionOffline");
        try{
            System.setProperty("remotemountains.regionOffline","true");
            RegionTerrainSource loaded=new RegionTerrainSource(dir,SEED,"",RECIPE,CONFIG,
                ()->{throw new AssertionError("offline model invoked");},
                ignored->{throw new AssertionError("offline modifier invoked");});
            check(SOURCE.equals(loaded.identity()),"manifest identity not recovered");
            near(loaded.sample(4,5).height(),created.sample(4,5).height(),0,"offline reload");
            expectFailure(()->loaded.sample(48,5),"offline missing region");
            expectFailure(()->new RegionTerrainSource(dir,SEED,"wrong",RECIPE,CONFIG,
                ()->base(new AtomicInteger()),ignored->modifier(new AtomicInteger())),"manifest source mismatch");
        }finally{
            if(previous==null)System.clearProperty("remotemountains.regionOffline");
            else System.setProperty("remotemountains.regionOffline",previous);
        }
    }

    private static void logicalLayoutCheck(){
        RegionLandformLayout layout=new RegionLandformLayout(SEED);
        RegionLandformLayout repeat=new RegionLandformLayout(SEED);
        int[] sizes=new int[Landform.values().length];
        int irregular=0,boundaries=0;
        for(int z=-7000;z<=7000;z+=211)for(int x=-7000;x<=7000;x+=211){
            var a=layout.at(x,z);var b=repeat.at(x,z);
            check(a.equals(b),"logical layout changed with evaluation order");
            check(a.primaryWeight()>=.5&&a.primaryWeight()<=1,"invalid blend weight");
            sizes[a.primary().ordinal()]++;
            if(a.primaryWeight()<.99)boundaries++;
            if(x%48!=0&&z%48!=0&&a.primary()!=layout.at(x+211,z).primary())irregular++;
        }
        int min=Integer.MAX_VALUE,max=0;
        for(int size:sizes){min=Math.min(min,size);max=Math.max(max,size);}
        check(min>0&&max>min*1.3,"logical landforms lack varied area");
        check(irregular>20&&boundaries>20,"logical borders appear grid-bound or absent");
    }

    private static void coordinateAndPersistenceChecks()throws Exception{
        Path dir=tempDirectory("regions-coordinates-");
        AtomicInteger baseCalls=new AtomicInteger(),modifierCalls=new AtomicInteger();
        BaseTerrainSource base=base(baseCalls);
        SurfaceModifier modifier=modifier(modifierCalls);
        RegionTerrainSource source=new RegionTerrainSource(dir,SEED,SOURCE,RECIPE,CONFIG,
            ()->base,ignored->modifier);
        int[][] points={{-49,-1},{-48,-1},{-47,-1},{-1,-49},{-1,-48},{-1,-47},
            {-1,-1},{0,-1},{47,-1},{48,-1},{-1,0},{47,47},{48,48}};
        for(int[] point:points){source.prepareBounds(point[0],point[1],point[0],point[1]);assertSample(source,point[0],point[1]);}
        int initialBase=baseCalls.get(),initialModifier=modifierCalls.get();
        check(initialBase>0&&initialModifier>0,"preparation did not invoke both stages");

        RegionTerrainSource loaded=new RegionTerrainSource(dir,SEED,SOURCE,RECIPE,CONFIG,
            ()->{throw new AssertionError("base model called on reload");},
            ignored->{throw new AssertionError("sculptor called on reload");});
        for(int[] point:points)assertSample(loaded,point[0],point[1]);
        check(baseCalls.get()==initialBase&&modifierCalls.get()==initialModifier,
            "reload prepared a region again");

        Path reverse=tempDirectory("regions-reverse-");
        RegionTerrainSource reversed=new RegionTerrainSource(reverse,SEED,SOURCE,RECIPE,CONFIG,
            ()->base(new AtomicInteger()),ignored->modifier(new AtomicInteger()));
        for(int i=points.length-1;i>=0;i--){reversed.prepareBounds(points[i][0],points[i][1],points[i][0],points[i][1]);assertSample(reversed,points[i][0],points[i][1]);}
        for(int[] point:points){
            Terrain.Column a=source.sample(point[0],point[1]);
            Terrain.Column b=reversed.sample(point[0],point[1]);
            near(a.height(),b.height(),.001,"generation order height");
            check(a.density().crossingCount()==b.density().crossingCount(),"generation order density");
        }
        var whole=new VdmBuilder(base,modifier,RegionConfig.SPACING,RegionConfig.HALO)
            .build(-32,-32,80).scaled(3);
        var voxelizer=new VdmVoxelizer();
        int folded=0;
        for(int[] point:points){
            int x=point[0],z=point[1],ox=Math.floorDiv(x,16)*16,oz=Math.floorDiv(z,16)*16;
            var expected=voxelizer.rasterize(whole,ox,oz,16)[Math.floorMod(z,16)*16+Math.floorMod(x,16)];
            var actual=source.sample(x,z).density();
            near(actual.top(),expected.top(),1e-6,"region seam versus whole VDM at "+x+","+z);
            check(actual.crossingCount()==expected.crossingCount(),"fold crossings differ at "+x+","+z);
            for(int y=40;y<=110;y+=5)
                check(actual.solid(y)==expected.solid(y),"fold density differs at "+x+","+z+","+y);
            if(actual.crossingCount()>1)folded++;
        }
        check(folded>0,"XYZ map produced no folded column");

        Path prepared=source.directory();
        expectFailure(()->RegionArtifact.read(prepared,SEED,"different-source",RECIPE,CONFIG,-1,-1),
            "source identity mismatch");
        expectFailure(()->RegionArtifact.read(prepared,SEED+1,SOURCE,RECIPE,CONFIG,-1,-1),
            "seed mismatch");
        expectFailure(()->RegionArtifact.read(prepared,SEED,SOURCE,"different-recipe",CONFIG,-1,-1),
            "recipe mismatch");
        expectFailure(()->new RegionConfig(3,"changed_v1"),"unsupported processing");
        expectFailure(()->RegionArtifact.read(prepared,SEED,SOURCE,RECIPE,new RegionConfig(6,"none_v1"),-1,-1),
            "size mismatch");
        Path artifact=RegionArtifact.path(prepared,-1,-1);
        if(!Files.exists(artifact))artifact=RegionArtifact.path(prepared,-1,0);
        final Path corrupted=artifact;
        byte[] bytes=Files.readAllBytes(corrupted);bytes[bytes.length-1]^=1;Files.write(corrupted,bytes);
        int badZ=corrupted.getFileName().toString().equals("r.-1.-1.rmr")?-1:0;
        expectFailure(()->RegionArtifact.read(prepared,SEED,SOURCE,RECIPE,CONFIG,-1,badZ),"corrupt file");
    }

    private static void concurrentPreparationCheck()throws Exception{
        Path dir=tempDirectory("regions-concurrent-");
        AtomicInteger constructed=new AtomicInteger(), modified=new AtomicInteger();
        RegionTerrainSource source=new RegionTerrainSource(dir,SEED,SOURCE,RECIPE,CONFIG,
            ()->{constructed.incrementAndGet();return base(new AtomicInteger());},
            ignored->modifier(modified));
        CountDownLatch gate=new CountDownLatch(1);
        try(var workers=Executors.newFixedThreadPool(8)){
            List<Future<Double>> tasks=new ArrayList<>();
            for(int i=0;i<8;i++)tasks.add(workers.submit(()->{gate.await();source.prepareRegion(0,0);return source.sample(7,9).height();}));
            gate.countDown();
            double expected=tasks.getFirst().get();
            for(Future<Double> task:tasks)near(task.get(),expected,0,"concurrent samples");
        }
        check(constructed.get()==1,"same region prepared "+constructed.get()+" times");
        int once=modified.get();
        check(once>0,"VDM stage not invoked");
        source.sample(8,9);
        check(modified.get()==once,"region prepared twice after concurrent requests");
    }

    private static void preparationBoundaryChecks(boolean raw)throws Exception{
        Path dir=tempDirectory(raw?"raw-preparation-":"region-preparation-");
        AtomicInteger factories=new AtomicInteger(),calls=new AtomicInteger();
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
        java.util.concurrent.atomic.AtomicBoolean slow=new java.util.concurrent.atomic.AtomicBoolean();
        java.util.function.Supplier<BaseTerrainSource> factory=()->{
            factories.incrementAndGet();
            return new BaseTerrainSource(){
                public String identity(){return SOURCE;}
                public Terrain.Column sample(double x,double z){
                    if(calls.getAndIncrement()==0)throw new IllegalStateException("injected sampling failure");
                    if(slow.get()){
                        entered.countDown();
                        try{
                            if(!release.await(10,TimeUnit.SECONDS))throw new AssertionError("slow source timed out");
                        }catch(InterruptedException failure){Thread.currentThread().interrupt();throw new AssertionError(failure);}
                    }
                    return base(new AtomicInteger()).sample(x,z);
                }
            };
        };
        BaseTerrainSource source=raw?new RawRegionTerrainSource(dir,SEED,SOURCE,CONFIG,factory)
            :new RegionTerrainSource(dir,SEED,SOURCE,RECIPE,CONFIG,factory,ignored->modifier(new AtomicInteger()));
        TerrainPreparation preparation=(TerrainPreparation)source;
        expectFailure(()->source.sample(-1,-1),"query must not generate");
        if(raw)expectFailure(()->((RawRegionTerrainSource)source).sampleGrid(-1,-1,2,1),"grid must not generate");
        check(factories.get()==0,"missing query constructed model");
        String previousOffline=System.getProperty("remotemountains.regionOffline");
        try{
            System.setProperty("remotemountains.regionOffline","true");
            expectFailure(()->preparation.prepareRegion(-1,-1),"offline preparation miss");
            check(factories.get()==0,"offline preparation constructed model");
        }finally{
            if(previousOffline==null)System.clearProperty("remotemountains.regionOffline");
            else System.setProperty("remotemountains.regionOffline",previousOffline);
        }
        expectFailure(()->preparation.prepareBounds(0,0,-1,0),"reversed bounds");
        expectFailure(()->preparation.prepareRegion(-1,-1),"injected preparation failure");
        try(var workers=Executors.newFixedThreadPool(4)){
            List<Future<Path>> tasks=new ArrayList<>();
            for(int i=0;i<4;i++)tasks.add(workers.submit(()->preparation.prepareRegion(-1,-1)));
            Path expected=tasks.getFirst().get();
            for(Future<Path> task:tasks)check(expected.equals(task.get()),"same key paths differ");
        }
        int preparedCalls=calls.get();
        if(raw)check(preparedCalls==1+CONFIG.worldWidth()*CONFIG.worldWidth(),"raw same key generated twice");
        else check(preparedCalls==1+(CONFIG.localWidth()+1)*(CONFIG.localWidth()+1)
            +(CONFIG.gridSize()+2)*(CONFIG.gridSize()+2),"region same key generated twice");
        preparation.prepareBounds(-48,-48,-1,-1);
        source.sample(-1,-1);
        check(factories.get()==1&&calls.get()==preparedCalls,"same key was prepared again");
        expectFailure(()->source.sample(0,-1),"negative bounds prepared adjacent region");
        if(raw){
            Terrain.Column[] grid=((RawRegionTerrainSource)source).sampleGrid(-47,-47,3,2);
            for(int z=0;z<3;z++)for(int x=0;x<3;x++){
                near(grid[z*3+x].height(),source.sample(-47+x*2,-47+z*2).height(),0,"negative raw grid");
            }
        }
        slow.set(true);
        try(var workers=Executors.newFixedThreadPool(2)){
            Future<Path> pending=workers.submit(()->preparation.prepareRegion(2,2));
            try{
                check(entered.await(5,TimeUnit.SECONDS),"slow preparation not started");
                Future<Terrain.Column> read=workers.submit(()->source.sample(-1,-1));
                check(Double.isFinite(read.get(2,TimeUnit.SECONDS).height()),"cached read during preparation");
            }finally{release.countDown();}
            pending.get(10,TimeUnit.SECONDS);
        }
    }

    private static BaseTerrainSource base(AtomicInteger calls){
        return new BaseTerrainSource(){
            public String identity(){return SOURCE;}
            public Terrain.Column sample(double x,double z){
                calls.incrementAndGet();
                double h=80+.125*x+.0625*z;
                return new Terrain.Column(h,Double.NaN,new Landscape.Base(h,Landform.KARST,
                    new Landscape.Climate(.4,.6),.2));
            }
        };
    }

    private static SurfaceModifier modifier(AtomicInteger calls){
        return (x,z,initial)->{
            calls.incrementAndGet();
            double lateral=12*Math.sin(x*.42)*Math.cos(z*.09);
            return new Displacement(initial.dx()+lateral,initial.dy(),initial.dz()+2*Math.cos(x*.09));
        };
    }

    private static void assertSample(RegionTerrainSource source,int x,int z){
        Terrain.Column c=source.sample(x,z);
        check(c.density()!=null,"missing persisted XYZ density at "+x+","+z);
        check(Double.isFinite(c.height()),"nonfinite height at "+x+","+z);
        double localHeight=80+.125*x/3+.0625*z/3;
        near(c.height(),62+(localHeight-72)*3,12,"misaligned region at "+x+","+z);
    }

    private static void near(double actual,double expected,double tolerance,String label){
        if(!Double.isFinite(actual)||Math.abs(actual-expected)>tolerance)
            throw new AssertionError(label+": "+actual+" versus "+expected);
    }
    private static void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    private static void expectFailure(Checked operation,String label)throws Exception{
        try{operation.run();}catch(IOException|IllegalStateException|IllegalArgumentException expected){return;}
        throw new AssertionError("Expected rejection: "+label);
    }
    private interface Checked{void run()throws Exception;}
    private static Path tempDirectory(String prefix)throws IOException{
        Path root=Path.of("verification","regions","unit");Files.createDirectories(root);
        return Files.createTempDirectory(root,prefix);
    }
}
