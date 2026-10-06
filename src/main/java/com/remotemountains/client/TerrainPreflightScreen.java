package com.remotemountains.client;

import com.remotemountains.diffusion.DiffusionServiceManager;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

final class TerrainPreflightScreen extends Screen {
    TerrainPreflightScreen() { super(Component.translatable("remotemountains.install.title")); }

    @Override public void onClose() {}

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
        var status = DiffusionServiceManager.status();
        Component stage = switch (status.stage()) {
            case NOT_STARTED -> Component.translatable("remotemountains.install.preparing");
            case DOWNLOADING -> Component.translatable("remotemountains.install.downloading");
            case INSTALLING -> Component.translatable("remotemountains.install.installing");
            case STARTING -> Component.translatable("remotemountains.install.starting");
            case READY -> Component.translatable("remotemountains.service.starting");
            case FAILED -> Component.translatable("remotemountains.install.failed");
        };
        graphics.centeredText(font, stage, width / 2, height / 2, 0xFFFFFFFF);
    }
}
