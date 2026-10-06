package com.remotemountains.cliff;

/** Conserved water/eroded-rock ledgers; detachment totals are internal throughputs. */
public record ErosionStatistics(double waterIn,double waterOut,double waterStored,double erodedRock,
        double sedimentOut,double sedimentStored,double detachedWater,double reattachedWater,
        double sidewaysWater,double maxRetreat,double seconds) {
    public double waterError(){return waterIn-waterOut-waterStored;}
    public double sedimentError(){return erodedRock-sedimentOut-sedimentStored;}
    public String json(){
        String[] names={"water_in","water_out","water_stored","water_error","eroded_rock","sediment_out",
            "sediment_stored","sediment_error","detached_water","reattached_water","sideways_water","max_retreat","seconds"};
        double[] values={waterIn,waterOut,waterStored,waterError(),erodedRock,sedimentOut,sedimentStored,
            sedimentError(),detachedWater,reattachedWater,sidewaysWater,maxRetreat,seconds};
        java.util.StringJoiner json=new java.util.StringJoiner(",","{","}");
        for(int i=0;i<names.length;i++)json.add('"'+names[i]+'"'+":"+values[i]);
        return json.toString();
    }
}
