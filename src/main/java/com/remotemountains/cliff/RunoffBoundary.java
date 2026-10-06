package com.remotemountains.cliff;

/** Prescribed, reproducible tributary inflows; not a simulation of the whole upstream basin. */
public final class RunoffBoundary {
    private final boolean prescribed;
    private final double waterPerStep,inletU,spreadU;
    public RunoffBoundary(){prescribed=false;waterPerStep=0;inletU=0;spreadU=1;}
    /** Water units injected into the bank patch per simulation step. */
    public RunoffBoundary(double waterPerStep,double inletU,double spreadU){
        if(!Double.isFinite(waterPerStep)||waterPerStep<0||!Double.isFinite(inletU)
                ||Math.abs(inletU)>=CliffSettings.HALF_LENGTH||!Double.isFinite(spreadU)||spreadU<=0)
            throw new IllegalArgumentException("Invalid prescribed runoff boundary");
        prescribed=true;this.waterPerStep=waterPerStep;this.inletU=inletU;this.spreadU=spreadU;
    }
    /** Transfer water/sediment to the unmodelled downstream catchment at the cliff foot. */
    public boolean outlet(CliffPatch p,int i){return p.boundary(i)||p.v(i/p.columns)>=CliffSettings.WALL_HALF_WIDTH;}
    public double inject(CliffPatch p,double[] water){
        int row=(int)((CliffSettings.HALF_DEPTH-CliffSettings.WALL_HALF_WIDTH)/CliffSettings.SPACING);
        if(prescribed){
            double weightSum=0;
            for(int col=1;col<p.columns-1;col++)weightSum+=bell((p.u(col)-inletU)/spreadU);
            if(weightSum==0)throw new IllegalStateException("Runoff inlet misses cliff chart");
            for(int col=1;col<p.columns-1;col++)
                water[p.index(col,row)]+=waterPerStep*bell((p.u(col)-inletU)/spreadU)/weightSum;
            return waterPerStep;
        }
        double total=0,phase=((p.settings.seed()>>>8)&255)/255.0*12-6;
        for(int col=1;col<p.columns-1;col++){
            double u=p.u(col),edge=CliffSettings.smooth((125-Math.abs(u))/20);
            double q=edge*(.06+.65*bell((u+61+phase)/11)+.95*bell((u-5-phase)/15)+.55*bell((u-66+phase)/9));
            water[p.index(col,row)]+=q;total+=q;
        }
        return total;
    }
    private double bell(double x){return Math.exp(-x*x);}
}
