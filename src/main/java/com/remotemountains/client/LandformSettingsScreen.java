package com.remotemountains.client;

import com.remotemountains.world.RemoteGenerator;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.CycleButton;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.worldselection.CreateWorldScreen;
import net.minecraft.network.chat.Component;

public final class LandformSettingsScreen extends Screen {
    private final CreateWorldScreen parent;
    private LandformMode mode;
    private final int initialRegionChunks;
    private String draftRegionChunks;
    private EditBox regionChunks;
    private Button done;

    public LandformSettingsScreen(CreateWorldScreen parent) {
        super(Component.translatable("remotemountains.settings.title"));
        this.parent = parent;
        RemoteGenerator generator = (RemoteGenerator) parent.getUiState().getSettings().selectedDimensions().overworld();
        mode = LandformMode.of(generator);
        initialRegionChunks = generator.regionChunks();
        draftRegionChunks = Integer.toString(initialRegionChunks);
    }

    @Override protected void init() {
        int center = width / 2;
        int top = height / 2 - 52;
        addRenderableWidget(CycleButton.builder(LandformMode::label, mode)
            .withValues(LandformMode.values())
            .create(center - 100, top, 200, 20, Component.translatable("remotemountains.settings.mode"),
                (button, selected) -> { mode = selected; updateValidation(); }));
        regionChunks = new EditBox(font, center - 100, top + 48, 200, 20, Component.translatable("remotemountains.settings.region_chunks"));
        regionChunks.setValue(draftRegionChunks);
        regionChunks.setMaxLength(3);
        regionChunks.setResponder(value -> { draftRegionChunks = value; updateValidation(); });
        addRenderableWidget(regionChunks);
        done = addRenderableWidget(Button.builder(Component.translatable("gui.done"), button -> apply())
            .bounds(center - 102, top + 105, 100, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("gui.cancel"), button -> onClose())
            .bounds(center + 2, top + 105, 100, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("remotemountains.install.open"), button ->
            minecraft.gui.setScreen(new TerrainInstallScreen(this)))
            .bounds(center - 102, top + 130, 204, 20).build());
        updateValidation();
    }

    private int parsedRegionChunks() {
        try {
            int chunks = Integer.parseInt(regionChunks.getValue());
            return chunks >= 3 && chunks <= 96 && chunks % 3 == 0 ? chunks : -1;
        } catch (NumberFormatException exception) {
            return -1;
        }
    }

    private void updateValidation() {
        if (regionChunks != null) regionChunks.setVisible(mode.supportsRegions());
        if (done != null) done.active = !mode.supportsRegions() || parsedRegionChunks() >= 0;
    }

    private void apply() {
        int chunks = mode.supportsRegions() ? parsedRegionChunks() : initialRegionChunks;
        if (chunks < 0) return;
        LandformMode selected = mode;
        parent.getUiState().updateDimensions((registries, dimensions) -> {
            RemoteGenerator previous = (RemoteGenerator) dimensions.overworld();
            if (selected.matches(previous) && chunks == previous.regionChunks()) return dimensions;
            return dimensions.replaceOverworldGenerator(registries, selected.create(previous.palette(), chunks));
        });
        minecraft.gui.setScreen(parent);
    }

    @Override public void onClose() {
        minecraft.gui.setScreen(parent);
    }

    @Override public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
        int center = width / 2;
        int top = height / 2 - 52;
        graphics.centeredText(font, title, center, top - 27, 0xFFFFFFFF);
        if (mode.supportsRegions()) {
            graphics.text(font, Component.translatable("remotemountains.settings.region_chunks"), center - 100, top + 34, 0xFFFFFFFF);
            Component help = Component.translatable(parsedRegionChunks() < 0 ? "remotemountains.settings.invalid" : "remotemountains.settings.region_help");
            graphics.centeredText(font, help, center, top + 75, parsedRegionChunks() < 0 ? 0xFFFF7777 : 0xFFAAAAAA);
        }
    }
}

