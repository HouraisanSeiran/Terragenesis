package com.remotemountains.cliff;

import com.remotemountains.core.*;
import com.remotemountains.vdm.*;
import java.util.*;

/** Lazy bounded patch cache shared by all chunks; local simulation is independent of load order. */
public final class RegionalCliffModifier implements SurfaceModifier {
    private final BaseTerrainSource base;
    private final RegionalCliffLayout layout;
    private final boolean demo;
    private final Map<Long,Optional<CliffPipeline.Result>> patches=new LinkedHashMap<>(16,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,Optional<CliffPipeline.Result>> e){return size()>12;}
    };
    public RegionalCliffModifier(BaseTerrainSource base,long seed,boolean demo){
        this.base=base;this.demo=demo;layout=new RegionalCliffLayout(seed,demo);
    }
    public synchronized CliffPipeline.Result patch(CliffPlacement placement){
        return patches.computeIfAbsent(placement.key(),k->Optional.ofNullable(build(placement))).orElse(null);
    }
    private CliffPipeline.Result build(CliffPlacement placement){
        BaseTerrainSource local=(x,z)->{var p=placement.toWorld(x,z);return base.sample(p.x(),p.z());};
        // Skip flooded and near-ceiling surfaces: do not manufacture cliffs in open ocean.
        if(!demo)for(int z=216;z<=296;z+=40)for(int x=216;x<=296;x+=40){
            var c=local.sample(x,z);if(c.height()<96||c.height()>265)return null;
        }
        return new CliffPipeline().build(local,placement.settings(),CliffPipeline.Stage.ERODED);
    }
    public synchronized Displacement apply(double x,double z,Displacement initial){
        Vec3 total=new Vec3(initial.dx(),initial.dy(),initial.dz());
        for(var site:layout.near(x,z)){
            if(!site.contains(x,z))continue;
            var result=patch(site);if(result==null)continue;
            Vec3 p=site.toLocal(x,z);var delta=result.patch().delta(p.x(),p.z());
            total=total.add(site.rotate(new Vec3(delta.dx(),delta.dy(),delta.dz())));
        }
        return new Displacement(total.x(),total.y(),total.z());
    }
    public synchronized int cachedPatches(){return patches.size();}
}
