# Regional terrain processing

`RegionProcessor.process` accepts row-major absolute Minecraft Y values sampled
every two world blocks, plus an optional protection mask. It leaves the raw
height array unchanged and returns separate derived heights, four continuous
weights in plain/hill/plateau/mountain order, and a dominant type per sample.
The derived height can be stored as `base = raw Y` and `dy = processed Y - base`;
`dx = dz = 0`. It does not create caves or underground geology.

The broad trend and local roughness use radius-24, sigma-8 Gaussian filters;
the local smoothing uses radius-6, sigma-2. Trend slope extends the maximum
support to 25 samples (50 world blocks). A caller must supply 25 samples of
halo around every published area. Only its interior is window-independent.
No per-region min/max normalization is used. The optional mask protects known
external features; this processor does not identify or protect rivers on its own.
Coast protection fades inland from submerged samples. Processing identity is
`ProcessingConfig.ID`; change it whenever these fixed parameters change.

Classification is based on the broad elevation trend, its slope, and local
height variance. This first version has no global intent noise. Lowland isolated
peaks can still lose a few blocks; on the saved lowland sample the highest point
loses about 3 blocks, while the saved mountain maximum is unchanged. The
50-block support cannot flatten terrain at kilometer scale.

Responsibilities are separated into `RegionFeatures` (filtered measurements),
`LandformClassifier` (continuous weights), `SurfaceProtection` (coast, external
mask, and summit protection), and `LandformPolicies` (weighted height change).
`RegionProcessor` validates and coordinates these stages. This structural split
preserves the original operation order: the three saved real-sample outputs,
including heights and weights, compare bit for bit with the earlier version.
