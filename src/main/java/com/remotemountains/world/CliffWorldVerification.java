package com.remotemountains.world;

import com.google.gson.*;
import com.remotemountains.cliff.*;
import com.remotemountains.diffusion.TerrainSources;
import com.remotemountains.vdm.*;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import java.nio.file.*;

/** Opt-in verification against blocks actually generated and saved by Minecraft. */
public final class CliffWorldVerification {
    public static void run(ServerLevel level,RemoteGenerator generator)throws Exception{
        if(!CliffSettings.RECIPE.equals(generator.recipe())&&!RegionalCliffLayout.DEMO_RECIPE.equals(generator.recipe()))throw new AssertionError("Erosion preset not selected");
        var terrain=generator.verificationTerrain();var result=terrain.cliff();
        if(result==null||result.statistics().erodedRock()<=0)throw new AssertionError("Erosion was bypassed");
        var base=TerrainSources.create(terrain.landscape.seed,terrain.identity());
        var rock=new CliffPipeline().build(base,CliffSettings.demo(terrain.landscape.seed),CliffPipeline.Stage.ROCK);
        var builder=new VdmBuilder(base,new CliffVdmModifier(rock),2,64);
        var before=new VdmVoxelizer().rasterize(builder.build(224,224,64),224,224,64);
        var palette=new SurfacePalette();int checked=0,changed=0;JsonArray rows=new JsonArray();
        for(int y=145;y>=65;y--){
            JsonArray row=new JsonArray();
            for(int x=224;x<288;x++){
                int z=256;level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
                var column=terrain.sample(x,z);var actual=level.getBlockState(new BlockPos(x,y,z));
                var expected=palette.sample(terrain,x,y,z,column);
                // Vanilla biome features add grass and replace rock with ore after terrain generation.
                // Compare solid occupancy, not exact material names; a missing rock still fails.
                if(actual.isSolidRender()!=expected.isSolidRender())throw new AssertionError("Generated solidity differs from erosion output at "+x+","+y+","+z+" actual="+actual+" expected="+expected+" surface="+column.height());
                if(column.density().solid(y)!=before[(z-224)*64+x-224].solid(y))changed++;
                row.add(actual.isSolidRender()?1:!actual.getFluidState().isEmpty()?2:actual.isAir()?0:3);checked++;
            }
            rows.add(row);
        }
        if(changed<10)throw new AssertionError("No visible erosion in actual world slice");
        JsonObject report=new JsonObject();report.addProperty("passed",true);report.addProperty("recipe",generator.recipe());
        report.addProperty("checked_blocks",checked);report.addProperty("changed_by_erosion",changed);
        report.addProperty("comparison","solid occupancy after vanilla biome decorations");
        report.addProperty("x_min",224);report.addProperty("x_max_exclusive",288);report.addProperty("z",256);
        report.addProperty("y_max",145);report.addProperty("y_min",65);report.add("rows_top_to_bottom",rows);
        JsonObject stats=JsonParser.parseString(result.statistics().json()).getAsJsonObject();stats.remove("seconds");
        report.add("erosion_statistics",stats);
        Files.writeString(Path.of("cliff-world-verification.json"),new GsonBuilder().setPrettyPrinting().create().toJson(report));
        System.out.println("REMOTE_EROSION_WORLD_PASS checked="+checked+" changed="+changed);
    }
}
