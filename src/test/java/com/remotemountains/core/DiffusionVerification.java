package com.remotemountains.core;

import com.remotemountains.vdm.*;
import com.remotemountains.diffusion.*;
import java.nio.*;

/** Analytic fixtures check protocol and real folded-surface voxelization, without faking model inference. */
public final class DiffusionVerification {
    private static int checks;
    private static void require(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    private static void fails(Runnable r){try{r.run();}catch(IllegalArgumentException e){checks++;return;}throw new AssertionError("Expected rejection");}
    public static void main(String[] args)throws Exception{
        ByteBuffer b=ByteBuffer.allocate(24+65*65*12).order(ByteOrder.LITTLE_ENDIAN);
        b.put(new byte[]{'R','M','D','2'}).putInt(65).putInt(2).putInt(72).putInt(0).putFloat(30);
        for(int z=0;z<65;z++)for(int x=0;x<65;x++)b.putFloat(x+z*10).putFloat(15).putFloat(1000);
        var tile=DiffusionTile.decode(b.array());
        require(tile.sample(.5,2.5).meters()==25.5,"Bilinear sample");
        require(tile.sample(64,64).meters()==704,"Shared border sample");
        fails(()->DiffusionTile.decode(new byte[4]));
        b.putFloat(24,Float.NaN);fails(()->DiffusionTile.decode(b.array()));
        fails(()->tile.sample(Double.NaN,0));
        Displacement[] data=new Displacement[16];
        double[] xs={-4,4,0,8},ys={0,10,20,30};
        for(int z=0;z<4;z++)for(int x=0;x<4;x++)data[z*4+x]=new Displacement(xs[x]-x*4,ys[x]-72,0);
        var map=new VectorDisplacementMap(0,0,4,4,data);
        var density=new VdmVoxelizer().rasterize(map,2,2,1)[0];
        require(density.crossingCount()==3,"XYZ VDM must retain all three folded surface crossings");
        require(!density.solid(23)&&density.solid(20)&&!density.solid(10)&&density.solid(5),"Rock-air-rock overhang");
        BaseTerrainSource plane=new BaseTerrainSource(){
            public String identity(){return "fixture-only";}
            public Terrain.Column sample(double x,double z){return new Terrain.Column(110+x*.25+z*.12,Double.NaN,new Landscape.Base(110+x*.25+z*.12,Landform.KARST,new Landscape.Climate(.5,.5),0));}
        };
        var builder=new VdmBuilder(plane);var voxelizer=new VdmVoxelizer();
        var a=voxelizer.rasterize(builder.build(-64,-64,64),-3,-3,3);
        var c=voxelizer.rasterize(builder.build(0,0,64),-3,-3,3);
        for(int i=0;i<a.length;i++){
            require(Math.abs(a[i].top()-c[i].top())<1e-8,"Adjacent VDM tiles agree in overlap at negative coordinates");
            for(int y=70;y<150;y++)require(a[i].solid(y)==c[i].solid(y),"Density seam");
        }
        var cliffBuilder=new VdmBuilder(plane,new CliffSculptor());
        var left=voxelizer.rasterize(cliffBuilder.build(192,192,64),248,248,8);
        var right=voxelizer.rasterize(cliffBuilder.build(256,256,64),248,248,8);
        for(int i=0;i<left.length;i++){
            require(Math.abs(left[i].top()-right[i].top())<1e-7,"Sculpted VDM shared boundary");
            for(int y=120;y<230;y++)require(left[i].solid(y)==right[i].solid(y),"Sculpted density shared boundary");
        }
        Displacement unchanged=new Displacement(0,80,0);
        require(new CliffSculptor().apply(-100,-100,unchanged).equals(unchanged),"Sculpting stays inside local mask");
        if(args.length>0){
            var exported=VdmFile.read(java.nio.file.Path.of(args[0]));
            require(exported.size()==8,"Python/Java VDM dimensions");
            var v=exported.vector(3,2);require(v.dx()==-45&&v.dy()==19&&v.dz()==83,"Python/Java XYZ ordering and signed units");
            var vertex=exported.vertex(3,2);require(vertex.x()==-47&&vertex.y()==91&&vertex.z()==87,"World-space reference contract");
        }
        System.out.println("PASS: "+checks+" diffusion protocol / VDM assertions (analytic fixtures, not model inference)");
    }
}
