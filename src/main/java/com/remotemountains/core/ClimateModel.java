package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class ClimateModel {
    private final Noise climate,shape;
    public ClimateModel(long seed){climate=new Noise(seed^459713);shape=new Noise(seed);}
    public Landscape.Climate sample(double x,double z,double height){
        double temp=clamp(.53+.72*climate.fbm(x/4200,z/4200,3)-(height-90)*.00135,0,1);
        double humidity=.53+.83*climate.fbm(x/2800+83,z/2800-31,3);
        // Broad prevailing-west-wind uplift and lee drying; a climatic approximation, not CFD.
        double relief=shape.at(x/700,z/700)-shape.at((x-230)/700,z/700);
        return new Landscape.Climate(temp,clamp(humidity+relief*.20,0,1));
    }
}
