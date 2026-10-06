package com.remotemountains.world;

import com.remotemountains.core.*;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import java.nio.file.*;

/** Real tall-dimension allocation, high terrain blocks and the top buildable coordinate. */
public final class TallWorldVerification {
    public static void run(ServerLevel level,RemoteGenerator generator)throws Exception{
        Terrain terrain=generator.verificationTerrain();
        if(level.getMinY()!=-64||level.getMaxY()!=1023||generator.getGenDepth()!=1088||generator.getSeaLevel()!=62)
            throw new AssertionError("Incorrect tall dimension bounds: "+level.getMinY()+".."+level.getMaxY());
        int x=generator.terrainSource().equals("live_diffusion_global")?20094:0;
        int z=generator.terrainSource().equals("live_diffusion_global")?26877:0;
        var column=terrain.sample(x,z);int solidHigh=0;
        level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
        for(int y=321;y<Math.floor(column.height())-12;y++){
            if(!terrain.solid(x,y,z,column))continue;
            if(!level.getBlockState(new BlockPos(x,y,z)).isSolidRender())throw new AssertionError("Missing high terrain at Y="+y);
            solidHigh++;
        }
        if(solidHigh<1&&!generator.terrainSource().equals("live_diffusion_global"))throw new AssertionError("No terrain verified above former ceiling");
        // Explicit marker is confined to this opt-in isolated test world and survives restart.
        BlockPos marker=new BlockPos(96,1023,96);
        level.getChunk(6,6);level.setBlock(marker,Blocks.GOLD_BLOCK.defaultBlockState(),2);
        if(!level.getBlockState(marker).is(Blocks.GOLD_BLOCK))throw new AssertionError("Cannot place at Y=1023");
        if(!level.isOutsideBuildHeight(1024)||level.isOutsideBuildHeight(1023))throw new AssertionError("Wrong build ceiling");
        Files.writeString(Path.of("tall-world.json"),"{\"passed\":true,\"min_y\":-64,\"max_y\":1023,\"sea_level\":62,\"high_solid_blocks\":"+solidHigh+",\"height\":"+column.height()+"}");
        System.out.println("REMOTE_TALL_PASS highBlocks="+solidHigh);
    }
}
