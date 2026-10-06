package com.remotemountains.cliff;

import java.util.Arrays;

/** Approximate adhesion loss plus vertical ballistic recontact with the same surface patch. */
public final class WaterDetachment {
    private final int[] targets;
    public WaterDetachment(CliffPatch p){targets=new int[p.size];Arrays.fill(targets,-1);}
    public double fraction(CliffPatch p,int i){
        if(p.mask[i]<.01)return 0;
        return CliffSettings.clamp((-p.normals[i].y()-.27)*1.35,0,.65);
    }
    public int target(int i){return targets[i];}
    public void refresh(CliffPatch p){
        Arrays.fill(targets,-1);
        for(int i=0;i<p.size;i++){
            if(fraction(p,i)==0)continue;
            Vec3 origin=p.positions[i];double highest=-Double.MAX_VALUE;int col=i%p.columns,row=i/p.columns;
            for(int v=row+1;v<p.rows-1;v++)for(int u=Math.max(0,col-3);u<Math.min(p.columns-1,col+4);u++){
                int a=p.index(u,v),b=a+1,c=a+p.columns,d=c+1;
                double h=height(origin,p.positions[a],p.positions[b],p.positions[d]);
                if(h<origin.y()-.35&&h>highest){highest=h;targets[i]=a;}
                h=height(origin,p.positions[a],p.positions[d],p.positions[c]);
                if(h<origin.y()-.35&&h>highest){highest=h;targets[i]=c;}
            }
        }
    }
    private double height(Vec3 ray,Vec3 a,Vec3 b,Vec3 c){
        double det=(b.x()-a.x())*(c.z()-a.z())-(b.z()-a.z())*(c.x()-a.x());
        if(Math.abs(det)<1e-10)return -Double.MAX_VALUE;
        double u=((ray.x()-a.x())*(c.z()-a.z())-(ray.z()-a.z())*(c.x()-a.x()))/det;
        double v=((b.x()-a.x())*(ray.z()-a.z())-(b.z()-a.z())*(ray.x()-a.x()))/det;
        if(u<0||v<0||u+v>1)return -Double.MAX_VALUE;
        return a.y()+u*(b.y()-a.y())+v*(c.y()-a.y());
    }
}
