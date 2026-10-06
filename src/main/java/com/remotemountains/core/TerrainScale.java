package com.remotemountains.core;

/** Persisted world-space transform, applied after all local geological processes. */
public record TerrainScale(int factor,int minY,int upperY,int seaLevel,String scaleId) {
    public TerrainScale(int factor,int minY,int upperY,int seaLevel) {
        this(factor,minY,upperY,seaLevel,"");
    }
    public static final TerrainScale LEGACY=new TerrainScale(1,-64,320,72);
    public static final TerrainScale TALL=new TerrainScale(3,-64,1024,62);
    public static final TerrainScale RAW_MODEL=new TerrainScale(1,-64,1024,62);
    public static final TerrainScale METRIC_SURFACE=new TerrainScale(1,-64,1024,62,"metric_1m_sea62_1024_v1");
    public static TerrainScale of(String id){return switch(id){
        case "legacy" -> LEGACY;
        case "relief_3x_sea62_1024_v1" -> TALL;
        case "raw_model_sea62_1024_v1" -> RAW_MODEL;
        case "metric_1m_sea62_1024_v1" -> METRIC_SURFACE;
        default -> throw new IllegalArgumentException("Unknown terrain scale: "+id);
    };}
    public double local(double value){return value/factor;}
    public double world(double value){return value*factor;}
    /** Keep the seabed/subsurface range; enlarge relief above the fixed sea datum. */
    public double height(double y){
        if(this.equals(METRIC_SURFACE))return y;
        return seaLevel()+(y-72)*(y<=72?1:factor);
    }
    public double localHeight(double y){
        if(this.equals(METRIC_SURFACE))return y;
        return 72+(y-seaLevel())/(y<=seaLevel()?1:factor);
    }
    public int depth(){return upperY-minY;}
    public String id(){
        if(!scaleId.isEmpty()) return scaleId;
        if(this.equals(LEGACY)) return "legacy";
        if(this.equals(TALL)) return "relief_3x_sea62_1024_v1";
        if(this.equals(RAW_MODEL)) return "raw_model_sea62_1024_v1";
        return factor+":"+minY+":"+upperY+":"+seaLevel;
    }
}
