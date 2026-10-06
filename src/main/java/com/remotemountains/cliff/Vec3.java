package com.remotemountains.cliff;

/** Small immutable world-space vector used by the surface simulation. */
public record Vec3(double x,double y,double z) {
    public Vec3 add(Vec3 b){return new Vec3(x+b.x,y+b.y,z+b.z);}
    public Vec3 subtract(Vec3 b){return new Vec3(x-b.x,y-b.y,z-b.z);}
    public Vec3 scale(double s){return new Vec3(x*s,y*s,z*s);}
    public double dot(Vec3 b){return x*b.x+y*b.y+z*b.z;}
    public Vec3 cross(Vec3 b){return new Vec3(y*b.z-z*b.y,z*b.x-x*b.z,x*b.y-y*b.x);}
    public double length(){return Math.sqrt(dot(this));}
    public Vec3 normalized(){double n=length();return n>1e-10?scale(1/n):new Vec3(0,1,0);}
}
