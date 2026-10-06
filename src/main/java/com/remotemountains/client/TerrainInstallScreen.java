package com.remotemountains.client;

import com.remotemountains.diffusion.DiffusionServiceManager;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

public final class TerrainInstallScreen extends Screen {
    private final Screen parent;
    private Button retry;

    public TerrainInstallScreen(Screen parent) {
        super(Component.translatable("remotemountains.install.title"));
        this.parent = parent;
    }

    @Override protected void init() {
        retry = addRenderableWidget(Button.builder(Component.translatable("remotemountains.install.retry"),
            button -> DiffusionServiceManager.retryFirstRunInstall())
            .bounds(width / 2 - 102, height / 2 + 48, 100, 20).build());
        retry.visible = DiffusionServiceManager.status().stage() == DiffusionServiceManager.Stage.FAILED;
        addRenderableWidget(Button.builder(Component.translatable("remotemountains.install.later"),
            button -> onClose()).bounds(width / 2 + 2, height / 2 + 48, 100, 20).build());
    }

    @Override public void onClose() { minecraft.gui.setScreen(parent); }

    @Override public void tick() {
        var stage = DiffusionServiceManager.status().stage();
        retry.visible = stage == DiffusionServiceManager.Stage.FAILED;
        if (stage == DiffusionServiceManager.Stage.READY) onClose();
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
        var status = DiffusionServiceManager.status();
        graphics.centeredText(font, title, width / 2, height / 2 - 48, 0xFFFFFFFF);
        Component stage = switch (status.stage()) {
            case NOT_STARTED -> Component.translatable("remotemountains.install.preparing");
            case DOWNLOADING -> Component.translatable("remotemountains.install.downloading");
            case INSTALLING -> Component.translatable("remotemountains.install.installing");
            case STARTING -> Component.translatable("remotemountains.install.starting");
            case READY -> Component.translatable("remotemountains.install.ready");
            case FAILED -> Component.translatable("remotemountains.install.failed");
        };
        graphics.centeredText(font, stage, width / 2, height / 2 - 12, 0xFFFFFFFF);
        String detail = status.failure() == null ? status.message() : status.failure();
        if (detail != null && !detail.isBlank())
            graphics.textWithWordWrap(font, Component.literal(detail), width / 2 - 110,
                height / 2 + 12, 220, 0xFFBBBBBB);
    }
}
