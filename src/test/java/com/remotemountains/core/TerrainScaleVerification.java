package com.remotemountains.core;

import com.remotemountains.cliff.*;
import com.remotemountains.diffusion.*;
import com.remotemountains.vdm.*;
import java.nio.file.*;

/** Exact uniform scaling, not a height-only stretch or block-column upsampling. */
public final class TerrainScaleVerification {
    private static int checks;
    private static void require(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception{
        var scale=TerrainScale.TALL;
        require(scale.upperY()==1024&&scale.depth()==1088&&scale.seaLevel()==62,"Tall contract");
        require(scale.height(48)==38&&scale.height(72)==62&&scale.height(172)==362,"Fixed sea and enlarged relief");
        var base=new DemoLandformSource(20260927,"",true);
        var original=new GeneratedVdmSource(base,20260927,RegionalCliffLayout.DEMO_RECIPE);
        var tall=new GeneratedVdmSource(base,20260927,RegionalCliffLayout.DEMO_RECIPE,scale);
        int[][] sites={{0,0},{512,0},{0,512},{512,512},{256,256},{-64,-64},{-1,-1},{768,768}};
        for(var site:sites)for(int delta=-2;delta<=2;delta++){
            int x=site[0]+delta,z=site[1];var a=original.sample(x,z);var b=tall.sample(x*3,z*3);
            require(Math.abs(b.height()-scale.height(a.height()))<1e-7,"Height scale");
            require(b.base().type()==a.base().type()&&b.base().climate().equals(a.base().climate()),"Region scale");
            require(Double.isNaN(a.water())?Double.isNaN(b.water()):b.water()==scale.height(a.water()),"Water scale");
            for(int y=-20;y<=318;y++)require(a.density().solid(y+.1)==b.density().solid(scale.height(y+.1)),"Folded VDM occupancy scale");
        }
        try(Terrain a=new Terrain(20260927,"",RegionalCliffLayout.DEMO_RECIPE,"demo_landforms_perlin_v2");
            Terrain b=new Terrain(20260927,"",RegionalCliffLayout.DEMO_RECIPE,"demo_landforms_perlin_v2","relief_3x_sea62_1024_v1")){
            var ac=a.sample(0,0);var bc=b.sample(0,0);
            for(int y=-20;y<280;y++)require(a.solid(0,y,0,ac)==b.solid(0,(int)scale.height(y),0,bc),"Caves not scaled");
            require(b.sample(0,0).height()>320,"Terrain never crosses old ceiling");
        }
        BaseTerrainSource plane=(x,z)->new Terrain.Column(100+x*.1+z*.2,Double.NaN,new Landscape.Base(100,Landform.RIFT,new Landscape.Climate(.5,.5),0));
        var builder=new VdmBuilder(plane);var vox=new VdmVoxelizer();
        var left=vox.rasterize(builder.build(-64,-64,64).scaled(3),-3,-3,4);
        var right=vox.rasterize(builder.build(0,0,64).scaled(3),-3,-3,4);
        for(int i=0;i<16;i++)require(Math.abs(left[i].top()-right[i].top())<1e-7,"Scaled mesh seam");
        require(Math.abs(tall.sample(-193,0).height()-tall.sample(-192,0).height())<5,"Negative scaled tile boundary");
        Path out=Path.of("verification/terrain-scale");Files.createDirectories(out);
        Files.writeString(out.resolve("results.json"),"{\"passed\":true,\"checks\":"+checks+",\"factor\":3,\"min_y\":-64,\"max_y\":1023}");
        System.out.println("PASS terrain scaling: "+checks);
    }
}
