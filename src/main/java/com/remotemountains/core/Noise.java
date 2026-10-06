package com.remotemountains.core;

/** Unbounded, coordinate-hashed gradient Perlin noise (no 256-cell permutation repeat). */
public final class Noise {
    private final long seed;
    public Noise(long seed) { this.seed = seed; }
    public static long hash(long seed, int x, int z) {
        return mix(seed ^ (long)x * 0x9E3779B97F4A7C15L ^ (long)z * 0xC2B2AE3D27D4EB4FL);
    }
    public static long mix(long v) {
        v = (v ^ v >>> 30) * 0xBF58476D1CE4E5B9L;
        v = (v ^ v >>> 27) * 0x94D049BB133111EBL;
        return v ^ v >>> 31;
    }
    public static double unit(long v) { return (mix(v) >>> 11) * 0x1.0p-53; }
    public static double clamp(double v, double a, double b) { return Math.max(a, Math.min(b, v)); }
    public static double smooth(double a, double b, double v) { double t=clamp((v-a)/(b-a),0,1); return t*t*(3-2*t); }
    public static double lerp(double a, double b, double t) { return a+(b-a)*t; }
    private static double fade(double t) { return t*t*t*(t*(t*6-15)+10); }
    private double gradient(int x,int y,int z,double dx,double dy,double dz) {
        int h=(int)(mix(hash(seed,x,z) ^ (long)y*0x165667B19E3779F9L)&15);
        double u=h<8?dx:dy, v=h<4?dy:(h==12||h==14?dx:dz);
        return ((h&1)==0?u:-u)+((h&2)==0?v:-v);
    }
    public double at(double x,double z) { return at(x,0.371,z); }
    public double at(double x,double y,double z) {
        int ix=(int)Math.floor(x), iy=(int)Math.floor(y), iz=(int)Math.floor(z);
        double dx=x-ix,dy=y-iy,dz=z-iz,u=fade(dx),v=fade(dy),w=fade(dz);
        return lerp(lerp(lerp(gradient(ix,iy,iz,dx,dy,dz),gradient(ix+1,iy,iz,dx-1,dy,dz),u),
                        lerp(gradient(ix,iy+1,iz,dx,dy-1,dz),gradient(ix+1,iy+1,iz,dx-1,dy-1,dz),u),v),
                    lerp(lerp(gradient(ix,iy,iz+1,dx,dy,dz-1),gradient(ix+1,iy,iz+1,dx-1,dy,dz-1),u),
                        lerp(gradient(ix,iy+1,iz+1,dx,dy-1,dz-1),gradient(ix+1,iy+1,iz+1,dx-1,dy-1,dz-1),u),v),w);
    }
    public double fbm(double x,double z,int octaves) {
        double sum=0,weight=1,total=0;
        for(int i=0;i<octaves;i++){sum+=weight*at(x,z);total+=weight;x=x*2.03+11.7;z=z*2.03-9.3;weight*=0.5;}
        return sum/total;
    }
}
