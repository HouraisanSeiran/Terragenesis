package com.remotemountains.prepared;

import com.remotemountains.core.Terrain;
import java.nio.file.Path;

/** Optional roundtrip check for the full offline watershed asset. */
public final class PreparedShowcaseVerification {
    private PreparedShowcaseVerification(){}
    public static void main(String[] args)throws Exception{
        if(args.length!=1)throw new IllegalArgumentException("Usage: PreparedShowcaseVerification <artifact-directory>");
        Path directory=Path.of(args[0]);
        long seed=20260927L;
        PreparedArtifact artifact=PreparedArtifact.read(directory,seed,"");
        var source=new com.remotemountains.watershed.WatershedTerrainSource(seed,"",true);
        double maxError=0;int maxX=0,maxZ=0;double maxOriginal=0,maxLoaded=0;
        int compared=0,wet=0;
        for(int x=0;x<=1600;x+=40)for(int z=-440;z<=440;z+=8){
            var original=source.sample(x,z);
            var loaded=artifact.terrain().sample(x,z);
            double error=Math.abs(original.height()-loaded.height());
            if(error>maxError){maxError=error;maxX=x;maxZ=z;maxOriginal=original.height();maxLoaded=loaded.height();}
            if(Double.isFinite(original.water())&&Math.abs(original.water()-loaded.water())<.01)wet++;
            compared++;
        }
        if(maxError>.02)throw new AssertionError("Prepared height differs: "+maxError
            +" at "+maxX+","+maxZ+" source="+maxOriginal+" loaded="+maxLoaded);
        if(wet<100)throw new AssertionError("Expected wet river/ocean samples: "+wet);
        System.setProperty("remotemountains.preparedDir",directory.toString());
        try(Terrain terrain=new Terrain(seed,artifact.identity(),PreparedVdmSource.RECIPE,
                "watershed_prepared_v1","relief_3x_sea62_1024_v1")){
            int wetColumns=0,solidWet=0;
            for(int x=400;x<=1200;x+=48)for(int z=-120;z<=120;z+=12){
                var column=terrain.sample(x*3.0,z*3.0);
                if(Double.isFinite(column.water())){
                    wetColumns++;
                    if(column.height()<=column.water()+.01)solidWet++;
                }
            }
            if(wetColumns<5||solidWet<5)throw new AssertionError("Prepared VDM lost wet river bed");
            System.out.println("Prepared showcase verified: "+compared+" source samples, "
                +wet+" wet, max error "+maxError+", "+solidWet+" wet VDM columns");
        }
    }
}
