package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class RiftShape implements LandformShape {
    private final Noise shape;
    private final ShapePrimitives primitives;
    public RiftShape(long seed){shape=new Noise(seed);primitives=new ShapePrimitives(seed);}
    public double height(Regions.Region r,double x,double z){
        double dx=x-r.x(),dz=z-r.z(),cs=Math.cos(r.angle()),sn=Math.sin(r.angle());
        double u=dx*cs+dz*sn,v=-dx*sn+dz*cs;
        double ox=Noise.unit(r.key()+31)*100,oz=Noise.unit(r.key()+32)*100;
        double n=shape.fbm(x/380+ox,z/380+oz,3);
        double floor=82+8*shape.fbm(x/950,z/950,3)+3*shape.at(x/150,z/150);

                double axis=120*shape.at(v/760+ox,oz)+55*Math.sin(v/570+ox);
                double cross=u-axis,width=135+50*shape.at(v/470,oz);
                double wall=smooth(width,width+90+45*shape.at(v/260+1,oz),Math.abs(cross));
                double bench=smooth(width+260,width+365,Math.abs(cross));
                double amplitude=cross>0?113:157;
                double broken=14*shape.fbm(u/240+ox,v/310+oz,3);
                return floor+wall*(amplitude+broken)+bench*22+4*n;
            
    }
}
