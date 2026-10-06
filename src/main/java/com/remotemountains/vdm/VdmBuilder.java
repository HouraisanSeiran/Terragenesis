package com.remotemountains.vdm;

import com.remotemountains.core.*;

/** Converts diffusion heights to XYZ displacements, then optionally sculpts local cliffs. */
public final class VdmBuilder {
    public static final int HALO=16,SPACING=2;
    private final BaseTerrainSource base;
    private final SurfaceModifier sculptor;
    private final int spacing,halo;
    public VdmBuilder(BaseTerrainSource base){this(base,null);}
    public VdmBuilder(BaseTerrainSource base,SurfaceModifier sculptor){this(base,sculptor,SPACING,HALO);}
    public VdmBuilder(BaseTerrainSource base,SurfaceModifier sculptor,int spacing,int halo){
        if(spacing<1||halo<0||halo%spacing!=0)throw new IllegalArgumentException("Invalid VDM sampling");
        this.base=base;this.sculptor=sculptor;this.spacing=spacing;this.halo=halo;
    }
    public VectorDisplacementMap build(int ox,int oz,int width){
        int n=(width+2*halo)/spacing+1;
        double[][] heights=new double[n+2][n+2];
        for(int z=0;z<n+2;z++)for(int x=0;x<n+2;x++)heights[z][x]=base.sample(ox-halo+(x-1)*spacing,oz-halo+(z-1)*spacing).height();
        Displacement[] vectors=new Displacement[n*n];
        for(int z=0;z<n;z++)for(int x=0;x<n;x++){
            double h=heights[z+1][x+1];
            Displacement d=new Displacement(0,h-72,0);
            vectors[z*n+x]=sculptor==null?d:sculptor.apply(ox-halo+x*spacing,oz-halo+z*spacing,d);
        }
        return new VectorDisplacementMap(ox-halo,oz-halo,n,spacing,vectors);
    }
}
