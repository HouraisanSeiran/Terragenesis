package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class PillarShape implements LandformShape {
    private final Noise shape;
    private final ShapePrimitives primitives;
    public PillarShape(long seed){shape=new Noise(seed);primitives=new ShapePrimitives(seed);}
    public double height(Regions.Region r,double x,double z){
        double dx=x-r.x(),dz=z-r.z(),cs=Math.cos(r.angle()),sn=Math.sin(r.angle());
        double u=dx*cs+dz*sn,v=-dx*sn+dz*cs;
        double ox=Noise.unit(r.key()+31)*100,oz=Noise.unit(r.key()+32)*100;
        double n=shape.fbm(x/380+ox,z/380+oz,3);
        double floor=82+8*shape.fbm(x/950,z/950,3)+3*shape.at(x/150,z/150);

                double clustered=primitives.cluster(u,v,125,ox,oz,true);
                double intact=smooth(.14,.42,shape.fbm(u/620+ox,v/620+oz,2));
                double plateau=intact*(105+23*n);
                // The central landmark stays a column group, not a continuous mesa.
                plateau*=smooth(240,700,Math.hypot(u,v));
                return floor+Math.max(clustered,plateau)+2*n;
            
    }
}
