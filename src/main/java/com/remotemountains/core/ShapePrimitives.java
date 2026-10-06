package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class ShapePrimitives {
    private final long seed; private final Noise shape;
    public ShapePrimitives(long seed){this.seed=seed;shape=new Noise(seed);}
    public double peak(double x,double z,double rx,double rz,double height,double offset){
        double wx=x+22*shape.at(x/110+offset,z/110),wz=z+19*shape.at(x/130,z/130+offset);
        double d=Math.sqrt(sq(wx/rx)+sq(wz/rz));
        double rough=1+.10*shape.fbm(x/75+offset,z/75,3);
        return Math.pow(Math.max(0,1-d*d),.70)*height*rough;
    }
    public double cluster(double u,double v,double spacing,double ox,double oz,boolean pillars){
        double wx=u+38*shape.at(u/280+ox,v/280),wz=v+38*shape.at(u/280,v/280+oz);
        int gx=(int)Math.floor(wx/spacing),gz=(int)Math.floor(wz/spacing);double highest=0;
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){
            int ix=gx+dx,iz=gz+dz;long h=hash(seed+(long)(ox*10000),ix,iz);
            boolean core=Math.abs(ix)<=1&&Math.abs(iz)<=1;
            if(!core&&unit(h)>(pillars?.67:.54))continue;
            double px=(ix+.15+.7*unit(h+1))*spacing,pz=(iz+.15+.7*unit(h+2))*spacing;
            double radius=(pillars?27:51)+(pillars?25:38)*unit(h+3);
            double d=Math.hypot((wx-px)/(radius*(.7+.6*unit(h+4))),(wz-pz)/radius);
            double height=75+115*unit(h+5);
            double profile=pillars?(1-smooth(.65,1.16,d)):Math.pow(Math.max(0,1-d*d),.72);
            highest=Math.max(highest,profile*height);
        }
        return highest;
    }
    public static double sq(double a){return a*a;}
}
