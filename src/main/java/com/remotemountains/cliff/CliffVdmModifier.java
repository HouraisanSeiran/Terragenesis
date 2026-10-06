package com.remotemountains.cliff;

import com.remotemountains.vdm.*;

/** Bakes a locally simulated rock surface back into XYZ displacements. */
public final class CliffVdmModifier implements SurfaceModifier {
    private final CliffPipeline.Result result;
    public CliffVdmModifier(CliffPipeline.Result result){this.result=result;}
    public CliffPipeline.Result result(){return result;}
    public Displacement apply(double x,double z,Displacement base){
        Displacement d=result.patch().delta(x,z);
        return new Displacement(base.dx()+d.dx(),base.dy()+d.dy(),base.dz()+d.dz());
    }
}
