package com.remotemountains.core;

import com.remotemountains.diffusion.DemoLandformSource;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.nio.file.*;
import javax.imageio.ImageIO;

/** Same seed, camera, colours and scale for both actual terrain sources. */
public final class LandformComparison {
    public static void export()throws Exception {
        BufferedImage sheet=new BufferedImage(1046,554,BufferedImage.TYPE_INT_RGB);
        Graphics2D g=sheet.createGraphics();g.setColor(new Color(24,29,34));g.fillRect(0,0,1046,554);
        g.setFont(new Font("Microsoft YaHei",Font.PLAIN,18));
        for(int panel=0;panel<2;panel++){
            var source=new DemoLandformSource(20260927,"",panel==1);
            g.setColor(Color.WHITE);g.drawString(panel==0?"之前 · 0.4.0":"之后 · Perlin 多尺度扰动",10+panel*523,26);
            for(int z=0;z<513;z++)for(int x=0;x<513;x++){
                double wx=-256+x*2,wz=-256+z*2;var c=source.sample(wx,wz);
                double light=Noise.clamp(.8-(source.sample(wx+2,wz).height()-c.height())*.12
                    -(source.sample(wx,wz+2).height()-c.height())*.08,.25,1.25);
                int rgb=c.height()<72?0x397DA2:0x9B9775;
                int r=(int)Math.min(255,((rgb>>16)&255)*light),green=(int)Math.min(255,((rgb>>8)&255)*light),b=(int)Math.min(255,(rgb&255)*light);
                sheet.setRGB(10+panel*523+x,36+z,(r<<16)|(green<<8)|b);
            }
        }
        g.dispose();Path out=Path.of("preview/perlin-landforms");Files.createDirectories(out);
        ImageIO.write(sheet,"png",out.resolve("comparison.png").toFile());
    }
}
