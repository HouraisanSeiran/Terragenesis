package com.remotemountains.diffusion;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Validated native model samples. Interpolation changes spacing, never claims new detail. */
public record DiffusionTile(int size,int blocksPerPixel,int seaLevel,float verticalScale,float[] values) {
    public record Sample(double meters,double temperature,double precipitation) {}
    public static DiffusionTile decode(byte[] bytes){
        if(bytes.length!=24+65*65*3*4)throw new IllegalArgumentException("Unexpected diffusion tile length");
        ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
        if(b.get()!= 'R'||b.get()!='M'||b.get()!='D'||b.get()!='2')throw new IllegalArgumentException("Invalid diffusion protocol");
        int size=b.getInt(),spacing=b.getInt(),sea=b.getInt(),reserved=b.getInt();float vertical=b.getFloat();
        if(size!=65||spacing<1||spacing>16||sea!=72||reserved!=0||!Float.isFinite(vertical)||vertical<1||vertical>1000)
            throw new IllegalArgumentException("Unsupported diffusion grid configuration");
        float[] data=new float[size*size*3];
        for(int i=0;i<data.length;i++){data[i]=b.getFloat();if(!Float.isFinite(data[i]))throw new IllegalArgumentException("Non-finite diffusion sample");}
        return new DiffusionTile(size,spacing,sea,vertical,data);
    }
    public Sample sample(double x,double z){
        if(!Double.isFinite(x)||!Double.isFinite(z)||x<0||z<0||x>64||z>64)throw new IllegalArgumentException("Outside tile");
        int ix=Math.min(63,(int)x),iz=Math.min(63,(int)z);double fx=x-ix,fz=z-iz;
        return new Sample(interpolate(ix,iz,fx,fz,0),interpolate(ix,iz,fx,fz,1),interpolate(ix,iz,fx,fz,2));
    }
    private double interpolate(int x,int z,double fx,double fz,int channel){
        double a=values[(z*size+x)*3+channel],b=values[(z*size+x+1)*3+channel];
        double c=values[((z+1)*size+x)*3+channel],d=values[((z+1)*size+x+1)*3+channel];
        return (a+(b-a)*fx)*(1-fz)+(c+(d-c)*fx)*fz;
    }
}
