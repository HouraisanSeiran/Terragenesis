package com.remotemountains.world;
import com.remotemountains.core.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
/** Maps density, rock type and current climate to vanilla blocks. */
public final class SurfacePalette {
    public BlockState sample(Terrain t,int x,int y,int z,Terrain.Column c){
        if (t.metricSurface()) {
            if (y <= -61) {
                return Blocks.BEDROCK.defaultBlockState();
            }
            if (!t.solid(x, y, z, c)) {
                return Blocks.AIR.defaultBlockState();
            }
            int surface = (int) Math.floor(c.height());
            if (y == surface) {
                return Blocks.GRASS_BLOCK.defaultBlockState();
            }
            if (y >= surface - 3) {
                return Blocks.DIRT.defaultBlockState();
            }
            return y < 0 ? Blocks.DEEPSLATE.defaultBlockState() : Blocks.STONE.defaultBlockState();
        }
        if(y<=-61)return Blocks.BEDROCK.defaultBlockState();
        int surface=(int)Math.floor(c.height());int variant=c.base().climate().variant();
        boolean wet=Double.isFinite(c.water())&&c.water()>surface;
        if(!t.solid(x,y,z,c)){
            if(y>surface&&Double.isFinite(c.water())&&y<=c.water())return (variant==0&&y==(int)c.water()?Blocks.ICE:Blocks.WATER).defaultBlockState();
            if(y==surface+1&&variant==0&&!wet)return Blocks.SNOW.defaultBlockState();
            return Blocks.AIR.defaultBlockState();
        }
        if(y==surface)return (wet?Blocks.GRAVEL:variant==1?Blocks.SAND:Blocks.GRASS_BLOCK).defaultBlockState();
        if(y>=surface-3*t.scale.factor())return (variant==1?Blocks.SANDSTONE:Blocks.DIRT).defaultBlockState();
        if(y<0)return Blocks.DEEPSLATE.defaultBlockState();
        Landform type=c.base().type();
        double localY=t.scale.localHeight(y);
        return (type==Landform.KARST?(localY%17<3?Blocks.CALCITE:Blocks.STONE):type==Landform.PILLARS?(localY%24<4?Blocks.TERRACOTTA:Blocks.SANDSTONE):Blocks.STONE).defaultBlockState();
    }
}
