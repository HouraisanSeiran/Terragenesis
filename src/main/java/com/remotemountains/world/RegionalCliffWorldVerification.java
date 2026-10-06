package com.remotemountains.world;

import com.remotemountains.cliff.*;
import com.remotemountains.diffusion.TerrainSources;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.core.BlockPos;
import java.nio.file.*;
import java.util.*;

/** Checks buried rock/air on rotated patches after Minecraft terrain and decorations. */
public final class RegionalCliffWorldVerification {
    public static void run(ServerLevel level,RemoteGenerator generator)throws Exception{
        var terrain=generator.verificationTerrain();long seed=terrain.landscape.seed;
        boolean global=RegionalCliffLayout.GLOBAL_RECIPE.equals(generator.recipe());
        var layout=new RegionalCliffLayout(seed,!global);
        var sites=global?globalCandidates(layout):layout.exhibits();
        var base=TerrainSources.create(seed,terrain.identity(),generator.terrainSource());
        var modifier=new RegionalCliffModifier(base,seed,!global);
        int checked=0,active=0;List<String> rows=new ArrayList<>();
        for(var site:sites){
            if(global&&active>=1)break;
            var result=modifier.patch(site);if(result==null)continue;
            active++;
            for(int offset=-20;offset<=20;offset+=4){
                var world=site.toWorld(256+offset*CliffPatch.OUT.x(),256+offset*CliffPatch.OUT.z());
                int x=(int)Math.floor(terrain.scale.world(world.x())),z=(int)Math.floor(terrain.scale.world(world.z()));
                level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
                var column=terrain.sample(x,z);
                for(int y=(int)Math.floor(column.height())-12*terrain.scale.factor();y<column.height()-2*terrain.scale.factor();y++){
                    boolean expected=terrain.solid(x,y,z,column);
                    var state=level.getBlockState(new BlockPos(x,y,z));
                    boolean actual=state.isSolidRender();
                    if(actual!=expected)throw new AssertionError("Regional patch differs at "+x+","+y+","+z
                        +" expected="+expected+" state="+state+" columnTop="+column.height()+" water="+column.water());
                    checked++;
                }
            }
            rows.add("{\"x\":"+terrain.scale.world(site.x())+",\"z\":"+terrain.scale.world(site.z())+",\"angle\":"+site.settings().angleDegrees()+",\"lean\":"+site.settings().lean()+"}");
        }
        if(!global&&active!=3)throw new AssertionError("Missing demo patches");
        if(global&&active==0)throw new AssertionError("No active regional cliff verified on real diffusion terrain");
        Files.writeString(Path.of("regional-cliff-world.json"),"{\"checked_blocks\":"+checked+",\"active_patches\":"+active+",\"sites\":["+String.join(",",rows)+"]}");
        System.out.println("REMOTE_REGIONAL_PASS active="+active+" blocks="+checked);
    }

    private static List<CliffPlacement> globalCandidates(RegionalCliffLayout layout){
        List<CliffPlacement> sites=new ArrayList<>();
        // Bounded outward sweep adapts to the actual model seed without hiding a missing patch.
        sites.add(layout.region(4,-5));
        for(int radius=0;radius<=6;radius++)for(int z=-radius;z<=radius;z++)for(int x=-radius;x<=radius;x++)
            if(Math.max(Math.abs(x),Math.abs(z))==radius&&!(x==4&&z==-5))sites.add(layout.region(x,z));
        return sites;
    }
}
