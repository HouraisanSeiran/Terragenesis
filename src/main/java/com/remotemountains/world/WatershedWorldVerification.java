package com.remotemountains.world;

import com.remotemountains.core.Terrain;
import com.remotemountains.watershed.WatershedTerrainSource;
import com.remotemountains.watershedcliff.WatershedCliffModifier;
import com.remotemountains.cliff.CliffPatch;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.Heightmap;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;

/** Opt-in real-server checks for the independent mountain-to-ocean preset. */
public final class WatershedWorldVerification {
    private record Site(String name,double x,double z,boolean wet) {}

    public static void run(ServerLevel level,RemoteGenerator generator)throws Exception{
        Terrain terrain=generator.verificationTerrain();
        if(!generator.terrainSource().equals(WatershedTerrainSource.SOURCE_V2)
                ||level.getMinY()!=-64||level.getMaxY()!=1023||generator.getSeaLevel()!=62)
            throw new AssertionError("Wrong watershed generator or dimension");
        var source=new WatershedTerrainSource(terrain.landscape.seed,terrain.identity(),true);
        var cliff=new WatershedCliffModifier(source,terrain.landscape.seed);
        var graph=source.graph();
        var sites=new ArrayList<Site>();
        var peak=source.peak();
        sites.add(new Site("peak",peak.x(),peak.z(),false));
        for(int i=0;i<3;i++){
            var node=graph.source(i);
            sites.add(new Site("source_"+i,node.x(),node.z(),true));
        }
        // The first downstream merge on the central source route.
        var nodes=graph.nodes();
        var node=graph.source(1);
        while(node.downstream()>=0){
            int id=node.id();
            long incoming=nodes.stream().filter(n->n.downstream()==id).count();
            if(incoming>1)break;
            node=nodes.get(node.downstream());
        }
        sites.add(new Site("confluence",node.x(),node.z(),true));
        var bank=graph.nearestChannel(900,0);
        sites.add(new Site("bank_channel",bank.x(),bank.z(),true));
        sites.add(new Site("mouth",graph.outlet().x(),graph.outlet().z(),true));
        sites.add(new Site("ocean",1800,0,true));
        var results=new ArrayList<String>();
        int wetSites=0,highSolids=0;
        double peakHeight=0;
        for(var site:sites){
            int x=(int)Math.round(site.x()*3),z=(int)Math.round(site.z()*3);
            var column=terrain.sample(x,z);
            var chunk=level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
            long hash=0;
            var pos=new BlockPos.MutableBlockPos();
            for(int dz=0;dz<16;dz++)for(int dx=0;dx<16;dx++)for(int y=-64;y<=1023;y++)
                hash=hash*31+chunk.getBlockState(pos.set(chunk.getPos().getMinBlockX()+dx,y,chunk.getPos().getMinBlockZ()+dz)).toString().hashCode();
            if(site.wet()){
                int waterBlocks=0;
                for(int y=Math.max(-60,(int)Math.floor(column.height())+1);y<=Math.floor(column.water());y++){
                    var state=level.getBlockState(pos.set(x,y,z));
                    if(state.is(Blocks.WATER)||state.is(Blocks.ICE))waterBlocks++;
                }
                if(waterBlocks<1)throw new AssertionError("Dry river/ocean site: "+site.name()+" at "+x+","+z+" bed="+column.height()+" water="+column.water());
                wetSites++;
            }else{
                peakHeight=column.height();
                if(peakHeight<700||peakHeight>800)throw new AssertionError("Peak outside target: "+peakHeight);
                for(int y=650;y<Math.floor(peakHeight)-12;y++)
                    if(terrain.solid(x,y,z,column)){
                        if(!level.getBlockState(pos.set(x,y,z)).isSolidRender())throw new AssertionError("Missing high mountain blocks");
                        highSolids++;
                    }
                if(highSolids==0)throw new AssertionError("No high mountain blocks");
            }
            int y=chunk.getHeight(Heightmap.Types.WORLD_SURFACE,x&15,z&15);
            var stored=chunk.getNoiseBiome(x>>2,y>>2,z>>2);
            if(!stored.equals(level.getUncachedNoiseBiome(x>>2,y>>2,z>>2)))throw new AssertionError("Biome mismatch");
            results.add("{\"site\":\""+site.name()+"\",\"x\":"+x+",\"z\":"+z+",\"height\":"+column.height()+",\"hash\":\""+hash+"\"}");
            System.out.println("REMOTE_WATERSHED_SITE "+site.name()+" "+x+","+z+" height="+column.height());
        }
        int bankEdges=0;
        for(int[] center:new int[][] {{382,36},{900,0},{1800,0}}){
            for(int z=center[1]-90;z<=center[1]+90;z+=2)
                for(int x=center[0]-90;x<=center[0]+90;x+=2){
                    var wet=terrain.sample(x,z);
                    if(!Double.isFinite(wet.water())
                            ||Math.floor(wet.water())<=Math.floor(wet.height()))continue;
                    for(int[] direction:new int[][] {{1,0},{-1,0},{0,1},{0,-1}}){
                        int nx=x+direction[0],nz=z+direction[1];
                        var dry=terrain.sample(nx,nz);
                        if(Double.isFinite(dry.water())
                                &&Math.floor(dry.water())>Math.floor(dry.height()))continue;
                        int waterY=(int)Math.floor(wet.water());
                        if((int)Math.floor(dry.height())+1<waterY)
                            throw new AssertionError("Perched river at "+x+","+z+" water="+waterY
                                +" neighboring dry ground="+dry.height());
                        level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
                        var state=level.getBlockState(new BlockPos(x,waterY,z));
                        if(!state.is(Blocks.WATER)&&!state.is(Blocks.ICE))
                            throw new AssertionError("Missing final water at "+x+","+waterY+","+z
                                +" state="+state+" height="+wet.height()+" water="+wet.water());
                        bankEdges++;
                    }
                }
        }
        if(bankEdges<8)throw new AssertionError("World bank scan missed river edges");
        int cliffBlocks=0;double largestCliffChange=0;
        var placement=cliff.placement();
        for(int offset=-20;offset<=20;offset+=4){
            var point=placement.toWorld(256+offset*CliffPatch.OUT.x(),256+offset*CliffPatch.OUT.z());
            int x=(int)Math.floor(point.x()*3),z=(int)Math.floor(point.z()*3);
            var column=terrain.sample(x,z);
            largestCliffChange=Math.max(largestCliffChange,Math.abs(column.height()-terrain.scale.height(source.sample(x/3.0,z/3.0).height())));
            level.getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16));
            for(int y=(int)Math.floor(column.height())-96;y<column.height()-15;y++){
                if(terrain.solid(x,y,z,column)!=level.getBlockState(new BlockPos(x,y,z)).isSolidRender())
                    throw new AssertionError("VDM bank block mismatch at "+x+","+y+","+z);
                cliffBlocks++;
            }
        }
        if(largestCliffChange<6)throw new AssertionError("VDM bank has no visible relief");
        var ledger=graph.ledger();var local=cliff.audit();
        if(Math.abs(ledger.waterResidual())>1e-6||Math.abs(ledger.sedimentResidual())>1e-6
                ||Math.abs(local.waterResidual())>1e-6||Math.abs(local.sedimentResidual())>1e-6
                ||graph.bankExchanges().size()!=1||local.waterIn()<=0||local.sedimentOut()<=0)
            throw new AssertionError("Watershed exchange conservation failed");
        Files.writeString(Path.of("remote-verification.json"),"["+String.join(",",results)+"]");
        Files.writeString(Path.of("watershed-world.json"),"{\"passed\":true,\"sea_level\":62,\"peak_height\":"+peakHeight
            +",\"wet_sites\":"+wetSites+",\"bank_edges\":"+bankEdges+",\"high_solid_blocks\":"+highSolids+",\"bank_exchanges\":"+graph.bankExchanges().size()
            +",\"water_residual\":"+ledger.waterResidual()+",\"sediment_residual\":"+ledger.sedimentResidual()
            +",\"cliff_checked_blocks\":"+cliffBlocks+",\"largest_cliff_change\":"+largestCliffChange
            +",\"bank_water_in\":"+local.waterIn()+",\"bank_sediment_out\":"+local.sedimentOut()+"}");
    }
}
