package com.remotemountains.cliff;

import com.remotemountains.core.BaseTerrainSource;

/** Builds a densely sampled wall, slope or overhang, connected to the original terrain. */
public final class CliffGeometry {
    public CliffPatch build(BaseTerrainSource base,CliffSettings settings){
        CliffPatch p=new CliffPatch(settings);
        for(int row=0;row<p.rows;row++)for(int col=0;col<p.columns;col++){
            int i=p.index(col,row);double u=p.u(col),v=p.v(row);
            Vec3 horizontal=CliffPatch.ALONG.scale(u).add(CliffPatch.OUT.scale(v));
            double x=CliffSettings.CENTER_X+horizontal.x(),z=CliffSettings.CENTER_Z+horizontal.z();
            p.reference[i]=new Vec3(x,base.sample(x,z).height(),z);
            double end=CliffSettings.smooth((CliffSettings.HALF_LENGTH-Math.abs(u))/42);
            double t=CliffSettings.clamp((CliffSettings.WALL_HALF_WIDTH-v)/(2*CliffSettings.WALL_HALF_WIDTH),0,1);
            double collar=CliffSettings.smooth((CliffSettings.HALF_DEPTH-Math.abs(v))/(CliffSettings.HALF_DEPTH-CliffSettings.WALL_HALF_WIDTH));
            double target=(t-.5)*settings.topOffset();
            double horizontalDelta=(target-CliffSettings.clamp(v,-CliffSettings.WALL_HALF_WIDTH,CliffSettings.WALL_HALF_WIDTH))*end*collar;
            double verticalDelta=(t-.5)*CliffSettings.HEIGHT*end*collar;
            p.skeleton[i]=p.reference[i].add(CliffPatch.OUT.scale(horizontalDelta)).add(new Vec3(0,verticalDelta,0));
            p.positions[i]=p.skeleton[i];
            p.mask[i]=end*CliffSettings.smooth((CliffSettings.WALL_HALF_WIDTH+10-Math.abs(v))/12);
            p.hardness[i]=1;
        }
        p.refreshGeometry();
        for(int i=0;i<p.size;i++)p.axis[i]=p.normals[i];
        return p;
    }
}
