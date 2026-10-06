package com.remotemountains.vdm;

/** Local finite fault scarp in world coordinates. Smooth mask makes tile boundaries irrelevant. */
public final class CliffSculptor implements SurfaceModifier {
    public static final String RECIPE="diffusion-vdm-cliff-v1";
    public Displacement apply(double x,double z,Displacement base){
        double cx=256,cz=256,rx=144,rz=164;
        double radius=Math.hypot((x-cx)/rx,(z-cz)/rz);
        double mask=Math.max(0,1-radius);mask=mask*mask*(3-2*mask);
        double nx=1/Math.hypot(1,.35),nz=.35/Math.hypot(1,.35);
        double profile=Math.tanh(((x-cx)*nx+(z-cz)*nz)/5);
        double lip=8*(1-profile*profile)*mask;
        return new Displacement(base.dx()+nx*lip,base.dy()+21*profile*mask,base.dz()+nz*lip);
    }
}
