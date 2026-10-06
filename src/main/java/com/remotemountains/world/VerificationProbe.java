package com.remotemountains.world;

import com.remotemountains.core.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.levelgen.Heightmap;
import java.nio.file.*;
import java.util.*;

/** Opt-in integration harness. Never active during ordinary gameplay. */
public final class VerificationProbe {
    public static void run(MinecraftServer server){
        if(!Boolean.getBoolean("remotemountains.verify"))return;
        server.execute(()->{
            try{
                ServerLevel level=server.overworld();
                if(!(level.getChunkSource().getGenerator() instanceof RemoteGenerator))throw new AssertionError("Wrong world preset");
                var generator=(RemoteGenerator)level.getChunkSource().getGenerator();
                if(Boolean.getBoolean("remotemountains.verifyWatershed")){
                    WatershedWorldVerification.run(level,generator);
                    if(Boolean.getBoolean("remotemountains.verifyCanyon"))CanyonWorldVerification.run(level,generator);
                    System.out.println("REMOTE_VERIFY_PASS");
                    return;
                }
                int factor=generator.verificationTerrain().scale.factor();
                List<String> results=new ArrayList<>();
                int[][] locations=Boolean.getBoolean("remotemountains.verifyGlobal")
                    ?new int[][]{{-8192,-8192},{-128,-128},{0,0},{256,256},{8192,8192}}
                    :new int[][]{{0,0},{512,0},{0,512},{512,512},{-1,-1},{127,127},{248,256},{264,256}};
                for(int[] point:locations){
                    int x=point[0]*factor,z=point[1]*factor;String type="diffusion_vdm";
                    LevelChunk chunk=level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
                    long hash=0;int solids=0;BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
                    for(int dz=0;dz<16;dz++)for(int dx=0;dx<16;dx++)for(int y=level.getMinY();y<=level.getMaxY();y++){
                        var state=chunk.getBlockState(pos.set(chunk.getPos().getMinBlockX()+dx,y,chunk.getPos().getMinBlockZ()+dz));
                        if(!state.isAir())solids++;hash=hash*31+state.toString().hashCode();
                    }
                    int y=chunk.getHeight(Heightmap.Types.WORLD_SURFACE,x&15,z&15);
                    var stored=chunk.getNoiseBiome(x>>2,y>>2,z>>2);
                    var queried=level.getUncachedNoiseBiome(x>>2,y>>2,z>>2);
                    if(!stored.equals(queried))throw new AssertionError("Biome query does not match saved chunk");
                    String name=stored.unwrapKey().orElseThrow().identifier().toString();
                    if(!name.startsWith("remotemountains:"))throw new AssertionError("Vanilla biome leaked into region");
                    if(solids<16000)throw new AssertionError("Terrain chunk unexpectedly empty");
                    results.add("{\"type\":\""+type+"\",\"x\":"+x+",\"z\":"+z+",\"height\":"+y+",\"hash\":\""+hash+"\",\"biome\":\""+name+"\"}");
                    System.out.println("REMOTE_VERIFY_CHUNK "+type+" "+x+","+z+" "+name);
                }
                if(Boolean.getBoolean("remotemountains.verifyErosion")&&factor==1)
                    CliffWorldVerification.run(level,(RemoteGenerator)level.getChunkSource().getGenerator());
                if(factor==3)TallWorldVerification.run(level,generator);
                RegionalCliffWorldVerification.run(level,(RemoteGenerator)level.getChunkSource().getGenerator());
                Files.writeString(Path.of("remote-verification.json"),"["+String.join(",",results)+"]");
                System.out.println("REMOTE_VERIFY_PASS");
            }catch(Throwable e){e.printStackTrace();System.out.println("REMOTE_VERIFY_FAIL");}
            finally{server.halt(false);}
        });
    }
}
