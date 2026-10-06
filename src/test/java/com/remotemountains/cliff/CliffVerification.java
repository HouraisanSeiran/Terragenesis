package com.remotemountains.cliff;

import com.remotemountains.core.*;
import com.remotemountains.diffusion.BakedTerrainSource;
import com.remotemountains.vdm.*;
import java.nio.file.*;

/** Independent geometry, budget, determinism, actual-voxel and boundary checks. */
public final class CliffVerification {
    private static int checks;
    private static void require(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    private static BaseTerrainSource plane(){return new BaseTerrainSource(){
        public String identity(){return "analytic-plane";}
        public Terrain.Column sample(double x,double z){return new Terrain.Column(110,Double.NaN,new Landscape.Base(110,Landform.KARST,new Landscape.Climate(.5,.5),0));}
    };}
    private static void budgets(ErosionStatistics s){
        require(Math.abs(s.waterError())<1e-8*Math.max(1,s.waterIn()),"Water was created or lost");
        require(Math.abs(s.sedimentError())<1e-8*Math.max(1,s.erodedRock()),"Eroded rock ledger does not balance");
        require(s.waterOut()>0&&s.waterStored()>=0,"Runoff must reach an exit");
        require(s.sidewaysWater()>0,"No sideways surface flow");
        require(s.erodedRock()>0&&s.maxRetreat()>.5,"Erosion did not sculpt the rock");
        require(s.maxRetreat()<=CliffSettings.MAX_RETREAT+1e-8,"Maximum retreat exceeded");
    }
    public static void main(String[] args)throws Exception{
        var flat=plane();var pipeline=new CliffPipeline();
        for(int lean:new int[]{-1,1})for(double angle:new double[]{60,90}){
            var p=new CliffGeometry().build(flat,new CliffSettings(42,angle,lean,0,.1));
            int u=p.columns/2,top=p.index(u,28),bottom=p.index(u,52);
            Vec3 difference=p.position(top).subtract(p.position(bottom));
            require(Math.abs(difference.y()-42)<1e-8,"Incorrect vertical cliff height");
            require(Math.abs(difference.dot(CliffPatch.OUT)-lean*42/Math.tan(Math.toRadians(angle)))<1e-8,"Incorrect cliff angle/lean");
            require(Math.abs(p.normal(p.index(u,40)).length()-1)<1e-8,"Invalid cliff normal");
        }
        BaseTerrainSource base=new BakedTerrainSource(20260927,"");
        for(var config:new CliffSettings[]{new CliffSettings(42,60,-1,96,.105),new CliffSettings(42,90,1,96,.105),new CliffSettings(42,60,1,96,.105)}){
            var angleResult=pipeline.build(flat,config,CliffPipeline.Stage.ERODED);
            budgets(angleResult.statistics());
        }
        var settings=CliffSettings.demo(20260927);
        var rock=pipeline.build(base,settings,CliffPipeline.Stage.ROCK);
        var result=pipeline.build(base,settings,CliffPipeline.Stage.ERODED);budgets(result.statistics());
        var repeated=pipeline.build(base,settings,CliffPipeline.Stage.ERODED);
        double maxHorizontal=0;
        for(int i=0;i<result.patch().size;i++){
            var p=result.patch();Vec3 v=p.position(i),n=p.normal(i);
            require(Double.isFinite(v.x())&&Double.isFinite(v.y())&&Double.isFinite(v.z()),"Nonfinite surface vertex");
            require(p.area(i)>.04&&Math.abs(n.length()-1)<1e-8,"Degenerate surface cell");
            require(v.equals(repeated.patch().position(i)),"Nondeterministic erosion");
            Vec3 delta=v.subtract(p.reference[i]);maxHorizontal=Math.max(maxHorizontal,Math.hypot(delta.x(),delta.z()));
            if(p.boundary(i))require(delta.length()<1e-8,"Patch border changed base terrain");
        }
        require(maxHorizontal<62,"VDM halo is too narrow");
        require(result.statistics().detachedWater()>0,"No water left the overhanging wall");
        require(result.statistics().reattachedWater()>0,"Falling water never reached the lower surface");
        var zero=pipeline.build(flat,new CliffSettings(42,76,1,20,0),CliffPipeline.Stage.ERODED);
        require(zero.statistics().erodedRock()==0,"Zero erosion strength still changed rock");
        var modifier=new CliffVdmModifier(result);
        require(modifier.apply(-100,-100,new Displacement(0,38,0)).equals(new Displacement(0,38,0)),"Changed terrain outside patch");
        var afterBuilder=new VdmBuilder(base,modifier,2,64);
        var beforeBuilder=new VdmBuilder(base,new CliffVdmModifier(rock),2,64);
        var voxelizer=new VdmVoxelizer();
        var a=voxelizer.rasterize(afterBuilder.build(192,192,64),240,240,32);
        var b=voxelizer.rasterize(afterBuilder.build(256,256,64),240,240,32);
        var before=voxelizer.rasterize(beforeBuilder.build(192,192,64),240,240,32);
        int changed=0,overhang=0;
        for(int i=0;i<a.length;i++){
            if(a[i].crossingCount()>1)overhang++;
            require(Math.abs(a[i].top()-b[i].top())<1e-7,"Height seam at chunk boundary");
            require(a[i].solid(50)&&!a[i].solid(170),"Invalid rock/air winding");
            for(int y=65;y<150;y++){
                require(a[i].solid(y)==b[i].solid(y),"Density seam at chunk boundary");
                if(a[i].solid(y)!=before[i].solid(y))changed++;
            }
        }
        require(changed>100,"Erosion failed to change actual block occupancy");
        require(overhang>0,"VDM lost the overhang");
        var legacy=new GeneratedVdmSource(base,20260927,CliffSculptor.RECIPE);
        require(legacy.recipe().equals(CliffSculptor.RECIPE)&&legacy.cliff()==null,"Legacy recipe was silently upgraded");
        var output=Path.of("verification/cliff-erosion");Files.createDirectories(output);
        String json="{\"passed\":true,\"checks\":"+checks+",\"changed_voxels\":"+changed+",\"overhang_columns\":"+overhang
            +",\"max_horizontal_displacement\":"+maxHorizontal+",\"statistics\":"+result.statistics().json()+"}";
        Files.writeString(output.resolve("results.json"),json);
        System.out.println("PASS cliff erosion: "+json);
    }
}
