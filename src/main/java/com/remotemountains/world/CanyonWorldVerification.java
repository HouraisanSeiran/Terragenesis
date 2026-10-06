package com.remotemountains.world;

import com.remotemountains.canyon.CanyonCliffModifier;
import com.remotemountains.cliff.CliffPatch;
import com.remotemountains.watershed.WatershedTerrainSource;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;

/** Tests the new bank patches in real saved Minecraft chunks. */
public final class CanyonWorldVerification {
    public static void run(ServerLevel level,RemoteGenerator generator)throws Exception {
        var terrain=generator.verificationTerrain();
        var base=new WatershedTerrainSource(terrain.landscape.seed,terrain.identity(),true);
        boolean mixed=generator.recipe().equals(CanyonCliffModifier.MIXED_RECIPE);
        var canyon=new CanyonCliffModifier(base,terrain.landscape.seed,mixed);
        if(canyon.placements().size()<2)throw new AssertionError("Too few canyon patches");
        var rows=new ArrayList<String>();int checked=0,changed=0;
        for(var site:canyon.placements()){
            long hash=0;double difference=0;
            for(int offset=-20;offset<=20;offset+=5){
                var point=site.toWorld(256+offset*CliffPatch.OUT.x(),256+offset*CliffPatch.OUT.z());
                int x=(int)Math.floor(point.x()*3),z=(int)Math.floor(point.z()*3);
                var column=terrain.sample(x,z);
                difference=Math.max(difference,Math.abs(column.height()-terrain.scale.height(base.sample(x/3.0,z/3.0).height())));
                level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
                for(int y=(int)Math.floor(column.height())-96;y<column.height()-15;y++){
                    var state=level.getBlockState(new BlockPos(x,y,z));
                    if(terrain.solid(x,y,z,column)!=state.isSolidRender())throw new AssertionError("Canyon rock mismatch at "+x+","+y+","+z);
                    hash=31*hash+state.toString().hashCode();checked++;
                }
            }
            if(difference>6)changed++;
            rows.add("{\"x\":"+site.x()*3+",\"z\":"+site.z()*3+",\"reference_angle\":"+site.settings().angleDegrees()
                +",\"max_height_change\":"+difference+",\"block_hash\":\""+hash+"\"}");
        }
        if(changed!=canyon.placements().size())throw new AssertionError("Missing canyon surface changes");
        var ledger=base.graph().ledger();
        if(Math.abs(ledger.waterResidual())>1e-6||Math.abs(ledger.sedimentResidual())>1e-6)
            throw new AssertionError("Canyon basin conservation error");
        Files.writeString(Path.of("canyon-world.json"),"{\"passed\":true,\"mixed\":"+mixed+",\"checked_blocks\":"+checked
            +",\"bank_exchanges\":"+base.graph().bankExchanges().size()+",\"water_residual\":"+ledger.waterResidual()
            +",\"sediment_residual\":"+ledger.sedimentResidual()+",\"sites\":["+String.join(",",rows)+"]}");
        System.out.println("REMOTE_CANYON_PASS patches="+changed+" blocks="+checked);
    }
}
