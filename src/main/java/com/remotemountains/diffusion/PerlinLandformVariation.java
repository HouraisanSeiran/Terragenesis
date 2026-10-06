package com.remotemountains.diffusion;

import com.remotemountains.core.*;

/** World-coordinate, seed-stable domain warping and relief modulation in block units. */
public final class PerlinLandformVariation {
    public record Point(double x,double z) {}
    private final Noise broad,detail;
    public PerlinLandformVariation(long seed){
        broad=new Noise(seed^0x3C6EF372FE94F82BL);
        detail=new Noise(seed^0x510E527FADE682D1L);
    }
    public Point warp(double x,double z){
        double dx=65*broad.fbm(x/140,z/140,3)+16*detail.fbm(x/38,z/38,2);
        double dz=65*broad.fbm(x/140+83,z/140-47,3)+16*detail.fbm(x/38-39,z/38+91,2);
        return new Point(x+dx,z+dz);
    }
    public double mask(double x,double z,double cx,double cz){
        Point p=warp(x,z);
        double distance=Math.hypot(p.x()-cx,p.z()-cz);
        // Compact unwarped envelope keeps the demo ocean collar and centre cliff intact.
        return (1-Noise.smooth(70,205,distance))
            *(1-Noise.smooth(185,222,Math.hypot(x-cx,z-cz)));
    }
    public double relief(double x,double z,double height,Landform type){
        double mass=broad.fbm(x/72+13,z/72-27,3);
        double folds=detail.fbm(x/23,z/23,3);
        double grain=detail.fbm(x/8+33,z/8-71,2);
        double weight=Noise.smooth(1,22,Math.abs(height));
        // Cut irregular notches and shoulders, and break up flat column tops.
        double groove=Noise.smooth(.05,.55,broad.fbm(x/55+11,z/110-19,3));
        double incision=groove*(type==Landform.PILLARS?5:9);
        return height*(1+.34*mass+.10*folds)
            +weight*(6*folds+1.3*grain-incision);
    }
}
