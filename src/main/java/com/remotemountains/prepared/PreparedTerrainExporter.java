package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.vdm.SurfaceModifier;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.Locale;

/** Explicit offline preparation entry point. Geometry uses local blocks before world scaling. */
public final class PreparedTerrainExporter {
    private PreparedTerrainExporter(){}
    public static PreparedArtifact export(Path directory,BaseTerrainSource source,
            SurfaceModifier modifier,long seed,int minX,int minZ,int width,int depth,
            int heightStep,int patchStep)throws IOException{
        return PreparedArtifact.export(directory,source,modifier,seed,minX,minZ,width,depth,heightStep,patchStep);
    }

    public static void main(String[] args)throws Exception{
        if(args.length!=1)throw new IllegalArgumentException("Usage: PreparedTerrainExporter <output-directory>");
        long seed=20260927L;
        var source=new com.remotemountains.watershed.WatershedTerrainSource(seed,"",true);
        // All runoff simulation happens here, before any Minecraft chunk is requested.
        SurfaceModifier modifier=new com.remotemountains.canyon.CanyonCliffModifier(source,seed,true);
        PreparedArtifact artifact=export(Path.of(args[0]),source,modifier,seed,
            -704,-896,1489,1121,2,2);
        writeCrossSection(Path.of(args[0]).resolve("river-cross-section.svg"),source,artifact.terrain());
        System.out.println("Prepared terrain: "+artifact.identity());
    }

    /** Cross-section proof compares the source with the imported raster at the trunk valley. */
    public static void writeCrossSection(Path file,BaseTerrainSource source,BaseTerrainSource imported)throws IOException{
        int x=900, z0=-320,z1=320;
        StringBuilder before=new StringBuilder(),after=new StringBuilder(),water=new StringBuilder();
        double maxError=0;
        for(int z=z0;z<=z1;z+=2){
            double px=70+(z-z0)*1.1;
            TerrainSample a=sample(source,x,z),b=sample(imported,x,z);
            if(!Double.isFinite(a.height)||!Double.isFinite(b.height))
                throw new IOException("Non-finite cross-section");
            maxError=Math.max(maxError,Math.abs(a.height-b.height));
            point(before,px,410-(a.height-40)*2.1);
            point(after,px,410-(b.height-40)*2.1);
            if(Double.isFinite(b.water))point(water,px,410-(b.water-40)*2.1);
        }
        String svg="<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"850\" height=\"470\" viewBox=\"0 0 850 470\">"
            +"<rect width=\"850\" height=\"470\" fill=\"#101e2d\"/>"
            +"<path d=\"M70 343H774\" stroke=\"#59778b\" stroke-dasharray=\"4 5\"/>"
            +"<polyline points=\""+before+"\" fill=\"none\" stroke=\"#f8bd65\" stroke-width=\"3\"/>"
            +"<polyline points=\""+after+"\" fill=\"none\" stroke=\"#7ee4c3\" stroke-width=\"2\"/>"
            +"<polyline points=\""+water+"\" fill=\"none\" stroke=\"#6fb8ff\" stroke-width=\"2\"/>"
            +"<text x=\"70\" y=\"32\" fill=\"white\" font-family=\"sans-serif\" font-size=\"18\">River cross-section at x=900</text>"
            +"<text x=\"70\" y=\"54\" fill=\"#f8bd65\" font-family=\"sans-serif\">source</text>"
            +"<text x=\"140\" y=\"54\" fill=\"#7ee4c3\" font-family=\"sans-serif\">imported height</text>"
            +"<text x=\"275\" y=\"54\" fill=\"#6fb8ff\" font-family=\"sans-serif\">imported water</text>"
            +"<text x=\"70\" y=\"445\" fill=\"white\" font-family=\"sans-serif\">z -320 to +320; max height error "
            +String.format(Locale.ROOT,"%.4f",maxError)+" blocks</text></svg>";
        Files.writeString(file,svg);
    }
    private record TerrainSample(double height,double water){}
    private static TerrainSample sample(BaseTerrainSource source,int x,int z){
        var c=source.sample(x,z);return new TerrainSample(c.height(),c.water());
    }
    private static void point(StringBuilder text,double x,double y){
        text.append(String.format(Locale.ROOT,"%.2f,%.2f ",x,y));
    }
}
