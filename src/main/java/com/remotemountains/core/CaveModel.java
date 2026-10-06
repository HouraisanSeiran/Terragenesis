package com.remotemountains.core;
public final class CaveModel {
    private final Noise caves;
    public CaveModel(long seed){caves=new Noise(seed^99273);}
    public boolean contains(double x,double y,double z,Landscape.Base base,double surface,double riverWater){
        if(y<-48||y>surface-6||y>base.height()-6)return false;
        if(riverWater>0&&y>riverWater-12)return false;
        double a=caves.at(x/69,y/43.0,z/69),b=caves.at(x/73+41,y/49.0+9,z/73-19);
        double radius=base.type()==Landform.KARST?.115:.075;
        boolean tunnel=a*a+b*b<radius*radius;
        double room=caves.at(x/110+13,y/60.0,z/110-71);
        boolean chamber=base.type()==Landform.KARST&&room>.46;
        return tunnel||chamber;
    }
}
