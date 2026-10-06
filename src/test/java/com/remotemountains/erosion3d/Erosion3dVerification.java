package com.remotemountains.erosion3d;

import java.util.List;

public final class Erosion3dVerification {
    public static void main(String[] args) {
        SweptPath path = new SweptPath(List.of(new Point3(0, 0, 0), new Point3(10, 0, 0)), 3);
        SweptPath.Sample frame = path.sample(new Point3(5, 0, 1));
        near(frame.tangent().dot(frame.across()), 0, 1e-12);
        near(frame.tangent().dot(frame.up()), 0, 1e-12);
        near(frame.up().dot(frame.across()), 0, 1e-12);
        ErosionConfig config = new ErosionConfig(.1, 1, 1);
        SedimentLedger ledger = new SedimentLedger();
        SurfaceSample bank = new SurfaceSample(new Point3(5, 0, 0), new Point3(0, 0, 1),
                2, true, 1, 10, 5, .02);
        ErosionResult result = Erosion3d.apply(bank, path, config, 1, ledger);
        near(result.retreat(), .1, 1e-12);
        near(result.delta().x(), 0, 1e-12);
        near(result.delta().z(), -.1, 1e-12);
        near(result.delta().dot(frame.tangent()), 0, 1e-12);
        near(result.removedVolume(), .2, 1e-12);
        near(ledger.rockRemoved(), ledger.sedimentProduced(), 1e-12);
        SurfaceSample dry = new SurfaceSample(bank.position(), bank.outwardNormal(), 1,
                false, 1, 10, 5, .02);
        SurfaceSample buried = new SurfaceSample(new Point3(5, -1, 0), bank.outwardNormal(), 1,
                false, 1, 10, 5, .02);
        SurfaceSample shallow = new SurfaceSample(bank.position(), bank.outwardNormal(), 1,
                true, .05, 10, 5, .02);
        SurfaceSample outside = new SurfaceSample(new Point3(5, 0, 4), bank.outwardNormal(), 1,
                true, 1, 10, 5, .02);
        SurfaceSample belowThreshold = new SurfaceSample(bank.position(), bank.outwardNormal(), 1,
                true, 1, 4, 5, .02);
        for (SurfaceSample s : List.of(dry, buried, shallow, outside, belowThreshold))
            near(Erosion3d.apply(s, path, config, 1, ledger).retreat(), 0, 0);
        SedimentLedger fractional = new SedimentLedger();
        SurfaceSample eighth = new SurfaceSample(bank.position(), bank.outwardNormal(), 1,
                true, 1, 1, 0, .125);
        for (int i = 0; i < 8; i++) Erosion3d.apply(eighth, path, config, 1, fractional);
        if (fractional.emitWholeBlocks(0) != 0) throw new AssertionError("Mobile sediment voxelized");
        fractional.deposit(fractional.transportAvailable());
        if (fractional.emitWholeBlocks(0) != 1) throw new AssertionError("Fractional sediment lost");
        near(fractional.depositedAvailable(), 0, 1e-9);
        near(fractional.rockRemoved(), 1, 1e-9);
        ErosionResult capped = Erosion3d.apply(bank, path,
                new ErosionConfig(.1, .03, .5), 100, fractional);
        near(capped.retreat(), .03, 1e-12);
        near(capped.sedimentVolume(), .03, 1e-12);
        near(fractional.rockRemoved(), fractional.sedimentProduced() + fractional.unconvertedRock(), 1e-9);
        near(fractional.sedimentProduced(), fractional.transportAvailable() + fractional.deposited(), 1e-9);
        near(fractional.deposited(), fractional.emittedSolid() + fractional.depositedAvailable(), 1e-9);
        SedimentLedger porous = new SedimentLedger();
        for (int i = 0; i < 4; i++) Erosion3d.apply(eighth, path, config, 1, porous);
        porous.deposit(porous.transportAvailable());
        if (porous.emitWholeBlocks(.5) != 1) throw new AssertionError("Porosity conversion failed");
        near(porous.emittedSolid(), .5, 1e-9);
        SedimentLedger decimal = new SedimentLedger();
        SurfaceSample tenth = new SurfaceSample(bank.position(), bank.outwardNormal(), 1,
                true, 1, 1, 0, .1);
        for (int i = 0; i < 10; i++) Erosion3d.apply(tenth, path, config, 1, decimal);
        decimal.deposit(decimal.transportAvailable());
        decimal.emitWholeBlocks(0);
        near(decimal.emittedSolid() + decimal.depositedAvailable(), decimal.deposited(), 1e-12);
        near(decimal.deposited(), decimal.sedimentProduced(), 1e-12);
        SedimentLedger exported = new SedimentLedger();
        Erosion3d.apply(eighth, path, config, 1, exported);
        exported.export(.0625);
        exported.deposit(exported.transportAvailable());
        near(exported.sedimentProduced(), exported.exportedSolid() + exported.deposited()
                + exported.transportAvailable(), 1e-12);
        System.out.println("Erosion3d verification passed");
    }
    private static void near(double actual, double expected, double tolerance) {
        if (!Double.isFinite(actual) || Math.abs(actual - expected) > tolerance)
            throw new AssertionError(actual + " != " + expected);
    }
}
