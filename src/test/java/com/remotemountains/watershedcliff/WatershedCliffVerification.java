package com.remotemountains.watershedcliff;

import com.remotemountains.watershed.WatershedTerrainSource;

/** Checks that patch water and sediment actually rejoin the downstream graph. */
public final class WatershedCliffVerification {
    private static void require(boolean yes,String message){
        if(!yes)throw new AssertionError(message);
    }
    private static void close(double a,double b,String message){
        require(Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(b)),message+": "+a+" vs "+b);
    }
    public static void main(String[] args){
        long seed=20260927L;
        var source=new WatershedTerrainSource(seed,"");
        var graph=source.graph();
        double beforeWater=graph.outlet().discharge(),beforeSediment=graph.outlet().sedimentFlux();
        var first=new WatershedCliffModifier(source,seed);
        var audit=first.audit();
        require(audit.allocatedPerStep()>0 && audit.waterOut()>0 && audit.erodedRock()>0,
            "River flow must erode and leave the cliff chart");
        close(audit.waterIn(),audit.allocatedPerStep()*audit.steps(),"Prescribed upstream input");
        close(audit.waterResidual(),0,"Patch water balance");
        close(audit.sedimentResidual(),0,"Patch sediment balance");
        close(graph.outlet().discharge(),beforeWater-audit.allocatedPerStep()
            +Math.min(audit.allocatedPerStep(),audit.returnedPerStep()),"Downstream water");
        close(graph.outlet().sedimentFlux(),beforeSediment+audit.sedimentOutPerStep(),
            "Downstream sediment");
        close(graph.ledger().waterResidual(),0,"Catchment water balance");
        close(graph.ledger().sedimentResidual(),0,"Catchment sediment balance");
        double onceWater=graph.outlet().discharge(),onceSediment=graph.outlet().sedimentFlux();
        var repeated=new WatershedCliffModifier(source,seed);
        require(graph.bankExchanges().size()==1,"Rebuild must not double-register bank exchange");
        close(graph.outlet().discharge(),onceWater,"Idempotent water routing");
        close(graph.outlet().sedimentFlux(),onceSediment,"Idempotent sediment routing");
        close(repeated.audit().waterOut(),audit.waterOut(),"Deterministic patch routing");
        System.out.println("PASS watershed cliff bank exchange");
    }
}
