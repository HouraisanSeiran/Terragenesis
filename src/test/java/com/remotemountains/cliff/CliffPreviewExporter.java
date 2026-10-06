package com.remotemountains.cliff;

import com.remotemountains.diffusion.BakedTerrainSource;
import java.nio.file.*;
import java.io.*;
import java.util.Locale;

/** Exports the same Java surfaces used by Minecraft, not a second visual-only algorithm. */
public final class CliffPreviewExporter {
    public static void main(String[] args)throws Exception{
        Path output=Path.of("preview/cliff-erosion-v2");Files.createDirectories(output);
        var base=new BakedTerrainSource(20260927,"");var pipeline=new CliffPipeline();
        for(var stage:CliffPipeline.Stage.values()){
            var result=pipeline.build(base,CliffSettings.demo(20260927),stage);var p=result.patch();
            Path csv=output.resolve(stage.name().toLowerCase()+".csv");
            try(var writer=Files.newBufferedWriter(csv)){
                writer.write("row,column,u,v,x,y,z,erosion,flow,hardness\n");
                for(int row=0;row<p.rows;row++)for(int col=0;col<p.columns;col++){
                    int i=p.index(col,row);Vec3 pos=p.position(i);
                    writer.write(String.format(Locale.ROOT,"%d,%d,%.3f,%.3f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f%n",
                        row,col,p.u(col),p.v(row),pos.x(),pos.y(),pos.z(),p.erodedDepth(i),p.runoff(i),p.resistance(i)));
                }
            }
            if(result.statistics()!=null)Files.writeString(output.resolve("statistics.json"),result.statistics().json());
        }
        for(int lean:new int[]{-1,1})for(double angle:new double[]{60,90}){
            var p=new CliffGeometry().build(base,new CliffSettings(20260927,angle,lean,0,0));
            try(var writer=Files.newBufferedWriter(output.resolve("angle-"+(int)angle+"-lean-"+lean+".csv"))){
                writer.write("out,height\n");
                for(int row=0;row<p.rows;row++){
                    Vec3 pos=p.position(p.index(p.columns/2,row));
                    double out=new Vec3(pos.x()-256,0,pos.z()-256).dot(CliffPatch.OUT);
                    writer.write(String.format(Locale.ROOT,"%.6f,%.6f%n",out,pos.y()));
                }
            }
        }
        System.out.println("Exported actual Java erosion stages: "+output);
    }
}
