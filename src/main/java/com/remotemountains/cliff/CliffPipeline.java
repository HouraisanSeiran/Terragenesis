package com.remotemountains.cliff;

import com.remotemountains.core.BaseTerrainSource;

/** Runs once per generator; chunk requests reuse the same immutable completed chart. */
public final class CliffPipeline {
    public enum Stage { SKELETON, ROCK, ERODED }
    public record Result(CliffPatch patch,ErosionStatistics statistics){}
    public Result build(BaseTerrainSource base,CliffSettings settings,Stage stage){
        return build(base,settings,stage,new RunoffBoundary());
    }
    public Result build(BaseTerrainSource base,CliffSettings settings,Stage stage,RunoffBoundary boundary){
        CliffPatch patch=new CliffGeometry().build(base,settings);
        if(stage!=Stage.SKELETON)new VoronoiRockField(settings.seed()).apply(patch);
        ErosionStatistics statistics=stage==Stage.ERODED?new SurfaceRunoffSolver().run(patch,boundary):null;
        return new Result(patch,statistics);
    }
}
