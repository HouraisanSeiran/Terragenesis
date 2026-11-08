package com.remotemountains.core;

import java.util.Arrays;

/** Pure core verification; compiles to a temporary target without building a mod JAR. */
public final class IrregularHydrologyVerification {
    private static void require(boolean condition,String message){
        if(!condition)throw new AssertionError(message);
    }

    public static void main(String[] args){
        Hydrology first=new Hydrology(new Landscape(20261020L));
        Hydrology second=new Hydrology(new Landscape(20261020L));
        Hydrology.Tile tile=first.tile(0,0),east=first.tile(1,0);
        Hydrology.Tile repeated=second.tile(0,0);
        int nonRasterEdges=0,nonRasterParents=0;
        for(int node=0;node<Hydrology.N*Hydrology.N;node++){
            require(tile.nodeX[node]==repeated.nodeX[node]&&tile.nodeZ[node]==repeated.nodeZ[node],"stable world nodes");
            require(Arrays.equals(tile.neighbors[node],repeated.neighbors[node]),"stable graph adjacency");
            for(int target:tile.neighbors[node]){
                require(Arrays.binarySearch(tile.neighbors[target],node)>=0,"symmetric graph edge");
                int distance=Math.max(Math.abs(node%Hydrology.N-target%Hydrology.N),Math.abs(node/Hydrology.N-target/Hydrology.N));
                if(distance>1)nonRasterEdges++;
            }
            int target=tile.parent[node];
            if(target>=0){
                require(Arrays.binarySearch(tile.neighbors[node],target)>=0,"receiver is an actual graph edge");
                if(Math.max(Math.abs(node%Hydrology.N-target%Hydrology.N),Math.abs(node/Hydrology.N-target/Hydrology.N))>1)nonRasterParents++;
            }
        }
        for(int row=0;row<Hydrology.N;row++){
            int westNode=row*Hydrology.N+Hydrology.N-1,eastNode=row*Hydrology.N;
            require(tile.nodeX[westNode]==east.nodeX[eastNode]&&tile.nodeZ[westNode]==east.nodeZ[eastNode],"overlapping tile nodes are bit-identical");
        }
        require(nonRasterEdges>0&&nonRasterParents>0,"routing uses genuinely non-eight-neighbor graph edges");
        Hydrology.Audit audit=tile.audit();
        require(Math.abs(audit.rain()-audit.outletFlow())<1e-7,"rain inventory conserved");
        require(audit.downhill(),"derived channel beds descend");
        require(audit.channels()>20,"prototype tributaries remain usable");
        for(double x=-100.;x<4200.;x+=137.){
            double raw=140.;
            Hydrology.Water a=first.sample(x,977.,raw),b=second.sample(x,977.,raw);
            require(a.equals(b),"sampling independent of tile load order");
            require(Double.isFinite(a.incision())&&a.incision()>=0.,"finite cut-only geometry");
        }
        System.out.println("PASS "+Hydrology.ALGORITHM+"; non-raster edges="+nonRasterEdges+"; receivers="+nonRasterParents);
    }
}
