package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.SurfaceModifier;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

/** Contract checks for source binding, wet beds, bounds, displacement, and corruption. */
public final class PreparedArtifactVerification {
    private PreparedArtifactVerification(){}
    public static void main(String[] args)throws Exception{
        Path dir=Files.createTempDirectory("prepared-terrain-test-");
        AtomicInteger sourceCalls=new AtomicInteger(),modifierCalls=new AtomicInteger();
        BaseTerrainSource source=new BaseTerrainSource(){
            public String identity(){return "synthetic-v1";}
            public Terrain.Column sample(double x,double z){
                sourceCalls.incrementAndGet();
                boolean edge=x==0||z==0||x==8||z==8;
                double height=edge?48:65;
                double water=72;
                Landscape.Base base=new Landscape.Base(height,Landform.KARST,
                    new Landscape.Climate(.4,.6),.2);
                return new Terrain.Column(height,water,base);
            }
        };
        SurfaceModifier modifier=(x,z,initial)->{
            modifierCalls.incrementAndGet();
            double dx=x==4&&z==4?1:0;
            return new Displacement(initial.dx()+dx,initial.dy()-dx,initial.dz());
        };
        PreparedArtifact artifact=PreparedTerrainExporter.export(dir,source,modifier,7,0,0,5,5,2,2);
        PreparedArtifact loaded=PreparedArtifact.read(dir,7,artifact.identity());
        int sourceCount=sourceCalls.get(),modifierCount=modifierCalls.get();
        check(loaded.terrain().sample(4,4).height()==65,"height roundtrip");
        check(loaded.terrain().sample(-1,4).height()==48,"outside ocean");
        check(loaded.terrain().sample(4,4).water()==72,"water roundtrip");
        check(loaded.modifier().apply(4,4,new Displacement(0,-7,0)).dx()==1,"VDM roundtrip");
        check(sourceCalls.get()==sourceCount&&modifierCalls.get()==modifierCount,
            "Runtime import invoked offline source or modifier");
        expectFailure(()->PreparedArtifact.read(dir,8,""),"seed binding");
        expectFailure(()->PreparedArtifact.read(dir,7,"wrong"),"identity binding");
        Path height=dir.resolve("height-water.rmh");
        byte[] bytes=Files.readAllBytes(height);bytes[bytes.length-1]^=1;Files.write(height,bytes);
        expectFailure(()->PreparedArtifact.read(dir,7,""),"checksum");
        BaseTerrainSource invalid=(x,z)->{
            double h=x==4&&z==4?74:48;
            return new Terrain.Column(h,72,new Landscape.Base(h,Landform.KARST,
                new Landscape.Climate(.4,.6),0));
        };
        expectFailure(()->PreparedTerrainExporter.export(dir.resolve("invalid"),invalid,
            (x,z,d)->d,7,0,0,5,5,2,2),"wet bed validation");
        System.out.println("Prepared artifact verification passed");
    }
    private static void check(boolean condition,String message){
        if(!condition)throw new AssertionError(message);
    }
    private static void expectFailure(Checked action,String message)throws Exception{
        try{action.run();}catch(IOException expected){return;}
        throw new AssertionError("Expected "+message+" rejection");
    }
    private interface Checked{void run()throws Exception;}
}
