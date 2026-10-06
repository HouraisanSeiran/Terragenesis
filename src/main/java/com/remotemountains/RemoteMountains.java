package com.remotemountains;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import com.remotemountains.world.RemoteGenerator;
import com.remotemountains.world.TerrainBiomeSource;

public final class RemoteMountains implements ModInitializer {
    public void onInitialize(){
        Registry.register(BuiltInRegistries.CHUNK_GENERATOR,Identifier.fromNamespaceAndPath("remotemountains","landforms"),RemoteGenerator.CODEC);
        Registry.register(BuiltInRegistries.BIOME_SOURCE,Identifier.fromNamespaceAndPath("remotemountains","landforms"),TerrainBiomeSource.CODEC);
        ServerLifecycleEvents.SERVER_STOPPED.register(server->RemoteGenerator.closeAll());
        ServerLifecycleEvents.SERVER_STOPPED.register(server->com.remotemountains.diffusion.DiffusionServiceManager.shutdown());
        ServerLifecycleEvents.SERVER_STARTED.register(com.remotemountains.world.WorldGenerationStatus::report);
        ServerLifecycleEvents.SERVER_STARTED.register(com.remotemountains.world.VerificationProbe::run);
        com.remotemountains.diffusion.DiffusionServiceManager.startFirstRunInstall();
    }
}
