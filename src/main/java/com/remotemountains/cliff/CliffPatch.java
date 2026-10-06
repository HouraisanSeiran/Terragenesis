package com.remotemountains.cliff;

import com.remotemountains.vdm.Displacement;

/** One connected surface chart, including unchanged collar vertices and runoff boundaries. */
public final class CliffPatch {
    public final int columns=161,rows=81,size=columns*rows;
    public final CliffSettings settings;
    public static final Vec3 OUT=new Vec3(1,0,.35).normalized();
    public static final Vec3 ALONG=new Vec3(OUT.z(),0,-OUT.x());
    final Vec3[] reference=new Vec3[size],skeleton=new Vec3[size],axis=new Vec3[size];
    final Vec3[] positions=new Vec3[size],normals=new Vec3[size];
    final double[] areas=new double[size],rock=new double[size],hardness=new double[size];
    final double[] joint=new double[size],retreat=new double[size],mask=new double[size],exposure=new double[size];
    public CliffPatch(CliffSettings settings){this.settings=settings;}
    public int index(int u,int v){return v*columns+u;}
    public double u(int column){return -CliffSettings.HALF_LENGTH+column*CliffSettings.SPACING;}
    public double v(int row){return -CliffSettings.HALF_DEPTH+row*CliffSettings.SPACING;}
    public Vec3 position(int i){return positions[i];}
    public Vec3 normal(int i){return normals[i];}
    public double erodedDepth(int i){return retreat[i];}
    public double runoff(int i){return exposure[i];}
    public double resistance(int i){return hardness[i];}
    public double area(int i){return areas[i];}
    public boolean boundary(int i){int u=i%columns,v=i/columns;return u==0||u==columns-1||v==0||v==rows-1;}
    public void refresh(){
        for(int i=0;i<size;i++)positions[i]=skeleton[i].add(axis[i].scale(rock[i]-retreat[i]));
        refreshGeometry();
    }
    void refreshGeometry(){
        for(int v=0;v<rows;v++)for(int u=0;u<columns;u++){
            int i=index(u,v),ul=Math.max(0,u-1),ur=Math.min(columns-1,u+1),vl=Math.max(0,v-1),vr=Math.min(rows-1,v+1);
            Vec3 du=positions[index(ur,v)].subtract(positions[index(ul,v)]).scale(1./(ur-ul));
            Vec3 dv=positions[index(u,vr)].subtract(positions[index(u,vl)]).scale(1./(vr-vl));
            Vec3 cross=dv.cross(du);normals[i]=cross.normalized();
            areas[i]=Math.max(.05,cross.length())*(u==0||u==columns-1?.5:1)*(v==0||v==rows-1?.5:1);
        }
    }
    /** Interpolate displacement, preserving the caller's independently sampled diffusion base. */
    public Displacement delta(double worldX,double worldZ){
        Vec3 offset=new Vec3(worldX-CliffSettings.CENTER_X,0,worldZ-CliffSettings.CENTER_Z);
        double gu=(offset.dot(ALONG)+CliffSettings.HALF_LENGTH)/CliffSettings.SPACING;
        double gv=(offset.dot(OUT)+CliffSettings.HALF_DEPTH)/CliffSettings.SPACING;
        if(gu<=0||gv<=0||gu>=columns-1||gv>=rows-1)return new Displacement(0,0,0);
        int u=(int)gu,v=(int)gv;double fu=gu-u,fv=gv-v;
        Vec3 a=delta(index(u,v)),b=delta(index(u+1,v)),c=delta(index(u,v+1)),d=delta(index(u+1,v+1));
        Vec3 r=a.scale((1-fu)*(1-fv)).add(b.scale(fu*(1-fv))).add(c.scale((1-fu)*fv)).add(d.scale(fu*fv));
        return new Displacement(r.x(),r.y(),r.z());
    }
    private Vec3 delta(int i){return positions[i].subtract(reference[i]);}
}
