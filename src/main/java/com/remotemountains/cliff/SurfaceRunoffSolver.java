package com.remotemountains.cliff;

import java.util.Arrays;

/** Conservative surface routing with tangential gravity and a small film-pressure term.
 * This is a deterministic visual erosion approximation, not Navier-Stokes or capillary flow.
 */
public final class SurfaceRunoffSolver {
    private static final int[] DU={-1,0,1,-1,1,-1,0,1},DV={-1,-1,-1,0,0,1,1,1};
    public ErosionStatistics run(CliffPatch p){return run(p,new RunoffBoundary());}
    public ErosionStatistics run(CliffPatch p,RunoffBoundary boundary){
        long start=System.nanoTime();int n=p.size;
        double[] water=new double[n],next=new double[n],sediment=new double[n],nextSediment=new double[n],discharge=new double[n];
        WaterDetachment falling=new WaterDetachment(p);
        CliffErosionSolver erosion=new CliffErosionSolver(p);
        double input=0,output=0,sedimentOut=0,removed=0,detached=0,reattached=0,sideways=0;
        double[] weights=new double[8];int[] neighbours=new int[8];
        for(int step=0;step<p.settings.steps();step++){
            if(step%4==0)p.refresh();
            if(step%16==0)falling.refresh(p);
            input+=boundary.inject(p,water);
            Arrays.fill(next,0);Arrays.fill(nextSediment,0);Arrays.fill(discharge,0);
            for(int i=0;i<n;i++){
                double volume=water[i],mass=sediment[i];
                if(boundary.outlet(p,i)){output+=volume;sedimentOut+=mass;continue;}
                if(volume<=1e-14){next[i]+=volume;nextSediment[i]+=mass;continue;}
                double fraction=falling.fraction(p,i),fall=volume*fraction,fallSediment=mass*fraction;
                if(fall>0){
                    int target=falling.target(i);detached+=fall;
                    if(target>=0&&p.positions[target].y()<p.positions[i].y()){
                        next[target]+=fall;nextSediment[target]+=fallSediment;reattached+=fall;
                    }else{output+=fall;sedimentOut+=fallSediment;}
                    volume-=fall;mass-=fallSediment;
                }
                Vec3 pos=p.positions[i],normal=p.normals[i];
                Vec3 gravity=new Vec3(0,-1,0).add(normal.scale(normal.y()));
                double depth=volume/p.areas[i],sum=0;int col=i%p.columns,row=i/p.columns;
                for(int k=0;k<8;k++){
                    int j=p.index(col+DU[k],row+DV[k]);neighbours[k]=j;
                    Vec3 edge=p.positions[j].subtract(pos);double length=Math.max(.1,edge.length());
                    double pressure=.08*(depth-water[j]/p.areas[j])/length;
                    double drive=Math.max(0,.5*(pos.y()-p.positions[j].y())/length+.5*gravity.dot(edge)/length+pressure);
                    weights[k]=drive*drive*drive*drive;sum+=weights[k];
                }
                double outgoing=sum>1e-14?volume*.72:0;
                double sedimentMoving=volume>0?mass*outgoing/volume:0;
                next[i]+=volume-outgoing;nextSediment[i]+=mass-sedimentMoving;
                discharge[i]=outgoing+.015*(volume-outgoing);p.exposure[i]+=outgoing;
                if(sum>1e-14)for(int k=0;k<8;k++)if(weights[k]>0){
                    double share=weights[k]/sum;int j=neighbours[k];
                    next[j]+=outgoing*share;nextSediment[j]+=sedimentMoving*share;
                    if(DU[k]!=0)sideways+=outgoing*share;
                }
            }
            removed+=erosion.erode(p,discharge,nextSediment);
            double[] swap=water;water=next;next=swap;swap=sediment;sediment=nextSediment;nextSediment=swap;
        }
        p.refresh();double max=0;
        for(double d:p.retreat)max=Math.max(max,d);
        return new ErosionStatistics(input,output,Arrays.stream(water).sum(),removed,
            sedimentOut,Arrays.stream(sediment).sum(),detached,reattached,sideways,max,(System.nanoTime()-start)/1e9);
    }
}
