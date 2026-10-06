package com.remotemountains.core;

import com.remotemountains.diffusion.*;
import java.nio.file.*;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;

/** Actual finite-source samples: feature visibility, labels, boundary and saved identity. */
public final class DemoVerification {
    private static int checks;
    private static void require(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception {
        long seed=20260927;
        var raw=new BakedTerrainSource(seed,"");
        var demo=new DemoLandformSource(seed,"",true);
        var reload=TerrainSources.create(seed,demo.identity(),"demo_landforms_perlin_v2");
        var old=new DemoLandformSource(seed,"");
        var oldReload=TerrainSources.create(seed,old.identity(),"demo_landforms_v1");
        var otherSeed=new DemoLandformSource(seed+1,"",true);
        int changed=0,seedChanged=0;
        for(int x=-128;x<=128;x+=8)for(int z=-128;z<=128;z+=8){
            require(old.sample(x,z).equals(oldReload.sample(x,z)),"Legacy demo changed");
            if(Math.abs(demo.sample(x,z).height()-old.sample(x,z).height())>2)changed++;
            if(Math.abs(demo.sample(x,z).height()-otherSeed.sample(x,z).height())>2)seedChanged++;
            require(Math.abs(demo.sample(x-.00001,z).height()-demo.sample(x+.00001,z).height())<.05,"Discontinuous Perlin surface");
        }
        require(changed>200&&seedChanged>200,"Variation missing");
        require(TerrainSources.create(seed,raw.identity()).identity().equals(raw.identity()),"Legacy baked identity changed");
        require(!demo.identity().equals(raw.identity()),"New terrain needs separate identity");
        try{new DemoLandformSource(seed,raw.identity());throw new AssertionError("Accepted incompatible identity");}
        catch(IllegalStateException expected){checks++;}
        for(int area=0;area<4;area++){
            int cx=(area%2)*512,cz=(area/2)*512;double min=1000,max=-1000,delta=0;
            require(demo.sample(cx,cz).base().type()==Landform.values()[area],"Exhibit biome mismatch");
            for(int z=cz-160;z<=cz+160;z+=8)for(int x=cx-160;x<=cx+160;x+=8){
                var c=demo.sample(x,z);min=Math.min(min,c.height());max=Math.max(max,c.height());
                delta=Math.max(delta,Math.abs(c.height()-raw.sample(x,z).height()));
                require(c.equals(reload.sample(x,z)),"Source reload differs");
                require(Double.isFinite(c.height())&&c.height()<319,"Invalid surface height");
            }
            require(max-min>35&&delta>25,"Missing visible landform "+area);
        }
        for(int z=-300;z<=800;z+=17){
            require(demo.sample(-250,z).height()==raw.sample(-250,z).height(),"Ocean collar changed");
            require(demo.sample(780,z).height()==48,"Demo escaped its extent");
        }
        // Height + illumination preview from this very source, not the historical prototype.
        BufferedImage image=new BufferedImage(513,513,BufferedImage.TYPE_INT_RGB);
        for(int z=0;z<513;z++)for(int x=0;x<513;x++){
            double wx=-256+x*2,wz=-256+z*2;var c=demo.sample(wx,wz);
            double shade=Noise.clamp(.8-(demo.sample(wx+2,wz).height()-c.height())*.12
                -(demo.sample(wx,wz+2).height()-c.height())*.08,.25,1.25);
            int color=c.height()<72?0x397DA2:c.base().type().color;
            int red=(int)Math.min(255,((color>>16)&255)*shade),green=(int)Math.min(255,((color>>8)&255)*shade),blue=(int)Math.min(255,(color&255)*shade);
            image.setRGB(x,z,(red<<16)|(green<<8)|blue);
        }
        Path out=Path.of("verification/demo-landforms");Files.createDirectories(out);
        ImageIO.write(image,"png",out.resolve("height-preview.png").toFile());
        Files.writeString(out.resolve("results.json"),"{\"passed\":true,\"checks\":"+checks+",\"seed\":"+seed+"}");
        System.out.println("PASS demo source: "+checks);
        LandformComparison.export();
    }
}
