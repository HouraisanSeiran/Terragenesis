package com.remotemountains.vdm;

import java.util.*;
import com.remotemountains.vdm.VectorDisplacementMap.Vertex;

/** Rasterizes displaced triangles into signed vertical crossings, including folded surfaces. */
public final class VdmVoxelizer {
    public DensityColumn[] rasterize(VectorDisplacementMap map,int ox,int oz,int width){
        return rasterize(map,ox,oz,width,Double.POSITIVE_INFINITY);
    }
    /** A checked displacement bound lets regional callers skip distant triangles. */
    public DensityColumn[] rasterize(VectorDisplacementMap map,int ox,int oz,int width,double maxLateral){
        List<List<DensityColumn.Crossing>> hits=new ArrayList<>();
        for(int i=0;i<width*width;i++)hits.add(new ArrayList<>());
        int firstX=0,firstZ=0,lastX=map.size()-1,lastZ=map.size()-1;
        if(Double.isFinite(maxLateral)){
            // Reference positions are regular; displacement is bounded separately.
            double worldStep=(double)map.spacing()*map.worldScale();
            if(worldStep<=0)throw new IllegalArgumentException("Invalid VDM world spacing");
            double originX=map.originX()*worldStep/map.spacing(),originZ=map.originZ()*worldStep/map.spacing();
            firstX=Math.max(0,(int)Math.floor((ox-maxLateral-originX)/worldStep)-1);
            firstZ=Math.max(0,(int)Math.floor((oz-maxLateral-originZ)/worldStep)-1);
            lastX=Math.min(lastX,(int)Math.ceil((ox+width-1+maxLateral-originX)/worldStep)+1);
            lastZ=Math.min(lastZ,(int)Math.ceil((oz+width-1+maxLateral-originZ)/worldStep)+1);
        }
        for(int z=firstZ;z<lastZ;z++)for(int x=firstX;x<lastX;x++){
            Vertex a=map.vertex(x,z),b=map.vertex(x+1,z),c=map.vertex(x,z+1),d=map.vertex(x+1,z+1);
            triangle(a,b,d,ox,oz,width,hits);triangle(a,d,c,ox,oz,width,hits);
        }
        DensityColumn[] result=new DensityColumn[width*width];
        for(int i=0;i<result.length;i++)result[i]=new DensityColumn(hits.get(i));
        return result;
    }
    private void triangle(Vertex a,Vertex b,Vertex c,int ox,int oz,int width,List<List<DensityColumn.Crossing>> hits){
        double det=(b.x()-a.x())*(c.z()-a.z())-(b.z()-a.z())*(c.x()-a.x());
        if(Math.abs(det)<1e-10)return;
        int minX=Math.max(ox,(int)Math.ceil(Math.min(a.x(),Math.min(b.x(),c.x()))));
        int maxX=Math.min(ox+width-1,(int)Math.floor(Math.max(a.x(),Math.max(b.x(),c.x()))));
        int minZ=Math.max(oz,(int)Math.ceil(Math.min(a.z(),Math.min(b.z(),c.z()))));
        int maxZ=Math.min(oz+width-1,(int)Math.floor(Math.max(a.z(),Math.max(b.z(),c.z()))));
        for(int z=minZ;z<=maxZ;z++)for(int x=minX;x<=maxX;x++){
            double u=((x-a.x())*(c.z()-a.z())-(z-a.z())*(c.x()-a.x()))/det;
            double v=((b.x()-a.x())*(z-a.z())-(b.z()-a.z())*(x-a.x()))/det;
            if(u>=-1e-9&&v>=-1e-9&&u+v<=1+1e-9)
                hits.get((z-oz)*width+x-ox).add(new DensityColumn.Crossing(a.y()+u*(b.y()-a.y())+v*(c.y()-a.y()),det>0?1:-1));
        }
    }
}
