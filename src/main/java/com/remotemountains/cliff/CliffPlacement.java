package com.remotemountains.cliff;

/** Rigid horizontal transform: solve gravity in local coordinates, then rotate XYZ back. */
public record CliffPlacement(long key,double x,double z,double rotation,CliffSettings settings) {
    public Vec3 toWorld(double localX,double localZ){
        double dx=localX-256,dz=localZ-256,c=Math.cos(rotation),s=Math.sin(rotation);
        return new Vec3(x+c*dx-s*dz,0,z+s*dx+c*dz);
    }
    public Vec3 toLocal(double wx,double wz){
        double dx=wx-x,dz=wz-z,c=Math.cos(rotation),s=Math.sin(rotation);
        return new Vec3(256+c*dx+s*dz,0,256-s*dx+c*dz);
    }
    public Vec3 rotate(Vec3 v){
        double c=Math.cos(rotation),s=Math.sin(rotation);
        return new Vec3(c*v.x()-s*v.z(),v.y(),s*v.x()+c*v.z());
    }
    public boolean contains(double wx,double wz){
        Vec3 p=toLocal(wx,wz).subtract(new Vec3(256,0,256));
        return Math.abs(p.dot(CliffPatch.ALONG))<160&&Math.abs(p.dot(CliffPatch.OUT))<80;
    }
}
