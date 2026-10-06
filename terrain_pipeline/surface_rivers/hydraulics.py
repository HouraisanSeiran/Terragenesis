"""Explicit, local hydraulic inputs for the optional branch prototype."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ChannelHydraulics:
    width: float
    depth: float
    roughness: float
    surface_slope: float

    def conveyance(self) -> float:
        """Wide rectangular Manning proxy; all lengths share the grid unit."""
        values = (self.width, self.depth, self.roughness, self.surface_slope)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Hydraulic inputs must be finite")
        if self.width <= 0 or self.depth < 0 or self.roughness <= 0 or self.surface_slope < 0:
            raise ValueError("Invalid channel hydraulics")
        return self.width * self.depth ** (5 / 3) * math.sqrt(self.surface_slope) / self.roughness


@dataclass(frozen=True)
class BranchHydraulics:
    main: ChannelHydraulics
    side: ChannelHydraulics
