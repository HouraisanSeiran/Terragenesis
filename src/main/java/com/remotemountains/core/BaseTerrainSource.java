package com.remotemountains.core;

/** A source supplies the actual base elevation; geometric prototypes are explicitly opt-in. */
public interface BaseTerrainSource {
    Terrain.Column sample(double x,double z);
    default String identity(){return "prototype-only";}
}
