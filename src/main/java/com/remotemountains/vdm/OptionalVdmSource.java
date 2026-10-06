package com.remotemountains.vdm;

import com.remotemountains.core.*;
import java.nio.file.*;

/** Diffusion supplies every base column; an exported VDM deforms only its covered area. */
public final class OptionalVdmSource implements BaseTerrainSource {
    private final BaseTerrainSource base;
    private final VdmTerrainSource sculpted;
    public OptionalVdmSource(BaseTerrainSource base){
        this.base=base;
        sculpted=System.getProperty("remotemountains.vdmFile","").isBlank()?null:new VdmTerrainSource(base);
    }
    public String identity(){return base.identity();}
    public String vdmIdentity(){return sculpted==null?"none":sculpted.vdmIdentity();}
    public Terrain.Column sample(double x,double z){
        if(sculpted==null||!sculpted.covers(x,z))return base.sample(x,z);
        return sculpted.sample(x,z);
    }
}
