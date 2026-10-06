package com.remotemountains.watershedcliff;

import com.remotemountains.cliff.CliffPatch;
import com.remotemountains.cliff.CliffPipeline;
import com.remotemountains.cliff.CliffPlacement;
import com.remotemountains.cliff.CliffSettings;
import com.remotemountains.cliff.ErosionStatistics;
import com.remotemountains.cliff.RunoffBoundary;
import com.remotemountains.cliff.Vec3;
import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.vdm.Displacement;
import com.remotemountains.vdm.SurfaceModifier;
import com.remotemountains.watershed.DrainageGraph;
import com.remotemountains.watershed.WatershedTerrainSource;

/** A single river-bank chart shared by every chunk in the mountain-to-sea demo. */
public final class WatershedCliffModifier implements SurfaceModifier {
    public static final String RECIPE="watershed-vdm-runoff-v1";
    public static final double BANK_FRACTION=.02;
    public static final double STEP_SECONDS=60; // Demo clock convention, not calibrated rainfall.
    private static final double CENTER_X=900;
    private static final double ROTATION=Math.atan2(-CliffPatch.OUT.x(),-CliffPatch.OUT.z());

    /** Water in local cubic metres, sediment as displaced rock volume; all fluxes are per demo step. */
    public record LocalAudit(double stepSeconds,int steps,double reachDischarge,double allocatedPerStep,
            double waterIn,double waterOut,double waterStored,double sedimentOut,double sedimentStored,
            double erodedRock,double waterResidual,double sedimentResidual,int fromNode,int returnNode) {
        public double returnedPerStep(){return waterOut/steps;}
        public double sedimentOutPerStep(){return sedimentOut/steps;}
        public String json(){
            return "{\"step_seconds\":"+stepSeconds+",\"steps\":"+steps
                +",\"reach_discharge_per_step\":"+reachDischarge
                +",\"allocated_per_step\":"+allocatedPerStep
                +",\"water_in\":"+waterIn+",\"water_out\":"+waterOut
                +",\"water_stored\":"+waterStored+",\"water_residual\":"+waterResidual
                +",\"sediment_out\":"+sedimentOut+",\"sediment_stored\":"+sedimentStored
                +",\"eroded_rock\":"+erodedRock+",\"sediment_residual\":"+sedimentResidual
                +",\"from_node\":"+fromNode+",\"return_node\":"+returnNode+"}";
        }
    }

    private final WatershedTerrainSource base;
    private final CliffPlacement placement;
    private final CliffPipeline.Result result;
    private final LocalAudit audit;

    public WatershedCliffModifier(BaseTerrainSource base,long seed){
        if(!(base instanceof WatershedTerrainSource watershed))
            throw new IllegalArgumentException("Watershed cliff requires WatershedTerrainSource");
        this.base=watershed;
        DrainageGraph graph=watershed.graph();
        DrainageGraph.Channel reach=graph.nearestChannel(CENTER_X,0);
        if(reach==null)throw new IllegalStateException("No trunk reach beside watershed cliff");
        placement=new CliffPlacement(seed,CENTER_X,reach.z()+96,ROTATION,
            new CliffSettings(seed^0x4874652aL,76,1,192,.105));
        // Use the immutable reach flow so a second modifier cannot reallocate adjusted Q.
        DrainageGraph.Node upstream=graph.baselineNode(reach.fromNode());
        DrainageGraph.Node downstream=graph.baselineNode(reach.toNode());
        double dx=downstream.x()-upstream.x(),dz=downstream.z()-upstream.z();
        double t=Math.max(0,Math.min(1,((reach.x()-upstream.x())*dx
            +(reach.z()-upstream.z())*dz)/(dx*dx+dz*dz)));
        double baseQ=upstream.discharge()+t*(downstream.discharge()-upstream.discharge());
        double allocated=baseQ*BANK_FRACTION;
        BaseTerrainSource local=(x,z)->{
            Vec3 world=placement.toWorld(x,z);
            return base.sample(world.x(),world.z());
        };
        CliffPipeline.Result built=new CliffPipeline().build(local,placement.settings(),
            CliffPipeline.Stage.ERODED,new RunoffBoundary(allocated,0,14));
        ErosionStatistics s=built.statistics();
        int steps=placement.settings().steps();
        LocalAudit completed=new LocalAudit(STEP_SECONDS,steps,baseQ,allocated,
            s.waterIn(),s.waterOut(),s.waterStored(),s.sedimentOut(),s.sedimentStored(),
            s.erodedRock(),s.waterError(),s.sedimentError(),reach.fromNode(),reach.toNode());
        graph.registerBankExchange(RECIPE,reach.fromNode(),reach.toNode(),allocated,
            Math.min(allocated,completed.returnedPerStep()),s.erodedRock()/steps,s.sedimentStored()/steps);
        audit=completed;
        result=built;
    }

    public CliffPipeline.Result result(){return result;}
    public LocalAudit audit(){return audit;}
    public CliffPlacement placement(){return placement;}

    @Override public Displacement apply(double x,double z,Displacement initial){
        if(!placement.contains(x,z))return initial;
        Vec3 local=placement.toLocal(x,z);
        Displacement d=result.patch().delta(local.x(),local.z());
        Vec3 rotated=placement.rotate(new Vec3(d.dx(),d.dy(),d.dz()));
        return new Displacement(initial.dx()+rotated.x(),initial.dy()+rotated.y(),initial.dz()+rotated.z());
    }
}
