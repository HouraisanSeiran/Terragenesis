package com.remotemountains.prepared;

import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.SurfaceModifier;

/** Baked local erosion and cliff displacement; no solver runs during chunk generation. */
public final class PreparedSurfaceModifier implements SurfaceModifier {
    private final PreparedArtifact artifact;
    public PreparedSurfaceModifier(PreparedArtifact artifact){this.artifact=artifact;}
    @Override public Displacement apply(double x,double z,Displacement initial){
        return artifact.apply(x,z,initial);
    }
}
