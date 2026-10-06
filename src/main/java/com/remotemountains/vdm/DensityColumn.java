package com.remotemountains.vdm;

import java.util.*;

/** Signed vertical surface crossings; multiple crossings preserve overhangs. */
public final class DensityColumn {
    public record Crossing(double height,int orientation) {}
    private final List<Crossing> crossings;
    public DensityColumn(List<Crossing> input){
        ArrayList<Crossing> sorted=new ArrayList<>(input);sorted.sort(Comparator.comparingDouble(Crossing::height).reversed());
        ArrayList<Crossing> unique=new ArrayList<>();
        for(var c:sorted){
            if(unique.isEmpty()||Math.abs(unique.getLast().height()-c.height())>1e-7||unique.getLast().orientation()!=c.orientation())unique.add(c);
        }
        crossings=List.copyOf(unique);
        if(crossings.isEmpty())throw new IllegalStateException("VDM mesh has a coverage hole");
    }
    public boolean solid(double y){int winding=0;for(var c:crossings)if(y<=c.height())winding+=c.orientation();return winding>0;}
    public double top(){return crossings.getFirst().height();}
    public int crossingCount(){return crossings.size();}
}
