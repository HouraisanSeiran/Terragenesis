package com.remotemountains.hydrology3d;

/** Width in blocks = widthFactor * Q^widthExponent; Q is block-cubed per second. */
public record RiverConfig(double widthFactor, double widthExponent, double minWidth,
        double maxWidth, double clearanceBlocks, double stepSeconds, double blockMeters) {
    public RiverConfig {
        if (!Double.isFinite(widthFactor) || widthFactor <= 0
                || !Double.isFinite(widthExponent) || widthExponent <= 0 || widthExponent > 1
                || !Double.isFinite(minWidth) || minWidth <= 0
                || !Double.isFinite(maxWidth) || maxWidth < minWidth
                || !Double.isFinite(clearanceBlocks) || clearanceBlocks < 0
                || !Double.isFinite(stepSeconds) || stepSeconds <= 0
                || !Double.isFinite(blockMeters) || blockMeters <= 0)
            throw new IllegalArgumentException("Invalid river dimension or time scale");
    }
    public static RiverConfig defaults() { return new RiverConfig(1.8, .45, 1, 32, 2, .05, 1); }
    public double width(double q) {
        if (!Double.isFinite(q) || q < 0) throw new IllegalArgumentException("Invalid discharge");
        return q == 0 ? 0 : Math.max(minWidth, Math.min(maxWidth, widthFactor * Math.pow(q, widthExponent)));
    }
    public double cubicMetersPerSecond(double q) {
        return q * blockMeters * blockMeters * blockMeters;
    }
}
