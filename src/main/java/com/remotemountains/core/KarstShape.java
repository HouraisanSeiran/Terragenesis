package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class KarstShape implements LandformShape {
    private final Noise shape;
    private final ShapePrimitives primitives;
    public KarstShape(long seed){shape=new Noise(seed);primitives=new ShapePrimitives(seed);}
    public double height(Regions.Region r,double x,double z){
        double dx=x-r.x(),dz=z-r.z(),cs=Math.cos(r.angle()),sn=Math.sin(r.angle());
        double u=dx*cs+dz*sn,v=-dx*sn+dz*cs;
        double ox=Noise.unit(r.key()+31)*100,oz=Noise.unit(r.key()+32)*100;
        double n=shape.fbm(x/380+ox,z/380+oz,3);
        double floor=82+8*shape.fbm(x/950,z/950,3)+3*shape.at(x/150,z/150);

                double peaks=primitives.cluster(u,v,155,ox,oz,false);
                double basin=1-.88*Math.exp(-ShapePrimitives.sq((u-590)/330)-ShapePrimitives.sq((v+230)/450));
                double main=primitives.peak(u+130,v-50,105,120,155,ox);
                return floor+Math.max(main,peaks*basin)+3*n;
            
    }
}
