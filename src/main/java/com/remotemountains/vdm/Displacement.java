package com.remotemountains.vdm;

/** World-space vector displacement, measured in Minecraft blocks. */
public record Displacement(double dx,double dy,double dz) {
    public Displacement {
        if(!Double.isFinite(dx)||!Double.isFinite(dy)||!Double.isFinite(dz))throw new IllegalArgumentException("Non-finite VDM");
    }
}
