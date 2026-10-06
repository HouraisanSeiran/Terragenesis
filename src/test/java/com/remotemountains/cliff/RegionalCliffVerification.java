package com.remotemountains.cliff;

import com.remotemountains.core.*;
import com.remotemountains.vdm.*;
import com.remotemountains.diffusion.*;
import java.nio.file.*;
import java.util.*;

/** Transform, regional seed, lazy cache, negative seams and actual demo sections. */
public final class RegionalCliffVerification {
    private static int checks;
    private static void require(boolean ok,String text){checks++;if(!ok)throw new AssertionError(text);}
    public static void main(String[] args)throws Exception{
        BaseTerrainSource flat=(x,z)->new Terrain.Column(150,Double.NaN,new Landscape.Base(150,Landform.RIFT,new Landscape.Climate(.5,.5),0));
        var layout=new RegionalCliffLayout(20260927,false);
        var modifier=new RegionalCliffModifier(flat,20260927,false);
        var second=new RegionalCliffModifier(flat,20260927,false);
        var site=layout.region(-1,-1);
        Vec3 q=site.toWorld(287,221),back=site.toLocal(q.x(),q.z());
        require(Math.abs(back.x()-287)<1e-9&&Math.abs(back.z()-221)<1e-9,"Placement inverse");
        require(site.equals(new RegionalCliffLayout(20260927,false).region(-1,-1)),"Seed repeat");
        require(!site.equals(new RegionalCliffLayout(20260928,false).region(-1,-1)),"Seed variation");
        Displacement zero=new Displacement(0,0,0);
        require(modifier.apply(0,0,zero).equals(zero)&&modifier.cachedPatches()==0,"No off-site inference");
        var a=modifier.apply(site.x(),site.z(),zero);
        require(Math.abs(a.dy())+Math.abs(a.dx())+Math.abs(a.dz())>1,"Regional cliff missing");
        require(a.equals(second.apply(site.x(),site.z(),zero)),"Query order changed patch");
        var patch=modifier.patch(site);require(patch.statistics().erodedRock()>0,"No erosion");
        require(Math.abs(patch.statistics().waterError())<1e-5,"Water budget");
        // A rotated cliff crossing a negative-coordinate tile boundary must voxelize identically.
        int tx=(int)Math.floor(site.x()/64)*64,tz=(int)Math.floor(site.z()/64)*64;
        var builder=new VdmBuilder(flat,modifier,2,64);var vox=new VdmVoxelizer();
        var left=vox.rasterize(builder.build(tx-64,tz,64),tx-2,(int)site.z()-2,4);
        var right=vox.rasterize(builder.build(tx,tz,64),tx-2,(int)site.z()-2,4);
        for(int i=0;i<left.length;i++)for(int y=90;y<210;y++)require(left[i].solid(y)==right[i].solid(y),"Rotated negative seam");
        BaseTerrainSource sea=(x,z)->new Terrain.Column(48,72,new Landscape.Base(48,Landform.RIFT,new Landscape.Climate(.5,.5),0));
        require(new RegionalCliffModifier(sea,20260927,false).apply(site.x(),site.z(),zero).equals(zero),"Ocean cliff");
        // Exercise eviction and deterministic reconstruction (including a formerly cached site).
        for(int i=0;i<14;i++){var next=layout.region(i,0);modifier.apply(next.x(),next.z(),zero);}
        require(modifier.cachedPatches()<=12,"Unbounded patch cache");
        require(modifier.apply(site.x(),site.z(),zero).equals(a),"Eviction changed generation");
        Path out=Path.of("preview/regional-cliffs");Files.createDirectories(out);
        var base=new DemoLandformSource(20260927,"",true);
        var demo=new RegionalCliffModifier(base,20260927,true);
        var old=new GeneratedVdmSource(base,20260927,CliffSettings.RECIPE);
        var current=new GeneratedVdmSource(base,20260927,RegionalCliffLayout.DEMO_RECIPE);
        StringBuilder csv=new StringBuilder("site,stage,row,column,x,y,z\n");int index=0;
        for(var exhibit:new RegionalCliffLayout(20260927,true).exhibits()){
            var eroded=demo.patch(exhibit);require(eroded.statistics().erodedRock()>0,"Dry exhibit");
            BaseTerrainSource local=(x,z)->{var p=exhibit.toWorld(x,z);return base.sample(p.x(),p.z());};
            var rock=new CliffPipeline().build(local,exhibit.settings(),CliffPipeline.Stage.ROCK);
            int changes=0;
            for(int k=-30;k<=30;k+=3){
                var p=exhibit.toWorld(256+k*CliffPatch.OUT.x(),256+k*CliffPatch.OUT.z());
                var before=old.sample(p.x(),p.z());var after=current.sample(p.x(),p.z());
                for(int y=40;y<310;y++)if(before.density().solid(y)!=after.density().solid(y))changes++;
            }
            require(index==0?changes==0:changes>20,"Exhibit not voxelized or legacy centre changed");
            for(var result:List.of(rock,eroded)){
                String stage=result==rock?"rock":"eroded";var p=result.patch();
                for(int row=0;row<p.rows;row++)for(int col=0;col<p.columns;col++){
                    Vec3 v=p.position(p.index(col,row));var world=exhibit.toWorld(v.x(),v.z());
                    csv.append(String.format(Locale.ROOT,"%d,%s,%d,%d,%.6f,%.6f,%.6f%n",index,stage,row,col,world.x(),v.y(),world.z()));
                }
            }
            index++;
        }
        Files.writeString(out.resolve("surfaces.csv"),csv);
        Files.createDirectories(Path.of("verification/regional-cliffs"));
        Files.writeString(Path.of("verification/regional-cliffs/results.json"),"{\"passed\":true,\"checks\":"+checks+"}");
        System.out.println("PASS regional cliffs: "+checks);
    }
}
