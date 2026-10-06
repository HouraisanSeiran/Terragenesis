package com.remotemountains.cliff;

/** Anisotropic jittered rock cells, selective joints and stratified resistance. */
public final class VoronoiRockField {
    public record Sample(double relief,double hardness,double joint){}
    private final long seed;
    public VoronoiRockField(long seed){this.seed=seed;}
    private double random(int x,int y,int channel){
        long h=seed+x*0x9E3779B97F4A7C15L+y*0xC2B2AE3D27D4EB4FL+channel*0x165667B19E3779F9L;
        h=(h^(h>>>30))*0xBF58476D1CE4E5B9L;h=(h^(h>>>27))*0x94D049BB133111EBL;
        return ((h^(h>>>31))>>>11)*0x1.0p-53;
    }
    public Sample sample(double u,double height){
        double x=(u+2.3*Math.sin(height*.16))/15,y=(height+1.1*Math.sin(u*.055))/9;
        int gx=(int)Math.floor(x),gy=(int)Math.floor(y),bestX=0,bestY=0;
        double first=Double.POSITIVE_INFINITY,second=first;
        for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++){
            int cx=gx+dx,cy=gy+dy;
            double px=cx+.15+.7*random(cx,cy,1),py=cy+.15+.7*random(cx,cy,2);
            double distance=Math.hypot(x-px,y-py);
            if(distance<first){second=first;first=distance;bestX=cx;bestY=cy;}
            else if(distance<second)second=distance;
        }
        // The nearest-distance gap is only a joint indicator, not an exact distance to a cell edge.
        double gap=second-first;
        double fracture=Math.exp(-gap*gap/.012)*(.3+.7*random(bestX,bestY,3));
        double interior=CliffSettings.smooth(gap/.22);
        double relief=(.65+1.65*random(bestX,bestY,4))*interior-.9*fracture;
        double layer=.5+.5*Math.sin(height*.49+Math.sin(u*.024));
        double hardness=CliffSettings.clamp(.40+.64*random(bestX,bestY,5)+.37*layer-.29*fracture,.22,1.5);
        return new Sample(relief,hardness,fracture);
    }
    public void apply(CliffPatch p){
        for(int v=0;v<p.rows;v++)for(int u=0;u<p.columns;u++){
            int i=p.index(u,v);Sample s=sample(p.u(u),p.skeleton[i].y());
            p.rock[i]=s.relief()*p.mask[i];p.hardness[i]=s.hardness();p.joint[i]=s.joint();
        }
        p.refresh();
    }
}
