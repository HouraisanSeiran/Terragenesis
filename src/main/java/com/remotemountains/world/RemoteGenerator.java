package com.remotemountains.world;

import com.mojang.serialization.MapCodec;
import com.mojang.serialization.Codec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import com.remotemountains.core.*;
import java.util.*;
import java.util.concurrent.*;
import net.minecraft.core.*;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.levelgen.*;
import net.minecraft.world.level.levelgen.blending.Blender;
import net.minecraft.world.level.levelgen.densityfunction.SamplerContext;

public final class RemoteGenerator extends ChunkGenerator {
    public static final MapCodec<RemoteGenerator> CODEC=RecordCodecBuilder.mapCodec(i->i.group(
        Biome.CODEC.listOf().fieldOf("biomes").forGetter(g->g.palette),
        Codec.STRING.optionalFieldOf("diffusion_identity","").forGetter(g->g.modelIdentity()),
        Codec.STRING.optionalFieldOf("vdm_recipe","diffusion-vdm-cliff-v1").forGetter(g->g.recipe),
        Codec.STRING.optionalFieldOf("vdm_identity","").forGetter(g->g.vdmIdentity),
        Codec.STRING.optionalFieldOf("terrain_source","legacy_auto").forGetter(g->g.terrainSource),
        Codec.STRING.optionalFieldOf("terrain_scale","legacy").forGetter(g->g.scaleId),
        Codec.INT.optionalFieldOf("region_chunks",24).forGetter(g->g.regionChunks),
        Codec.STRING.optionalFieldOf("region_processing","none_v1").forGetter(g->g.regionProcessing)
    ).apply(i,RemoteGenerator::new));
    private static final Set<RemoteGenerator> LIVE=ConcurrentHashMap.newKeySet();
    private final List<Holder<Biome>> palette;
    private volatile Terrain terrain;
    private String modelIdentity;
    private String vdmIdentity;
    private final String recipe;
    private final String terrainSource;
    private final String scaleId;
    private final int regionChunks;
    private final String regionProcessing;
    private final TerrainScale scale;
    private final SurfacePalette surface=new SurfacePalette();
    public RemoteGenerator(List<Holder<Biome>> palette,String modelIdentity,String recipe,String vdmIdentity,String terrainSource,String scaleId){
        this(palette,modelIdentity,recipe,vdmIdentity,terrainSource,scaleId,24,"none_v1");
    }
    public RemoteGenerator(List<Holder<Biome>> palette,String modelIdentity,String recipe,String vdmIdentity,String terrainSource,String scaleId,int regionChunks,String regionProcessing){
        super(new TerrainBiomeSource(palette));
        TerrainModeDescriptor mode = TerrainModeRegistry.requireValid(terrainSource, recipe, scaleId);
        this.recipe=recipe;
        this.terrainSource=terrainSource;
        this.scaleId=scaleId;scale=TerrainScale.of(scaleId);
        this.regionChunks=regionChunks;this.regionProcessing=regionProcessing;
        if (mode.supportsRegions() || terrainSource.equals("metric_processed_readonly_v1")) {
            new com.remotemountains.region.RegionConfig(regionChunks, regionProcessing);
        }
        if(palette.size()!=16)throw new IllegalArgumentException("Expected four climates for each of four landforms");
        this.palette=List.copyOf(palette);this.modelIdentity=modelIdentity;this.vdmIdentity=vdmIdentity;LIVE.add(this);
    }
    private synchronized Terrain terrain(RandomState random){
        if(terrain==null){
            Terrain created=new Terrain(random.seed(),modelIdentity,recipe,terrainSource,scaleId,regionChunks,regionProcessing);
            if(!vdmIdentity.isEmpty()&&!vdmIdentity.equals(created.vdmIdentity())){created.close();throw new IllegalStateException("Saved world VDM differs from supplied map");}
            terrain=created;modelIdentity=terrain.identity();vdmIdentity=terrain.vdmIdentity();((TerrainBiomeSource)biomeSource).bind(terrain);
        }
        if(terrain.landscape.seed!=random.seed())throw new IllegalStateException("Generator reused with different world seed");
        return terrain;
    }
    public static void closeAll(){for(RemoteGenerator g:LIVE)if(g.terrain!=null)g.terrain.close();LIVE.clear();}
    public String recipe(){return recipe;}
    public String terrainSource(){return terrainSource;}
    public String scaleId(){return scaleId;}
    public List<Holder<Biome>> palette(){return palette;}
    public int regionChunks(){return regionChunks;}
    public String modelIdentity(){return terrain==null?modelIdentity:terrain.identity();}
    Terrain verificationTerrain(){return terrain;}
    @Override public ChunkGeneratorStructureState createState(HolderLookup<net.minecraft.world.level.levelgen.structure.StructureSet> structures,RandomState random,long seed){
        terrain(random);return super.createState(structures,random,seed);
    }
    protected MapCodec<? extends ChunkGenerator> codec(){return CODEC;}
    public int getGenDepth(){return scale.depth();}
    public int getMinY(){return scale.minY();}
    public int getSeaLevel(){return scale.seaLevel();}
    @Override public CompletableFuture<ChunkAccess> createBiomes(RandomState random,Blender blender,StructureManager structures,ChunkAccess chunk){
        Terrain prepared = terrain(random);
        int chunkX = chunk.getPos().getMinBlockX();
        int chunkZ = chunk.getPos().getMinBlockZ();
        prepared.prepareBounds(chunkX, chunkZ, chunkX + 15, chunkZ + 15);
        chunk.fillBiomesFromNoise(biomeSource.createUncachedResolver(random));
        return CompletableFuture.completedFuture(chunk);
    }
    @Override public CompletableFuture<ChunkAccess> buildTerrain(ChunkAccess chunk,Blender blender,RandomState random,StructureManager structures,BiomeManager manager,WorldGenRegion region,Set<Holder<Biome>> biomes){
        Terrain t=terrain(random);int sx=chunk.getPos().getMinBlockX(),sz=chunk.getPos().getMinBlockZ();
        int tx=Math.floorDiv(sx,Terrain.TILE),tz=Math.floorDiv(sz,Terrain.TILE);
        t.prepareBounds(tx * Terrain.TILE, tz * Terrain.TILE,
            tx * Terrain.TILE + Terrain.TILE - 1, tz * Terrain.TILE + Terrain.TILE - 1);
        // DH ignores buildTerrain's future, so finish chunk writes before returning to its next step.
        Terrain.Column[] columns=t.tile(tx,tz).join();
        BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
            for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                int wx=sx+x,wz=sz+z;Terrain.Column c=columns[Math.floorMod(wz,Terrain.TILE)*Terrain.TILE+Math.floorMod(wx,Terrain.TILE)];
                int requestedTop=(int)Math.ceil(Math.max(c.height(),Double.isFinite(c.water())?c.water():c.height()))+1;
                if(t.metricSurface() && requestedTop>=scale.upperY())throw new IllegalStateException("Metric terrain exceeds build height");
                int top=Math.min(scale.upperY()-1,requestedTop);
                for(int y=scale.minY();y<=top;y++){
                    BlockState state=surface.sample(t,wx,y,wz,c);
                    if(!state.isAir())chunk.setBlockState(pos.set(wx,y,wz),state,0);
                }
            }
            Heightmap.primeHeightmaps(chunk,EnumSet.of(Heightmap.Types.WORLD_SURFACE_WG,Heightmap.Types.OCEAN_FLOOR_WG,Heightmap.Types.MOTION_BLOCKING,Heightmap.Types.WORLD_SURFACE,Heightmap.Types.OCEAN_FLOOR));
        if (!t.needsPreparation()) t.prefetch(tx,tz);
        return CompletableFuture.completedFuture(chunk);
    }
    public int getBaseHeight(int x,int z,Heightmap.Types type,LevelHeightAccessor level,RandomState random){
        Terrain t=terrain(random);t.prepareBounds(x,z,x,z);Terrain.Column c=t.sample(x,z);
        for(int y=Math.min(level.getMaxY(),scale.upperY()-1);y>=Math.max(level.getMinY(),scale.minY());y--)if(type.isOpaque().test(surface.sample(t,x,y,z,c)))return y+1;
        return level.getMinY();
    }
    public NoiseColumn getBaseColumn(int x,int z,LevelHeightAccessor level,RandomState random){
        Terrain t=terrain(random);t.prepareBounds(x,z,x,z);Terrain.Column c=t.sample(x,z);BlockState[] states=new BlockState[level.getHeight()];
        for(int i=0;i<states.length;i++)states[i]=surface.sample(t,x,level.getMinY()+i,z,c);
        return new NoiseColumn(level.getMinY(),states);
    }
    public void spawnOriginalMobs(WorldGenRegion region){
        NaturalSpawner.spawnMobsForChunkGeneration(region,new BlockPos(region.getCenter().getMiddleBlockX(),90*scale.factor(),region.getCenter().getMiddleBlockZ()),region.getCenter(),region.getRandom());
    }
    public void addDebugScreenInfo(List<String> lines,RandomState random,BlockPos pos,SamplerContext context){
        Terrain t=terrain(random);
        t.prepareBounds(pos.getX(),pos.getZ(),pos.getX(),pos.getZ());
        Terrain.Column c=t.sample(pos.getX(),pos.getZ());
        lines.add("Remote Mountains: "+c.base().type().title+" / climate "+c.base().climate().variant());
        lines.add("Terrain recipe: "+recipe);
    }
}
