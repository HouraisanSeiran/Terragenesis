package com.remotemountains.client.mixin;

import com.remotemountains.client.LandformSettingsScreen;
import com.remotemountains.world.RemoteGenerator;
import net.minecraft.client.gui.screens.worldselection.PresetEditor;
import net.minecraft.client.gui.screens.worldselection.WorldCreationUiState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(WorldCreationUiState.class)
public abstract class LandformPresetEditorMixin {
    @Inject(method = "getPresetEditor", at = @At("HEAD"), cancellable = true)
    private void remotemountains$editor(CallbackInfoReturnable<PresetEditor> result) {
        WorldCreationUiState state = (WorldCreationUiState) (Object) this;
        if (state.getSettings().selectedDimensions().overworld() instanceof RemoteGenerator) {
            result.setReturnValue((parent, context) -> new LandformSettingsScreen(parent));
        }
    }
}
