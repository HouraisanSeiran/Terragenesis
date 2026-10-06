package com.remotemountains.vdm;

/** Modifies a diffusion-derived vertex while preserving its reference-grid correspondence. */
public interface SurfaceModifier {
    Displacement apply(double x,double z,Displacement base);
}
