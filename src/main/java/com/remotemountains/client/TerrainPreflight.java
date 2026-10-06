package com.remotemountains.client;

import com.remotemountains.diffusion.DiffusionServiceManager;
import com.remotemountains.core.TerrainModeRegistry;
import com.remotemountains.world.RemoteGenerator;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.AlertScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.WorldDimensions;

import java.util.concurrent.CompletableFuture;

public final class TerrainPreflight {
    private static final String INSTALL_ONLY = "install_only";
    private TerrainPreflight() {}

    public static String expectedIdentity(WorldDimensions dimensions) {
        ChunkGenerator generator = dimensions.overworld();
        if (!(generator instanceof RemoteGenerator remote)) return null;
        return switch (TerrainModeRegistry.requireValid(remote.terrainSource(), remote.recipe(), remote.scaleId()).preflight()) {
            case START_SERVICE -> remote.modelIdentity();
            case INSTALL_ONLY -> INSTALL_ONLY;
            case NONE -> null;
        };
    }

    public static void run(Minecraft client, Screen returnTo, String identity, Runnable ready, Runnable cleanup) {
        if (identity == null) { ready.run(); return; }
        client.gui.setScreen(new TerrainPreflightScreen());
        CompletableFuture.runAsync(() -> {
            if (INSTALL_ONLY.equals(identity)) DiffusionServiceManager.startFirstRunInstall().join();
            else DiffusionServiceManager.ensureAvailable(identity);
        }).whenComplete((ignored, failure) ->
            client.execute(() -> {
                if (failure == null) { ready.run(); return; }
                cleanup.run();
                Throwable cause = failure.getCause() == null ? failure : failure.getCause();
                client.gui.setScreen(new AlertScreen(() -> client.gui.setScreen(returnTo),
                    Component.translatable("remotemountains.service.failed"), Component.literal(cause.getMessage() == null ? cause.toString() : cause.getMessage())));
            }));
    }
}
