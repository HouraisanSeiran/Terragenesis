package com.remotemountains.core;

import java.awt.*;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.nio.file.*;
import java.util.*;

/** Exports actual generator samples, not an illustrative substitute. */
public final class PreviewExporter {
    public static void main(String[] args)throws Exception{
        Path out=Path.of("preview");Files.createDirectories(out);
        try(Terrain t=Terrain.proceduralPrototype(20260927L)){
            Map<Landform,Regions.Region> selected=new EnumMap<>(Landform.class);
            for(int radius=0;radius<=4;radius++)for(int z=-radius;z<=radius;z++)for(int x=-radius;x<=radius;x++){
                Regions.Region r=t.landscape.regions.region(x,z);selected.putIfAbsent(r.type(),r);
            }
            StringBuilder json=new StringBuilder("[\n");
            BufferedImage sheet=new BufferedImage(1280,1020,BufferedImage.TYPE_INT_RGB);Graphics2D g=sheet.createGraphics();
            g.setColor(new Color(18,25,29));g.fillRect(0,0,1280,1020);
            int panel=0;
            for(Landform type:Landform.values()){
                Regions.Region r=selected.get(type);int n=220;double span=1800,step=span/(n-1);
                double[][] h=new double[n][n];Terrain.Column[][] columns=new Terrain.Column[n][n];
                for(int z=0;z<n;z++)for(int x=0;x<n;x++){
                    columns[z][x]=t.sample(r.x()+(x-(n-1)/2.0)*step,r.z()+(z-(n-1)/2.0)*step);h[z][x]=columns[z][x].height();
                }
                BufferedImage image=new BufferedImage(620,450,BufferedImage.TYPE_INT_RGB);Graphics2D p=image.createGraphics();
                p.setRenderingHint(RenderingHints.KEY_ANTIALIASING,RenderingHints.VALUE_ANTIALIAS_ON);
                p.setColor(new Color(25,35,41));p.fillRect(0,0,620,450);
                double scale=1.32;
                for(int z=0;z<n-1;z++)for(int x=0;x<n-1;x++){
                    int[] px=new int[4],py=new int[4];int[] vx={x,x+1,x+1,x},vz={z,z,z+1,z+1};
                    for(int k=0;k<4;k++){px[k]=(int)(310+(vx[k]-vz[k])*scale);py[k]=(int)(93+(vx[k]+vz[k])*.56-(h[vz[k]][vx[k]]-75)*.90);}
                    Terrain.Column c=columns[z][x];double slope=(h[z][x+1]-h[z][x])*.045+(h[z+1][x]-h[z][x])*.065;
                    double light=Noise.clamp(.85-slope,.35,1.25);
                    Color color=new Color(type.color);
                    if(Double.isFinite(c.water()))color=new Color(59,135,166);
                    else if(c.base().climate().variant()==0)color=new Color(202,215,218);
                    else if(c.base().climate().variant()==1)color=new Color(183,150,101);
                    p.setColor(new Color((int)Noise.clamp(color.getRed()*light,0,255),(int)Noise.clamp(color.getGreen()*light,0,255),(int)Noise.clamp(color.getBlue()*light,0,255)));
                    p.fillPolygon(px,py,4);
                }
                p.dispose();ImageIO.write(image,"png",out.resolve(type.name().toLowerCase(Locale.ROOT)+".png").toFile());
                int ox=10+(panel%2)*640,oy=20+(panel/2)*500;
                g.setColor(new Color(232,237,231));g.setFont(new Font("Microsoft YaHei",Font.BOLD,24));g.drawString(type.title,ox+18,oy+28);
                g.setFont(new Font("Microsoft YaHei",Font.PLAIN,13));g.setColor(new Color(155,177,181));g.drawString("实际生成器 · 1800 × 1800 格 · 地表预览",ox+18,oy+52);
                g.drawImage(image,ox,oy+55,null);
                if(panel++>0)json.append(",\n");json.append("{\"type\":\"").append(type).append("\",\"x\":").append((int)r.x()).append(",\"z\":").append((int)r.z()).append("}");
                System.out.println("Preview "+type+" at "+(int)r.x()+", "+(int)r.z());
            }
            g.dispose();ImageIO.write(sheet,"png",out.resolve("landforms.png").toFile());Files.writeString(out.resolve("locations.json"),json+"\n]\n");
        }
    }
}
