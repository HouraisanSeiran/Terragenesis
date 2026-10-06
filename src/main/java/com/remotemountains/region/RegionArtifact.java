package com.remotemountains.region;

import com.remotemountains.core.*;
import com.remotemountains.vdm.*;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** One immutable region package: source fields and the processed XYZ surface mesh. */
public final class RegionArtifact {
    private static final int MAGIC=0x524D5231, VERSION=1;
    public static final String ALGORITHM="region_xyz_v1:"+RegionLandformLayout.VERSION;
    private final int rx,rz,side;
    private final RegionConfig config;
    private final double[] height,water,temperature,rain,landmark;
    private final byte[] landform;
    private final VectorDisplacementMap mesh;
    private final String identity;

    private RegionArtifact(int rx,int rz,RegionConfig config,double[] height,double[] water,
            double[] temperature,double[] rain,double[] landmark,byte[] landform,
            VectorDisplacementMap mesh,String identity){
        this.rx=rx;this.rz=rz;this.config=config;this.side=config.localWidth()+1;
        this.height=height;this.water=water;this.temperature=temperature;this.rain=rain;
        this.landmark=landmark;this.landform=landform;this.mesh=mesh;this.identity=identity;
    }
    public String identity(){return identity;}
    public VectorDisplacementMap mesh(){return mesh;}
    public static Path path(Path directory,int rx,int rz){return directory.resolve("r."+rx+"."+rz+".rmr");}
    public static RegionArtifact prepare(Path directory,long seed,String sourceId,String recipe,
            RegionConfig config,int rx,int rz,BaseTerrainSource base,SurfaceModifier modifier)throws IOException{
        Objects.requireNonNull(base);Objects.requireNonNull(modifier);
        if(!sourceId.equals(base.identity()))throw new IOException("Region source identity changed");
        int width=config.localWidth(),side=width+1,n=side*side;
        int ox=Math.multiplyExact(rx,width),oz=Math.multiplyExact(rz,width);
        RegionLandformLayout layout=new RegionLandformLayout(seed);
        double[] h=new double[n],w=new double[n],t=new double[n],r=new double[n],l=new double[n];
        byte[] type=new byte[n];
        for(int z=0;z<side;z++)for(int x=0;x<side;x++){
            Terrain.Column c=base.sample(ox+x,oz+z);int i=z*side+x;
            h[i]=c.height();w[i]=c.water();t[i]=c.base().climate().temperature();
            r[i]=c.base().climate().rain();l[i]=c.base().landmark();
            type[i]=(byte)layout.at((ox+x)*3.0,(oz+z)*3.0).primary().ordinal();
            checkColumn(h[i],w[i],t[i],r[i],l[i],type[i]);
        }
        VectorDisplacementMap map=new VdmBuilder(base,modifier,RegionConfig.SPACING,RegionConfig.HALO).build(ox,oz,width);
        int m=map.size();
        for(int z=0;z<m;z++)for(int x=0;x<m;x++){
            Displacement d=map.vector(x,z);
            if(Math.abs(d.dx())>RegionConfig.HALO-RegionConfig.SPACING||Math.abs(d.dz())>RegionConfig.HALO-RegionConfig.SPACING)
                throw new IOException("VDM motion exceeds region halo");
        }
        Path target=path(directory,rx,rz);Files.createDirectories(directory);
        Path temp=Files.createTempFile(directory,"region-",".tmp");
        try{
            try(DataOutputStream out=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(temp)))){
                out.writeInt(MAGIC);out.writeInt(VERSION);out.writeUTF(ALGORITHM);out.writeLong(seed);out.writeUTF(sourceId);
                out.writeUTF(recipe);out.writeInt(config.chunks());out.writeUTF(config.processing());
                out.writeInt(rx);out.writeInt(rz);out.writeInt(side);out.writeInt(m);
                for(int i=0;i<n;i++){
                    out.writeDouble(h[i]);out.writeDouble(w[i]);out.writeDouble(t[i]);out.writeDouble(r[i]);
                    out.writeDouble(l[i]);out.writeByte(type[i]);
                }
                for(int z=0;z<m;z++)for(int x=0;x<m;x++){
                    Displacement d=map.vector(x,z);out.writeDouble(d.dx());out.writeDouble(d.dy());out.writeDouble(d.dz());
                }
            }
            byte[] payload=Files.readAllBytes(temp);
            try(DataOutputStream out=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(temp,StandardOpenOption.APPEND)))){
                out.write(MessageDigest.getInstance("SHA-256").digest(payload));
            }catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}
            Files.move(temp,target,StandardCopyOption.ATOMIC_MOVE);
        }finally{Files.deleteIfExists(temp);}
        return read(directory,seed,sourceId,recipe,config,rx,rz);
    }
    public static RegionArtifact read(Path directory,long seed,String sourceId,String recipe,
            RegionConfig config,int rx,int rz)throws IOException{
        Path target=path(directory,rx,rz);long length=Files.size(target);
        int side=config.localWidth()+1,m=config.gridSize();
        long expected=4+4+2+ALGORITHM.length()+8+2+sourceId.getBytes(java.nio.charset.StandardCharsets.UTF_8).length
            +2+recipe.getBytes(java.nio.charset.StandardCharsets.UTF_8).length+4
            +2+config.processing().length()+16+41L*side*side+24L*m*m+32;
        if(length<64||length>expected+64||length>64L*1024*1024)
            throw new IOException("Invalid region package size");
        byte[] bytes=Files.readAllBytes(target),payload=Arrays.copyOf(bytes,bytes.length-32);
        try{
            byte[] actual=MessageDigest.getInstance("SHA-256").digest(payload);
            if(!MessageDigest.isEqual(actual,Arrays.copyOfRange(bytes,payload.length,bytes.length)))
                throw new IOException("Region package checksum mismatch");
        }catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}
        try(DataInputStream in=new DataInputStream(new ByteArrayInputStream(payload))){
            if(in.readInt()!=MAGIC||in.readInt()!=VERSION||!in.readUTF().equals(ALGORITHM)||in.readLong()!=seed
                    ||!in.readUTF().equals(sourceId)||!in.readUTF().equals(recipe)
                    ||in.readInt()!=config.chunks()||!in.readUTF().equals(config.processing())
                    ||in.readInt()!=rx||in.readInt()!=rz||in.readInt()!=side||in.readInt()!=m)
                throw new IOException("Region package identity or layout mismatch");
            int n=side*side;double[] h=new double[n],w=new double[n],t=new double[n],r=new double[n],l=new double[n];
            byte[] type=new byte[n];
            for(int i=0;i<n;i++){
                h[i]=in.readDouble();w[i]=in.readDouble();t[i]=in.readDouble();r[i]=in.readDouble();
                l[i]=in.readDouble();type[i]=in.readByte();checkColumn(h[i],w[i],t[i],r[i],l[i],type[i]);
            }
            Displacement[] vectors=new Displacement[m*m];
            for(int i=0;i<vectors.length;i++){
                vectors[i]=new Displacement(in.readDouble(),in.readDouble(),in.readDouble());
                if(Math.abs(vectors[i].dx())>RegionConfig.HALO-RegionConfig.SPACING
                        ||Math.abs(vectors[i].dz())>RegionConfig.HALO-RegionConfig.SPACING)
                    throw new IOException("Region VDM motion exceeds halo");
            }
            if(in.read()!=-1)throw new IOException("Trailing region package data");
            int ox=Math.multiplyExact(rx,config.localWidth())-RegionConfig.HALO;
            int oz=Math.multiplyExact(rz,config.localWidth())-RegionConfig.HALO;
            return new RegionArtifact(rx,rz,config,h,w,t,r,l,type,
                new VectorDisplacementMap(ox,oz,m,RegionConfig.SPACING,vectors),HexFormat.of().formatHex(Arrays.copyOfRange(bytes,payload.length,bytes.length)));
        }catch(IllegalArgumentException e){throw new IOException("Invalid region package sample",e);}
    }
    private static void checkColumn(double h,double w,double t,double r,double l,byte type)throws IOException{
        if(!Double.isFinite(h)||!(Double.isNaN(w)||Double.isFinite(w))
                ||!Double.isFinite(t)||!Double.isFinite(r)||!Double.isFinite(l)
                ||type<0||type>=Landform.values().length)throw new IOException("Invalid region base sample");
    }
    public Terrain.Column sampleBase(double localX,double localZ){
        double gx=localX-rx*(double)config.localWidth(),gz=localZ-rz*(double)config.localWidth();
        if(gx<0||gz<0||gx>config.localWidth()||gz>config.localWidth())throw new IllegalArgumentException("Outside region");
        int ix=Math.min(side-2,(int)Math.floor(gx)),iz=Math.min(side-2,(int)Math.floor(gz));
        double fx=gx-ix,fz=gz-iz;
        double elevation=interp(height,ix,iz,fx,fz);
        double level=interpWater(ix,iz,fx,fz,elevation);
        int nearest=Math.min(side-1,(int)Math.round(gz))*side+Math.min(side-1,(int)Math.round(gx));
        var base=new Landscape.Base(elevation,Landform.values()[landform[nearest]],
            new Landscape.Climate(interp(temperature,ix,iz,fx,fz),interp(rain,ix,iz,fx,fz)),
            interp(landmark,ix,iz,fx,fz));
        return new Terrain.Column(elevation,level,base);
    }
    private double interp(double[] a,int x,int z,double fx,double fz){
        int i=z*side+x;return (a[i]*(1-fx)+a[i+1]*fx)*(1-fz)
            +(a[i+side]*(1-fx)+a[i+side+1]*fx)*fz;
    }
    private double interpWater(int x,int z,double fx,double fz,double elevation){
        int i=z*side+x;int[] at={i,i+1,i+side,i+side+1};
        double[] weight={(1-fx)*(1-fz),fx*(1-fz),(1-fx)*fz,fx*fz};
        double total=0,level=0;
        for(int j=0;j<4;j++)if(Double.isFinite(water[at[j]])){
            total+=weight[j];level+=weight[j]*water[at[j]];
        }
        if(total==0)return Double.NaN;
        level/=total;return elevation<=level+0.001?level:Double.NaN;
    }
}
