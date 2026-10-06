package com.remotemountains.vdm;

/** A sampled three-channel map on the reference plane (x,72,z), not a height map. */
public final class VectorDisplacementMap {
    public record Vertex(double x,double y,double z) {}
    private final int originX,originZ,size,spacing;
    private final Displacement[] vectors;
    private int worldScale=1;
    public VectorDisplacementMap(int originX,int originZ,int size,int spacing,Displacement[] vectors){
        if(size<2||spacing<1||vectors.length!=size*size)throw new IllegalArgumentException("Invalid VDM grid");
        this.originX=originX;this.originZ=originZ;this.size=size;this.spacing=spacing;this.vectors=vectors.clone();
        for(var v:this.vectors)if(v==null)throw new IllegalArgumentException("Missing displacement");
    }
    public int size(){return size;}
    public int originX(){return originX;}
    public int originZ(){return originZ;}
    public int spacing(){return spacing;}
    public int worldScale(){return worldScale;}
    public VectorDisplacementMap scaled(int factor){
        if(factor<1)throw new IllegalArgumentException("Invalid world scale");
        var result=new VectorDisplacementMap(originX,originZ,size,spacing,vectors);
        result.worldScale=factor;return result;
    }
    public boolean covers(double x,double z){
        // A margin avoids requiring the mesh to cover blocks exactly on its outermost edge.
        x/=worldScale;z/=worldScale;
        return x>=originX+spacing&&z>=originZ+spacing&&x<originX+(size-2)*spacing&&z<originZ+(size-2)*spacing;
    }
    public Displacement vector(int x,int z){return vectors[z*size+x];}
    public Vertex vertex(int x,int z){
        var d=vector(x,z);
        double height=72+d.dy();
        double sea=worldScale==1?72:62;
        return new Vertex((originX+x*spacing+d.dx())*worldScale,sea+d.dy()*(height<=72?1:worldScale),(originZ+z*spacing+d.dz())*worldScale);
    }
}
