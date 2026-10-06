# Bounded three-dimensional river prototype

`RiverNetwork` validates and solves a supplied directed graph of water-surface
centerlines. Nodes and polylines use game-world block coordinates. Flow rates
are block-cubed per second; lake capacity and storage are block-cubed, with
`RiverConfig.stepSeconds` defining the budget interval. The default
`blockMeters=1` is a separate game-space calibration, not a physical inference
from the diffusion input. That input maps 30 m/pixel to 2 horizontal blocks but
roughly 6 m per vertical block, so its visual slopes are anisotropic.

The fixture `verification/hydrology3d/synthetic_network.json` is synthetic.
The library checks graph cycles, nonrising open-channel paths, confluences,
discharge accounting, and finite lake storage. XZ intersections do not join
unless they share a graph node. It does not plan routes, compute channel depth
or cave cover, model pressurized flow, or generate Minecraft terrain. No default
world preset uses it.
