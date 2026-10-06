package com.remotemountains.client;

import com.remotemountains.diffusion.DiffusionServiceManager;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.gui.screens.TitleScreen;

public final class TerrainInstallClient implements ClientModInitializer {
    private boolean shown;

    @Override public void onInitializeClient() {
        DiffusionServiceManager.startFirstRunInstall();
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            if (shown || !(client.gui.screen() instanceof TitleScreen)) return;
            var stage = DiffusionServiceManager.status().stage();
            if (stage == DiffusionServiceManager.Stage.NOT_STARTED
                    || stage == DiffusionServiceManager.Stage.READY) return;
            shown = true;
            client.gui.setScreen(new TerrainInstallScreen(client.gui.screen()));
        });
    }
}
