package com.remotemountains.client;

import com.remotemountains.core.TerrainModeDescriptor;
import com.remotemountains.core.TerrainModeRegistry;
import com.remotemountains.world.RemoteGenerator;
import java.util.List;
import net.minecraft.core.Holder;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.biome.Biome;

public enum LandformMode {
    PROCESSED("processed"), TUNED("raw"), RAW("raw_legacy"), REGION("region"),
    GLOBAL("global"), DEMO("demo"), WATERSHED("watershed"), CANYON("canyon"),
    CANYON_SINGLE("canyon_single");

    private final String key;
    private final TerrainModeDescriptor descriptor;

    LandformMode(String key) {
        this.key = key;
        this.descriptor = TerrainModeRegistry.selectable(key);
    }

    public Component label() {
        return Component.translatable("remotemountains.mode." + key);
    }

    public static LandformMode of(RemoteGenerator generator) {
        for (LandformMode mode : values()) {
            if (mode.matches(generator)) return mode;
        }
        return PROCESSED;
    }

    public boolean matches(RemoteGenerator generator) {
        return descriptor.source().equals(generator.terrainSource())
            && descriptor.recipe().equals(generator.recipe());
    }

    public RemoteGenerator create(List<Holder<Biome>> palette, int regionChunks) {
        return new RemoteGenerator(palette, "", descriptor.recipe(), "", descriptor.source(),
            descriptor.scaleId(), regionChunks, "none_v1");
    }
    public boolean supportsRegions() {
        return descriptor.supportsRegions();
    }
}
