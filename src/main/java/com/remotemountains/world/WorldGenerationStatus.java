package com.remotemountains.world;

import net.minecraft.server.MinecraftServer;
import org.slf4j.LoggerFactory;

/** Explicitly distinguishes installed mod from selected world generator in the game log. */
public final class WorldGenerationStatus {
    public static void report(MinecraftServer server){
        var log=LoggerFactory.getLogger("RemoteMountains");
        var generator=server.overworld().getChunkSource().getGenerator();
        if(generator instanceof RemoteGenerator remote)
            log.info("Remote Mountains terrain ACTIVE; source={}; recipe={}; {}",remote.terrainSource(),remote.recipe(),
                switch(remote.terrainSource()) {
                    case "live_diffusion_global" -> "world coordinates are sampled from Terrain Diffusion";
                    case "region_diffusion_v1" -> "on-demand regional model terrain with saved XYZ displacement";
                    case "region_demo_v1" -> "on-demand regional demo terrain with saved XYZ displacement";
                    case "watershed_demo_v1" -> "independent mountain-to-ocean basin; sea Y=62; river mouth world X=4800";
                    default -> "finite landform exhibits; tall presets use 3x horizontal scale";
                });
        else log.warn("Remote Mountains is installed but NOT ACTIVE for this overworld. Create a new world and select 'Remote Mountains / Landform World' (remotemountains:landforms). Current generator={}",generator.getClass().getSimpleName());
    }
}
