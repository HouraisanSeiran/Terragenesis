package com.remotemountains.core;

import static com.remotemountains.core.Noise.*;

/** Stateless landscape samples. Geological shape and present climate have separate seeds. */
public final class Landscape {
    public record Climate(double temperature,double rain) {
        public int variant(){return temperature<.28?0:rain<.34?1:rain>.64?3:2;}
    }
    public record Base(double height,Landform type,Climate climate,double landmark) {}
    public final long seed;
    public final Regions regions;
    private final Noise shape;
    private final ClimateModel climate;
    private final LandformShape[] shapes;
    public final CaveModel caves;
    public Landscape(long seed){
        this.seed=seed;regions=new Regions(seed);shape=new Noise(seed);
        climate=new ClimateModel(seed);caves=new CaveModel(seed);
        shapes=new LandformShape[]{new InselbergShape(seed),new RiftShape(seed),new KarstShape(seed),new PillarShape(seed)};
    }
    public Base base(double x,double z){
        Regions.Blend b=regions.at(x,z);double h=0,landmark=0;
        for(int i=0;i<b.regions().length;i++)if(b.weights()[i]>0){
            Regions.Region r=b.regions()[i];h+=shapes[r.type().ordinal()].height(r,x,z)*b.weights()[i];
            landmark=Math.max(landmark,(1-smooth(340,720,Math.hypot(x-r.x(),z-r.z())))*b.weights()[i]);
        }
        Climate c=climate.sample(x,z,h);
        // Climate-dependent rock weathering; bulk river incision lives in Hydrology.
        double rock=b.primary().type()==Landform.KARST?1.25:b.primary().type()==Landform.PILLARS?.65:1;
        double gullies=Math.pow(1-Math.abs(shape.at(x/85+9,z/85)),10);
        h-=gullies*(1.3+4*c.rain())*rock*(1-landmark*.85);
        return new Base(clamp(h,68,300),b.primary().type(),c,landmark);
    }
}
