package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class InselbergShape implements LandformShape {
    private final Noise shape;
    private final ShapePrimitives primitives;
    public InselbergShape(long seed){shape=new Noise(seed);primitives=new ShapePrimitives(seed);}
    public double height(Regions.Region r,double x,double z){
        double dx=x-r.x(),dz=z-r.z(),cs=Math.cos(r.angle()),sn=Math.sin(r.angle());
        double u=dx*cs+dz*sn,v=-dx*sn+dz*cs;
        double ox=Noise.unit(r.key()+31)*100,oz=Noise.unit(r.key()+32)*100;
        double n=shape.fbm(x/380+ox,z/380+oz,3);
        double floor=82+8*shape.fbm(x/950,z/950,3)+3*shape.at(x/150,z/150);

                double main=primitives.peak(u,v,285,210,185,ox);
                double satellites=Math.max(primitives.peak(u-690,v+240,190,145,100,ox+5),primitives.peak(u+520,v-550,155,220,125,ox+13));
                return floor+Math.max(main,satellites)+5*n;
            
    }
}
