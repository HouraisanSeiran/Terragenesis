package com.remotemountains.diffusion;

import com.remotemountains.core.*;
import java.io.*;
import java.nio.*;
import java.security.*;
import java.util.HexFormat;

/** First-playable demo: a real pretrained diffusion patch, with an explicit finite ocean collar. */
public final class BakedTerrainSource implements BaseTerrainSource {
    private final int size,spacing,origin;
    private final float[] samples;
    private final String identity;
    private final Regions regions;
    public BakedTerrainSource(long seed,String expectedIdentity){
        regions=new Regions(seed);
        try(InputStream in=BakedTerrainSource.class.getResourceAsStream("/assets/remotemountains/terrain/demo.rmb")){
            if(in==null)throw new IllegalStateException("Missing baked Terrain Diffusion sample; build the preview first");
            byte[] bytes=in.readAllBytes();identity="baked-"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            if(!expectedIdentity.isEmpty()&&!identity.equals(expectedIdentity))throw new IllegalStateException("Saved world's baked terrain differs from installed version");
            ByteBuffer b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
            if(b.getInt()!=0x31424d52)throw new IllegalStateException("Invalid baked terrain header");
            size=b.getInt();spacing=b.getInt();origin=b.getInt();
            if(size<3||size>2049||spacing<1||spacing>16||bytes.length!=16+size*size*12)throw new IllegalStateException("Invalid baked terrain dimensions");
            samples=new float[size*size*3];
            for(int i=0;i<samples.length;i++){samples[i]=b.getFloat();if(!Float.isFinite(samples[i]))throw new IllegalStateException("Invalid baked sample");}
        }catch(IOException|NoSuchAlgorithmException e){throw new IllegalStateException("Cannot read baked terrain",e);}
    }
    public String identity(){return identity;}
    public Terrain.Column sample(double x,double z){
        double gx=(x-origin)/spacing,gz=(z-origin)/spacing;
        double height=48,temp=18,rain=1000;
        if(gx>=0&&gz>=0&&gx<=size-1&&gz<=size-1){
            double meters=interpolate(gx,gz,0);
            double offset=meters/30;
            height=72+(offset>=0?225*Math.tanh(offset/225):125*Math.tanh(offset/125));
            temp=interpolate(gx,gz,1);rain=interpolate(gx,gz,2);
            // The demo is finite. Only the outer 64 blocks blend to an ocean floor.
            double edge=Math.min(Math.min(gx,gz),Math.min(size-1-gx,size-1-gz))*spacing;
            double weight=Math.max(0,Math.min(1,edge/64));weight=weight*weight*(3-2*weight);
            height=48+(height-48)*weight;
        }
        var climate=new Landscape.Climate(Noise.clamp((temp+12)/45,0,1),Noise.clamp(rain/2200,0,1));
        var info=new Landscape.Base(height,regions.at(x,z).primary().type(),climate,0);
        return new Terrain.Column(height,height<72?72:Double.NaN,info);
    }
    private double interpolate(double x,double z,int channel){
        int ix=Math.min(size-2,(int)x),iz=Math.min(size-2,(int)z);double fx=x-ix,fz=z-iz;
        double a=samples[(iz*size+ix)*3+channel],b=samples[(iz*size+ix+1)*3+channel];
        double c=samples[((iz+1)*size+ix)*3+channel],d=samples[((iz+1)*size+ix+1)*3+channel];
        return (a+(b-a)*fx)*(1-fz)+(c+(d-c)*fx)*fz;
    }
}
