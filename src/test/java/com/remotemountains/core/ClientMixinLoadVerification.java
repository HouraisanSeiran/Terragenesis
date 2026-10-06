package com.remotemountains.core;

import net.fabricmc.api.EnvType;
import net.fabricmc.loader.impl.launch.knot.Knot;

public final class ClientMixinLoadVerification {
    private ClientMixinLoadVerification() {}

    public static void main(String[] args) {
        ClassLoader loader = new Knot(EnvType.CLIENT).init(args);
        try {
            Class.forName("net.minecraft.client.gui.screens.worldselection.CreateWorldScreen", false, loader);
            Class.forName("net.minecraft.client.gui.screens.worldselection.WorldCreationUiState", false, loader);
            Class.forName("net.minecraft.client.Minecraft", false, loader);
            Class.forName("com.remotemountains.client.LandformSettingsScreen", false, loader);
            Class.forName("com.remotemountains.client.TerrainInstallClient", false, loader);
            Class.forName("com.remotemountains.client.TerrainInstallScreen", false, loader);
            Class.forName("com.remotemountains.client.TerrainPreflightScreen", false, loader);
        } catch (ClassNotFoundException e) {
            throw new AssertionError("Minecraft client class missing", e);
        }
        System.out.println("PASS: CreateWorldScreen and Minecraft transformed by Fabric Mixin");
    }
}
