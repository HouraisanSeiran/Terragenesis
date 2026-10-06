package com.remotemountains.client.mixin;

import com.remotemountains.client.TerrainPreflight;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.server.WorldStem;
import net.minecraft.server.packs.repository.PackRepository;
import net.minecraft.world.level.gamerules.GameRules;
import net.minecraft.world.level.storage.LevelStorageSource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.io.IOException;
import java.util.Optional;

@Mixin(Minecraft.class)
public abstract class WorldLoadPreflightMixin {
    @Shadow public abstract void doWorldLoad(LevelStorageSource.LevelStorageAccess access, PackRepository packs,
        WorldStem stem, Optional<GameRules> rules, boolean created);
    @Unique private boolean remotemountains$ready;

    @Inject(method = "doWorldLoad", at = @At("HEAD"), cancellable = true)
    private void remotemountains$checkBeforeServer(LevelStorageSource.LevelStorageAccess access, PackRepository packs,
        WorldStem stem, Optional<GameRules> rules, boolean created, CallbackInfo ci) {
        if (remotemountains$ready) { remotemountains$ready = false; return; }
        String identity = TerrainPreflight.expectedIdentity(stem.worldDataAndGenSettings().genSettings().dimensions());
        if (identity == null) return;
        ci.cancel();
        Minecraft client = (Minecraft) (Object) this;
        TerrainPreflight.run(client, new TitleScreen(),
            identity, () -> { remotemountains$ready = true; doWorldLoad(access, packs, stem, rules, created); }, () -> {
                stem.close();
                try { access.close(); } catch (IOException ignored) {}
            });
    }
}
