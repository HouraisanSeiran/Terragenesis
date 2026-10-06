package com.remotemountains.cliff;

import java.util.Arrays;

/** Contact-driven wall retreat and neighbouring channel-wall erosion in a bounded chart. */
public final class CliffErosionSolver {
    private final double[] demand;
    public CliffErosionSolver(CliffPatch p){demand=new double[p.size];}
    public double erode(CliffPatch p,double[] discharge,double[] sediment){
        Arrays.fill(demand,0);
        for(int i=0;i<p.size;i++){
            if(p.boundary(i)||p.mask[i]<=0)continue;
            double dose=p.settings.erosionRate()*Math.sqrt(Math.max(0,discharge[i])/p.areas[i]);
            dose*=p.mask[i]*(1+.6*p.joint[i])/p.hardness[i];
            demand[i]+=dose;
            // Adjacent protruding rock faces are in contact with the finite-width rivulet.
            for(int j:new int[]{i-1,i+1})if(!p.boundary(j)&&p.rock[j]-p.retreat[j]>p.rock[i]-p.retreat[i]-.2)
                demand[j]+=.30*dose*p.mask[j]/p.hardness[j];
        }
        double removed=0;
        for(int i=0;i<p.size;i++){
            if(p.boundary(i)||p.mask[i]<=0)continue;
            double cosine=Math.max(.25,p.normals[i].dot(p.axis[i]));
            // A ray-depth update has normal speed depthRate * dot(ray, surfaceNormal).
            double amount=Math.min(CliffSettings.MAX_STEP_RETREAT,Math.max(0,demand[i]/cosine));
            amount=Math.min(amount,CliffSettings.MAX_RETREAT*p.mask[i]-p.retreat[i]);
            if(amount<=0)continue;
            double volume=amount*p.areas[i]*cosine;
            p.retreat[i]+=amount;sediment[i]+=volume;removed+=volume;
        }
        return removed;
    }
}
