package com.remotemountains.cliff;

/** Immutable, versioned demo settings. Angles are measured from horizontal. */
public record CliffSettings(long seed,double angleDegrees,int lean,int steps,double erosionRate) {
    public static final String RECIPE="diffusion-vdm-voronoi-runoff-v2";
    public static final double CENTER_X=256,CENTER_Z=256,HEIGHT=42;
    public static final double HALF_LENGTH=160,HALF_DEPTH=80,WALL_HALF_WIDTH=24,SPACING=2;
    public static final double MAX_RETREAT=7.0,MAX_STEP_RETREAT=.055;
    public CliffSettings {
        if(!Double.isFinite(angleDegrees)||angleDegrees<60||angleDegrees>90||Math.abs(lean)!=1
                ||steps<0||steps>512||!Double.isFinite(erosionRate)||erosionRate<0||erosionRate>1)
            throw new IllegalArgumentException("Invalid cliff settings");
    }
    public static CliffSettings demo(long seed){return new CliffSettings(seed,76,1,192,.105);}
    public double topOffset(){return lean*HEIGHT/Math.tan(Math.toRadians(angleDegrees));}
    public static double clamp(double v,double lo,double hi){return Math.max(lo,Math.min(hi,v));}
    public static double smooth(double v){double t=clamp(v,0,1);return t*t*(3-2*t);}
}
