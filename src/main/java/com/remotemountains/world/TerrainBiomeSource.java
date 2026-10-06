package com.remotemountains.world;

import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import java.util.List;
import java.util.stream.Stream;
import net.minecraft.core.Holder;
import net.minecraft.world.level.biome.*;

/** The same seed-bound biome resolver is used by chunks, biome lookup and decoration. */
public final class TerrainBiomeSource extends BiomeSource {
    public static final MapCodec<TerrainBiomeSource> CODEC=RecordCodecBuilder.mapCodec(i->i.group(
        Biome.CODEC.listOf().fieldOf("biomes").forGetter(s->s.palette)
    ).apply(i,TerrainBiomeSource::new));
    private final List<Holder<Biome>> palette;
    private volatile Terrain terrain;
    public TerrainBiomeSource(List<Holder<Biome>> palette){
        if(palette.size()!=16)throw new IllegalArgumentException("Expected 16 climate/landform biomes");
        this.palette=List.copyOf(palette);
    }
    public void bind(Terrain terrain){this.terrain=terrain;}
    protected MapCodec<? extends BiomeSource> codec(){return CODEC;}
    protected Stream<Holder<Biome>> collectPossibleBiomes(){return palette.stream();}
    public BiomeResolver createResolver(Climate.Sampler ignored){
        Terrain bound=terrain;
        if(bound==null)throw new IllegalStateException("Biome source must be bound to world seed before sampling");
        return (x,y,z)->{
            int worldX = Math.multiplyExact(x, 4);
            int worldZ = Math.multiplyExact(z, 4);
            bound.prepareBounds(worldX, worldZ, worldX, worldZ);
            Landscape.Base b=bound.sample(worldX,worldZ).base();
            return palette.get(b.type().ordinal()*4+b.climate().variant());
        };
    }
}
