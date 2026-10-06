package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Landform;
import com.remotemountains.core.Landscape;
import com.remotemountains.core.Terrain;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.SurfaceModifier;
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;

/** Immutable finite local-coordinate terrain and VDM displacement export. */
public final class PreparedArtifact {
    private static final int HEIGHT_MAGIC = 0x524D4831; // RMH1
    private static final int VDM_MAGIC = 0x524D5031; // RMP1
    private static final int VERSION = 2;
    private static final int MAX_CELLS = 16_000_000;
    private static final String HEIGHT_FILE = "height-water.rmh";
    private static final String VDM_FILE = "vdm-patches.rmp";
    private static final String MANIFEST_FILE = "terrain.properties";
    private final int x0, z0, width, depth, step, patchStep, patchWidth, patchDepth;
    private final long seed;
    private final String sourceIdentity, identity;
    private final float[] elevation, water, temperature, rain, landmark;
    private final byte[] landform;
    private final float[] dx, dy, dz;

    private PreparedArtifact(int x0, int z0, int width, int depth, int step,
            int patchStep, int patchWidth, int patchDepth, long seed, String sourceIdentity,
            String identity, float[] elevation, float[] water, float[] temperature,
            float[] rain, float[] landmark, byte[] landform, float[] dx, float[] dy, float[] dz) {
        this.x0=x0; this.z0=z0; this.width=width; this.depth=depth; this.step=step;
        this.patchStep=patchStep; this.patchWidth=patchWidth; this.patchDepth=patchDepth;
        this.seed=seed; this.sourceIdentity=sourceIdentity; this.identity=identity;
        this.elevation=elevation; this.water=water; this.temperature=temperature; this.rain=rain;
        this.landmark=landmark; this.landform=landform; this.dx=dx; this.dy=dy; this.dz=dz;
    }

    public String identity(){return identity;}
    public String sourceIdentity(){return sourceIdentity;}
    public long seed(){return seed;}
    public int minX(){return x0;}
    public int minZ(){return z0;}
    public int maxX(){return x0+(width-1)*step;}
    public int maxZ(){return z0+(depth-1)*step;}
    public PreparedTerrainSource terrain(){return new PreparedTerrainSource(this);}
    public PreparedSurfaceModifier modifier(){return new PreparedSurfaceModifier(this);}

    public static PreparedArtifact read(Path directory, long expectedSeed, String expectedIdentity) throws IOException {
        Path manifest=directory.resolve(MANIFEST_FILE);
        Map<String,String> meta=new TreeMap<>();
        for(String line:Files.readAllLines(manifest)) {
            if(line.isBlank()||line.startsWith("#"))continue;
            int equals=line.indexOf('=');
            if(equals<1||meta.putIfAbsent(line.substring(0,equals),line.substring(equals+1))!=null)
                throw new IOException("Invalid prepared terrain manifest");
        }
        if(!"2".equals(meta.get("version"))||!"local-blocks".equals(meta.get("coordinates"))
                ||!"72".equals(meta.get("reference_y"))||!"1".equals(meta.get("world_scale")))
            throw new IOException("Unsupported prepared terrain coordinate contract");
        long seed=parseLong(meta,"seed");
        if(seed!=expectedSeed)throw new IOException("Prepared terrain seed mismatch: "+seed+" != "+expectedSeed);
        String sourceIdentity=required(meta,"source_identity");
        Path heightPath=directory.resolve(HEIGHT_FILE),vdmPath=directory.resolve(VDM_FILE);
        String heightHash=sha256(heightPath),vdmHash=sha256(vdmPath);
        if(!heightHash.equals(required(meta,"height_sha256"))||!vdmHash.equals(required(meta,"vdm_sha256")))
            throw new IOException("Prepared terrain checksum mismatch");
        String identity="prepared-v1:"+sourceIdentity+":"+heightHash+":"+vdmHash;
        if(expectedIdentity!=null&&!expectedIdentity.isEmpty()&&!expectedIdentity.equals(identity))
            throw new IOException("Saved world prepared terrain differs from installed artifact");
        int x0=parseInt(meta,"origin_x"),z0=parseInt(meta,"origin_z");
        int width=parseInt(meta,"width"),depth=parseInt(meta,"depth"),step=parseInt(meta,"step");
        int patchStep=parseInt(meta,"patch_step");
        checkGrid(width,depth,step);
        if(patchStep<step||(width-1)*step%patchStep!=0||(depth-1)*step%patchStep!=0)
            throw new IOException("VDM patch grid does not align with height grid");
        int patchWidth=(width-1)*step/patchStep+1,patchDepth=(depth-1)*step/patchStep+1;
        checkGrid(patchWidth,patchDepth,patchStep);
        int n=width*depth,m=patchWidth*patchDepth;
        float[] height=new float[n],water=new float[n],temp=new float[n],rain=new float[n],landmark=new float[n];
        byte[] landform=new byte[n];float[] dx=new float[m],dy=new float[m],dz=new float[m];
        try(DataInputStream in=new DataInputStream(new BufferedInputStream(Files.newInputStream(heightPath)))) {
            checkHeader(in,HEIGHT_MAGIC,x0,z0,width,depth,step,seed,sourceIdentity);
            for(int i=0;i<n;i++){
                height[i]=in.readFloat();water[i]=in.readFloat();temp[i]=in.readFloat();
                rain[i]=in.readFloat();landmark[i]=in.readFloat();landform[i]=in.readByte();
                checkSample(height[i],water[i],temp[i],rain[i],landmark[i],landform[i]);
                if(onEdge(i,width,depth)&&(height[i]!=48||water[i]!=72))
                    throw new IOException("Prepared terrain edge must match outer ocean");
            }
            if(in.read()!=-1)throw new IOException("Trailing height data");
        }
        try(DataInputStream in=new DataInputStream(new BufferedInputStream(Files.newInputStream(vdmPath)))) {
            checkHeader(in,VDM_MAGIC,x0,z0,patchWidth,patchDepth,patchStep,seed,sourceIdentity);
            for(int i=0;i<m;i++){
                dx[i]=in.readFloat();dy[i]=in.readFloat();dz[i]=in.readFloat();
                if(!Float.isFinite(dx[i])||!Float.isFinite(dy[i])||!Float.isFinite(dz[i]))
                    throw new IOException("Non-finite VDM patch");
                if(onEdge(i,patchWidth,patchDepth)&&(dx[i]!=0||dy[i]!=0||dz[i]!=0))
                    throw new IOException("VDM patch crosses artifact boundary");
            }
            if(in.read()!=-1)throw new IOException("Trailing VDM data");
        }
        return new PreparedArtifact(x0,z0,width,depth,step,patchStep,patchWidth,patchDepth,
            seed,sourceIdentity,identity,height,water,temp,rain,landmark,landform,dx,dy,dz);
    }

    /** Export both stages once; modifier may run expensive erosion here, never during import. */
    public static PreparedArtifact export(Path directory, BaseTerrainSource source, SurfaceModifier modifier,
            long seed, int x0, int z0, int width, int depth, int step, int patchStep) throws IOException {
        if(source==null||modifier==null||source.identity().isEmpty()||source.identity().length()>1000
                ||source.identity().contains("\n")||source.identity().contains("\r"))
            throw new IllegalArgumentException("Invalid prepared source or modifier");
        checkGrid(width,depth,step);
        if(patchStep<step||(width-1)*step%patchStep!=0||(depth-1)*step%patchStep!=0)
            throw new IllegalArgumentException("VDM grid must align with height grid");
        int patchWidth=(width-1)*step/patchStep+1,patchDepth=(depth-1)*step/patchStep+1;
        checkGrid(patchWidth,patchDepth,patchStep);
        Files.createDirectories(directory);
        try(DataOutputStream out=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(directory.resolve(HEIGHT_FILE))))) {
            writeHeader(out,HEIGHT_MAGIC,x0,z0,width,depth,step,seed,source.identity());
            for(int z=0;z<depth;z++)for(int x=0;x<width;x++){
                Terrain.Column c=source.sample(x0+(double)x*step,z0+(double)z*step);
                Landscape.Base base=c.base();
                float h=(float)c.height(),w=(float)c.water();
                float temp=(float)base.climate().temperature(),rain=(float)base.climate().rain();
                float landmark=(float)base.landmark();byte type=(byte)base.type().ordinal();
                checkSample(h,w,temp,rain,landmark,type);
                if(onEdge(z*width+x,width,depth)&&(h!=48||w!=72))
                    throw new IOException("Export extent cuts through land or a river bank at "+(x0+x*step)+","+(z0+z*step));
                out.writeFloat(h);out.writeFloat(w);out.writeFloat(temp);out.writeFloat(rain);
                out.writeFloat(landmark);out.writeByte(type);
            }
        }
        try(DataOutputStream out=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(directory.resolve(VDM_FILE))))) {
            writeHeader(out,VDM_MAGIC,x0,z0,patchWidth,patchDepth,patchStep,seed,source.identity());
            for(int z=0;z<patchDepth;z++)for(int x=0;x<patchWidth;x++){
                int px=x0+x*patchStep,pz=z0+z*patchStep;
                Terrain.Column baseColumn=source.sample(px,pz);
                Displacement initial=new Displacement(0,baseColumn.height()-72,0);
                Displacement edited=modifier.apply(px,pz,initial);
                float dx=(float)(edited.dx()-initial.dx());
                float dy=(float)(edited.dy()-initial.dy());
                float dz=(float)(edited.dz()-initial.dz());
                if(!Float.isFinite(dx)||!Float.isFinite(dy)||!Float.isFinite(dz))
                    throw new IOException("Non-finite VDM patch at "+px+","+pz);
                if(Double.isFinite(baseColumn.water())
                        &&edited.dy()+72>baseColumn.water()+0.001)
                    throw new IOException("VDM patch raises wet bed above water at "+px+","+pz);
                if(onEdge(z*patchWidth+x,patchWidth,patchDepth)&&(dx!=0||dy!=0||dz!=0))
                    throw new IOException("VDM patch crosses artifact boundary at "+px+","+pz);
                out.writeFloat(dx);out.writeFloat(dy);out.writeFloat(dz);
            }
        }
        Map<String,String> meta=new TreeMap<>();
        meta.put("version",Integer.toString(VERSION));meta.put("coordinates","local-blocks");
        meta.put("reference_y","72");meta.put("world_scale","1");
        meta.put("seed",Long.toString(seed));meta.put("source_identity",source.identity());
        meta.put("origin_x",Integer.toString(x0));meta.put("origin_z",Integer.toString(z0));
        meta.put("width",Integer.toString(width));meta.put("depth",Integer.toString(depth));
        meta.put("step",Integer.toString(step));meta.put("patch_step",Integer.toString(patchStep));
        meta.put("height_sha256",sha256(directory.resolve(HEIGHT_FILE)));
        meta.put("vdm_sha256",sha256(directory.resolve(VDM_FILE)));
        StringBuilder lines=new StringBuilder();
        for(var entry:meta.entrySet())lines.append(entry.getKey()).append('=').append(entry.getValue()).append('\n');
        Files.writeString(directory.resolve(MANIFEST_FILE),lines.toString());
        return read(directory,seed,"");
    }

    Terrain.Column sample(double x,double z){
        if(x<x0||z<z0||x>maxX()||z>maxZ()){
            Landscape.Base base=new Landscape.Base(48,Landform.KARST,new Landscape.Climate(.5,.5),0);
            return new Terrain.Column(48,72,base);
        }
        double gx=(x-x0)/step,gz=(z-z0)/step;
        float h=interpolate(elevation,width,depth,gx,gz);
        int index=Math.min(depth-1,(int)Math.round(gz))*width+Math.min(width-1,(int)Math.round(gx));
        float w=interpolateWater(gx,gz,h);
        Landscape.Base base=new Landscape.Base(h,Landform.values()[landform[index]],
            new Landscape.Climate(interpolate(temperature,width,depth,gx,gz),
                interpolate(rain,width,depth,gx,gz)),interpolate(landmark,width,depth,gx,gz));
        return new Terrain.Column(h,w,base);
    }

    Displacement apply(double x,double z,Displacement initial){
        if(x<x0||z<z0||x>maxX()||z>maxZ())return initial;
        double gx=(x-x0)/patchStep,gz=(z-z0)/patchStep;
        return new Displacement(initial.dx()+interpolate(dx,patchWidth,patchDepth,gx,gz),
            initial.dy()+interpolate(dy,patchWidth,patchDepth,gx,gz),
            initial.dz()+interpolate(dz,patchWidth,patchDepth,gx,gz));
    }

    private static float interpolate(float[] values,int width,int depth,double x,double z){
        int ix=Math.min(width-2,(int)x),iz=Math.min(depth-2,(int)z);
        double fx=x-ix,fz=z-iz;
        double a=values[iz*width+ix]*(1-fx)+values[iz*width+ix+1]*fx;
        double b=values[(iz+1)*width+ix]*(1-fx)+values[(iz+1)*width+ix+1]*fx;
        return (float)(a*(1-fz)+b*fz);
    }
    private float interpolateWater(double x,double z,float height){
        int ix=Math.min(width-2,(int)x),iz=Math.min(depth-2,(int)z);
        double fx=x-ix,fz=z-iz;
        int[] corners={iz*width+ix,iz*width+ix+1,(iz+1)*width+ix,(iz+1)*width+ix+1};
        double[] weight={(1-fx)*(1-fz),fx*(1-fz),(1-fx)*fz,fx*fz};
        double wetWeight=0,level=0;
        boolean allWet=true;
        for(int i=0;i<4;i++){
            float w=water[corners[i]];
            if(Float.isNaN(w)){allWet=false;continue;}
            wetWeight+=weight[i];level+=weight[i]*w;
        }
        if(wetWeight==0)return Float.NaN;
        float w=(float)(level/wetWeight);
        if(allWet&&height>w+0.001f)
            throw new IllegalStateException("Prepared wet cell has exposed interpolated bed");
        return height<=w+0.001f?w:Float.NaN;
    }
    private static void checkGrid(int width,int depth,int step){
        if(width<2||depth<2||step<1||step>16||(long)width*depth>MAX_CELLS
                ||(long)(width-1)*step>Integer.MAX_VALUE
                ||(long)(depth-1)*step>Integer.MAX_VALUE)
            throw new IllegalArgumentException("Invalid prepared terrain grid");
    }
    private static boolean onEdge(int i,int width,int depth){
        int x=i%width,z=i/width;return x==0||z==0||x==width-1||z==depth-1;
    }
    private static void checkSample(float h,float w,float temp,float rain,float landmark,byte type)throws IOException{
        if(!Float.isFinite(h)||(!Float.isNaN(w)&&(!Float.isFinite(w)||h>w))
                ||!Float.isFinite(temp)||!Float.isFinite(rain)||!Float.isFinite(landmark)
                ||type<0||type>=Landform.values().length)
            throw new IOException("Invalid prepared height/water sample");
    }
    private static void writeHeader(DataOutputStream out,int magic,int x,int z,int width,int depth,int step,
            long seed,String sourceIdentity)throws IOException{
        out.writeInt(magic);out.writeInt(VERSION);out.writeInt(x);out.writeInt(z);
        out.writeInt(width);out.writeInt(depth);out.writeInt(step);
        out.writeLong(seed);out.writeUTF(sourceIdentity);
    }
    private static void checkHeader(DataInputStream in,int magic,int x,int z,int width,int depth,int step,
            long seed,String sourceIdentity)throws IOException{
        if(in.readInt()!=magic||in.readInt()!=VERSION||in.readInt()!=x||in.readInt()!=z
                ||in.readInt()!=width||in.readInt()!=depth||in.readInt()!=step
                ||in.readLong()!=seed||!in.readUTF().equals(sourceIdentity))
            throw new IOException("Prepared terrain binary header mismatch");
    }
    private static String required(Map<String,String> meta,String key)throws IOException{
        String value=meta.get(key);if(value==null||value.isEmpty())throw new IOException("Missing "+key);
        return value;
    }
    private static int parseInt(Map<String,String> meta,String key)throws IOException{
        try{return Integer.parseInt(required(meta,key));}catch(NumberFormatException e){throw new IOException("Invalid "+key,e);}
    }
    private static long parseLong(Map<String,String> meta,String key)throws IOException{
        try{return Long.parseLong(required(meta,key));}catch(NumberFormatException e){throw new IOException("Invalid "+key,e);}
    }
    private static String sha256(Path path)throws IOException{
        try{
            MessageDigest digest=MessageDigest.getInstance("SHA-256");
            try(var in=Files.newInputStream(path)){
                byte[] block=new byte[65536];int n;
                while((n=in.read(block))!=-1)digest.update(block,0,n);
            }
            return HexFormat.of().formatHex(digest.digest());
        }catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}
    }
}
