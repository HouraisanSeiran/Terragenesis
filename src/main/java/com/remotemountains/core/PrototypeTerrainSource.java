package com.remotemountains.core;

/** Historical non-diffusion baseline. Tests only; the Fabric generator never selects it. */
public final class PrototypeTerrainSource implements BaseTerrainSource {
    private final Landscape landscape;
    private final Hydrology hydrology;
    public PrototypeTerrainSource(Landscape landscape,Hydrology hydrology){this.landscape=landscape;this.hydrology=hydrology;}
    public Terrain.Column sample(double x,double z){
        Landscape.Base base=landscape.base(x,z);Hydrology.Water water=hydrology.sample(x,z,base.height());
        double height=base.height()-water.incision();
        return new Terrain.Column(height,Double.isFinite(water.surface())&&water.surface()>height?water.surface():Double.NaN,base);
    }
}
