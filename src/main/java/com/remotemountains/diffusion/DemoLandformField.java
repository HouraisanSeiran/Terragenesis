package com.remotemountains.diffusion;

import com.remotemountains.core.Landform;
import com.remotemountains.core.LandformShape;
import com.remotemountains.core.Noise;
import com.remotemountains.core.Regions;
import com.remotemountains.core.InselbergShape;
import com.remotemountains.core.RiftShape;
import com.remotemountains.core.KarstShape;
import com.remotemountains.core.PillarShape;

import static com.remotemountains.core.Noise.smooth;

/** Four compact landform test areas placed inside the finite diffusion sample. */
public final class DemoLandformField {
    private static final double CENTER_OFFSET = 256.0;
    private static final double RADIUS = 220.0;
    private static final double CORE = 90.0;
    private final LandformShape[] shapes;
    private final Regions.Region[] regions;
    private final Noise detail;
    private final PerlinLandformVariation variation;

    public DemoLandformField(long seed) {
        this(seed,false);
    }
    public DemoLandformField(long seed,boolean natural) {
        variation=natural?new PerlinLandformVariation(seed):null;
        shapes = new LandformShape[]{new InselbergShape(seed), new RiftShape(seed),
            new KarstShape(seed), new PillarShape(seed)};
        detail = new Noise(seed ^ 0x6A09E667F3BCC909L);
        regions = new Regions.Region[]{
            region(seed, 0, 0, 0, 0, Landform.INSELBERG),
            region(seed, 1, 0, 2 * CENTER_OFFSET, 0, Landform.RIFT),
            region(seed, 0, 1, 0, 2 * CENTER_OFFSET, Landform.KARST),
            region(seed, 1, 1, 2 * CENTER_OFFSET, 2 * CENTER_OFFSET, Landform.PILLARS)
        };
    }

    private static Regions.Region region(long seed, int gx, int gz, double x, double z, Landform type) {
        long key = Noise.hash(seed ^ 0x51ED2705L, gx, gz);
        return new Regions.Region(gx, gz, x, z, key, type, Noise.unit(key + 3) * Math.PI * 2.0);
    }

    public double apply(double x, double z, double modelHeight) {
        double result = modelHeight;
        for (int i = 0; i < regions.length; i++) {
            Regions.Region r = regions[i];
            double distance = Math.hypot(x - r.x(), z - r.z());
            double mask = variation==null?1.0-smooth(CORE,RADIUS,distance):variation.mask(x,z,r.x(),r.z());
            if (mask <= 0.0) continue;
            // Compress prototype kilometre-scale features to fit the 440-block exhibit.
            var p=variation==null?new PerlinLandformVariation.Point(x,z):variation.warp(x,z);
            double geological = shapes[i].height(r, r.x() + (p.x()-r.x())*2, r.z() + (p.z()-r.z())*2);
            double displacement = (geological - 86.0) * (.58 + .08 * detail.at(x / 91.0, z / 91.0));
            if(variation!=null)displacement=variation.relief(x,z,displacement,r.type());
            result += mask * displacement;
        }
        // Soft ceiling keeps isolated peaks from turning into clipped flat plateaus.
        return result <= 260 ? result : 260 + 50*Math.tanh((result-260)/50);
    }

    public Landform type(double x,double z) {
        return Landform.values()[(x < 256 ? 0 : 1) + (z < 256 ? 0 : 2)];
    }
}
