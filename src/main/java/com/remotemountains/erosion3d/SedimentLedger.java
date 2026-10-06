package com.remotemountains.erosion3d;

/** Volumes are solid-equivalent blocks cubed; emitted blocks use explicit porosity. */
public final class SedimentLedger {
    private double rockRemoved;
    private double sedimentProduced;
    private double unconvertedRock;
    // Cumulative mobile material resolved as a deposit or boundary export.
    private double transported;
    private double deposited;
    private double exportedSolid;
    private double emittedSolid;
    private double transportAvailable;
    private double depositedAvailable;
    private long emittedBlocks;

    public void add(ErosionResult result) {
        if (!finiteNonnegative(result.removedVolume()) || !finiteNonnegative(result.sedimentVolume())
                || result.sedimentVolume() > result.removedVolume()) {
            throw new IllegalArgumentException("Invalid erosion budget");
        }
        double nextRock = addFinite(rockRemoved, result.removedVolume());
        double nextSediment = addFinite(sedimentProduced, result.sedimentVolume());
        double nextUnconverted = addFinite(unconvertedRock, result.removedVolume() - result.sedimentVolume());
        double nextAvailable = addFinite(transportAvailable, result.sedimentVolume());
        rockRemoved = nextRock;
        sedimentProduced = nextSediment;
        unconvertedRock = nextUnconverted;
        transportAvailable = nextAvailable;
    }

    /** Transfer mobile solid volume into local deposit. */
    public void deposit(double solidVolume) {
        if (!finiteNonnegative(solidVolume) || solidVolume > transportAvailable) {
            throw new IllegalArgumentException("Invalid deposition");
        }
        double nextTransported = addFinite(transported, solidVolume);
        double nextDeposited = addFinite(deposited, solidVolume);
        double nextAvailable = addFinite(depositedAvailable, solidVolume);
        transportAvailable -= solidVolume;
        transported = nextTransported;
        deposited = nextDeposited;
        depositedAvailable = nextAvailable;
    }

    /** Transfer mobile solid volume through an explicit outgoing boundary. */
    public void export(double solidVolume) {
        if (!finiteNonnegative(solidVolume) || solidVolume > transportAvailable) {
            throw new IllegalArgumentException("Invalid export");
        }
        double nextTransported = addFinite(transported, solidVolume);
        double nextExported = addFinite(exportedSolid, solidVolume);
        transportAvailable -= solidVolume;
        transported = nextTransported;
        exportedSolid = nextExported;
    }

    /** Voxelize only deposited solid; porosity is the empty fraction of each output block. */
    public long emitWholeBlocks(double porosity) {
        if (!Double.isFinite(porosity) || porosity < 0 || porosity >= 1) {
            throw new IllegalArgumentException("Invalid porosity");
        }
        double solidPerBlock = 1 - porosity;
        double possible = Math.floor(depositedAvailable / solidPerBlock);
        if (!Double.isFinite(possible) || possible >= Long.MAX_VALUE - emittedBlocks) {
            throw new IllegalArgumentException("Voxel count overflow");
        }
        long whole = (long) possible;
        double consumed = whole * solidPerBlock;
        double nextEmitted = addFinite(emittedSolid, consumed);
        long nextBlocks = Math.addExact(emittedBlocks, whole);
        depositedAvailable -= consumed;
        emittedSolid = nextEmitted;
        emittedBlocks = nextBlocks;
        return whole;
    }
    public double rockRemoved() { return rockRemoved; }
    public double sedimentProduced() { return sedimentProduced; }
    public double unconvertedRock() { return unconvertedRock; }
    public double transported() { return transported; }
    public double deposited() { return deposited; }
    public double exportedSolid() { return exportedSolid; }
    public double transportAvailable() { return transportAvailable; }
    public double depositedAvailable() { return depositedAvailable; }
    public double emittedSolid() { return emittedSolid; }
    public long emittedBlocks() { return emittedBlocks; }

    private static boolean finiteNonnegative(double value) {
        return Double.isFinite(value) && value >= 0;
    }

    private static double addFinite(double a, double b) {
        double result = a + b;
        if (!Double.isFinite(result)) {
            throw new IllegalArgumentException("Budget overflow");
        }
        return result;
    }
}
