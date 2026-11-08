"""Grid units and immutable result contracts for offline drainage."""

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class GridInput:
    height: np.ndarray
    spacing_blocks: float
    origin: tuple[float, float]
    runoff: np.ndarray
    outlet_mask: np.ndarray
    world_seed: int = 20261020

    def __post_init__(self) -> None:
        height = np.asarray(self.height, dtype=np.float64)
        runoff = np.asarray(self.runoff, dtype=np.float64)
        outlets = np.asarray(self.outlet_mask, dtype=np.bool_)
        if height.ndim != 2 or min(height.shape) < 1 or runoff.shape != height.shape or outlets.shape != height.shape:
            raise ValueError("height, runoff, and outlet_mask must share a nonempty 2D shape")
        if not np.isfinite(height).all() or not np.isfinite(runoff).all() or (runoff < 0).any():
            raise ValueError("height and nonnegative runoff must be finite")
        if not np.isfinite(self.spacing_blocks) or self.spacing_blocks <= 0:
            raise ValueError("spacing_blocks must be finite and positive")
        if len(self.origin) != 2 or not np.isfinite(self.origin).all():
            raise ValueError("origin must contain two finite world coordinates")
        if (not isinstance(self.world_seed, (int, np.integer))
                or isinstance(self.world_seed, (bool, np.bool_))):
            raise ValueError("world_seed must be an integer")
        if not outlets.any():
            raise ValueError("At least one explicit outlet is required")
        height = height.copy()
        runoff = runoff.copy()
        outlets = outlets.copy()
        height.flags.writeable = False
        runoff.flags.writeable = False
        outlets.flags.writeable = False
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "runoff", runoff)
        object.__setattr__(self, "outlet_mask", outlets)


@dataclass(frozen=True)
class RoutingResult:
    receiver: np.ndarray  # Flattened cell index; -1 only for explicit outlets.
    order: np.ndarray  # Downstream-first flattened cell indices.
    routing_height: np.ndarray  # Working filled height; original input is unchanged.
    outlet_mask: np.ndarray
    spacing_blocks: float


@dataclass(frozen=True)
class AccumulationResult:
    discharge: np.ndarray  # Volume per time at each cell, including upstream inputs.
    outlet_discharge: np.ndarray  # Same shape, zero except at explicit outlets.
    input_total: float
    outlet_total: float
    residual: float
