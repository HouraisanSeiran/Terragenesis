package com.remotemountains.vdm;

import java.nio.*;
import java.nio.file.*;
import java.io.IOException;

/** Reads the direct XYZ diffusion export without converting height into lateral displacement. */
public final class VdmFile {
    public static VectorDisplacementMap read(Path path)throws IOException{
        long length=Files.size(path);
        if(length<28||length>256L*1024*1024)throw new IllegalArgumentException("Invalid VDM file size");
        ByteBuffer b=ByteBuffer.wrap(Files.readAllBytes(path)).order(ByteOrder.LITTLE_ENDIAN);
        if(b.get()!='V'||b.get()!='D'||b.get()!='M'||b.get()!='1')throw new IllegalArgumentException("Invalid VDM magic");
        int width=b.getInt(),height=b.getInt();float ox=b.getFloat(),oz=b.getFloat(),spacing=b.getFloat(),reference=b.getFloat();
        if(width!=height||width<2||length!=28+12L*width*height||reference!=72||!Float.isFinite(ox)||!Float.isFinite(oz)
            ||ox!=Math.rint(ox)||oz!=Math.rint(oz)||Math.abs(ox)>30000000||Math.abs(oz)>30000000
            ||!Float.isFinite(spacing)||spacing<1||spacing>16||spacing!=Math.rint(spacing))throw new IllegalArgumentException("Unsupported VDM coordinates");
        Displacement[] vectors=new Displacement[width*height];
        for(int i=0;i<vectors.length;i++)vectors[i]=new Displacement(b.getFloat(),b.getFloat(),b.getFloat());
        return new VectorDisplacementMap((int)ox,(int)oz,width,(int)spacing,vectors);
    }
}
