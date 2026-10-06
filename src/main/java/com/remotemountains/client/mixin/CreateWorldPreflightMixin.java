package com.remotemountains.client.mixin;

import com.remotemountains.client.TerrainPreflight;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.worldselection.CreateWorldScreen;
import net.minecraft.client.gui.screens.worldselection.WorldCreationUiState;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(CreateWorldScreen.class)
public abstract class CreateWorldPreflightMixin extends Screen {
    @Shadow @Final private WorldCreationUiState uiState;
    @Shadow private void onCreate() {}
    @Unique private boolean remotemountains$ready;

    protected CreateWorldPreflightMixin(Component title) { super(title); }

    @Inject(method = "onCreate", at = @At("HEAD"), cancellable = true)
    private void remotemountains$checkBeforeCreation(CallbackInfo ci) {
        if (remotemountains$ready) { remotemountains$ready = false; return; }
        String identity = TerrainPreflight.expectedIdentity(uiState.getSettings().selectedDimensions());
        if (identity == null) return;
        ci.cancel();
        Minecraft minecraft = Minecraft.getInstance();
        TerrainPreflight.run(minecraft, (Screen) (Object) this, identity, () -> {
            remotemountains$ready = true;
            minecraft.gui.setScreen((Screen) (Object) this);
            onCreate();
        }, () -> {});
    }
}
