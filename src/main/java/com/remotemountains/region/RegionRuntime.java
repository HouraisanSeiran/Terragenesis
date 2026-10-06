package com.remotemountains.region;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.TerrainScale;
import com.remotemountains.diffusion.DemoLandformSource;
import com.remotemountains.diffusion.DiffusionTerrainSource;
import com.remotemountains.diffusion.DiffusionServiceManager;
import com.remotemountains.cliff.RegionalCliffModifier;
import java.nio.file.Path;
import java.nio.file.Files;
import java.io.IOException;
import java.util.Properties;
import java.util.function.Supplier;

/** Opt-in tall-world region binding. */
public final class RegionRuntime {
    private RegionRuntime() {}
    public static RegionTerrainSource create(long seed,String identity,String recipe,String scaleId,
            int chunks,String processing){
        return create(seed,identity,recipe,scaleId,chunks,processing,"region_diffusion_v1");
    }
    public static RegionTerrainSource create(long seed,String identity,String recipe,String scaleId,
            int chunks,String processing,String mode){
        if(!RegionTerrainSource.RECIPE.equals(recipe)||!TerrainScale.TALL.equals(TerrainScale.of(scaleId)))
            throw new IllegalArgumentException("Region terrain requires regional XYZ recipe and tall scale");
        RegionConfig config=new RegionConfig(chunks,processing);
        Supplier<BaseTerrainSource> producer=switch(mode){
            case "region_diffusion_v1" -> ()->new DiffusionTerrainSource(seed,identity);
            case "region_demo_v1" -> ()->new DemoLandformSource(seed,identity,true);
            default -> throw new IllegalArgumentException("Unsupported region source: "+mode);
        };
        Path root=regionRoot();
        if(mode.equals("region_demo_v1"))root=root.resolve("demo");
        return new RegionTerrainSource(root,seed,identity,recipe,config,producer,
            base->new RegionalCliffModifier(base,seed,false));
    }
    public static RawRegionTerrainSource createRaw(long seed,String identity,String recipe,String scaleId,
            int chunks,String processing){
        if(!RawRegionTerrainSource.RECIPE.equals(recipe)&&!RawRegionTerrainSource.TUNED_RECIPE.equals(recipe))
            throw new IllegalArgumentException("Unsupported raw region recipe: "+recipe);
        if(!TerrainScale.RAW_MODEL.equals(TerrainScale.of(scaleId)))
            throw new IllegalArgumentException("Raw region requires the raw model recipe and one-to-one tall scale");
        return new RawRegionTerrainSource(regionRoot(),seed,identity,recipe,new RegionConfig(chunks,processing));
    }
    public static DerivedRegionTerrainSource createProcessed(long seed,String identity,String recipe,String scaleId,
            int chunks,String processing){
        if(!DerivedRegionTerrainSource.RECIPE.equals(recipe)
                ||!TerrainScale.RAW_MODEL.equals(TerrainScale.of(scaleId)))
            throw new IllegalArgumentException("Processed region requires its recipe and one-to-one tall scale");
        return new DerivedRegionTerrainSource(regionRoot(),seed,identity,new RegionConfig(chunks,processing));
    }
    private static Path regionRoot(){
        Properties settings=new Properties();
        Path configFile=net.fabricmc.loader.api.FabricLoader.getInstance().getConfigDir()
            .resolve("terragenesis-regions.properties");
        if(Files.exists(configFile))try(var input=Files.newBufferedReader(configFile,java.nio.charset.StandardCharsets.UTF_8)){
            settings.load(input);
        }catch(IOException e){throw new IllegalStateException("Cannot read region configuration",e);}
        String regionDir=System.getProperty("remotemountains.regionDir");
        if(regionDir==null||regionDir.isBlank())regionDir=settings.getProperty("regionDir");
        Path root=regionDir==null||regionDir.isBlank()
            ?DiffusionServiceManager.homePath().resolve("regions"):Path.of(regionDir);
        if(Boolean.parseBoolean(settings.getProperty("offlineOnly","false"))
                &&System.getProperty("remotemountains.regionOffline")==null)
            System.setProperty("remotemountains.regionOffline","true");
        return root;
    }
}
