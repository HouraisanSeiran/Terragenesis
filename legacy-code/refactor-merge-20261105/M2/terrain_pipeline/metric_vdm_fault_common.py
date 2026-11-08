"""Shared recipe and selection weights for the current metric VDM fault."""

from dataclasses import dataclass
import math

import numpy as np


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class FaultRecipe:
    plane_origin_xz_m: tuple
    strike_degrees: float
    slip_m: float
    moving_side: str
    transition_width_m: float

    def __post_init__(self):
        if not isinstance(self.plane_origin_xz_m, tuple) or len(self.plane_origin_xz_m) != 2:
            raise ValueError("invalid plane origin")
        for value in self.plane_origin_xz_m:
            _finite(value, "plane origin")
        _finite(self.strike_degrees, "strike")
        _finite(self.slip_m, "slip")
        if self.moving_side not in ("positive", "negative"):
            raise ValueError("moving_side must be positive or negative")
        _finite(self.transition_width_m, "transition width")
        if self.transition_width_m <= 0:
            raise ValueError("transition width must be positive")


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def _selection_weights(reference, selection, width):
    """Keep the original metric mask-distance arithmetic unchanged."""
    rows, columns = selection.shape
    distances = np.full(selection.shape, np.inf, np.float64)
    outside = np.argwhere(~selection)
    if len(outside):
        inside = np.argwhere(selection)
        for row, column in inside:
            distances[row, column] = np.min(np.hypot(outside[:, 0] - row, outside[:, 1] - column))
    spacing = []
    horizontal = reference[:, :, (0, 2)]
    if rows > 1:
        spacing.extend(np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel().tolist())
    if columns > 1:
        spacing.extend(np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel().tolist())
    metre_spacing = float(np.median(spacing)) if spacing else 1.
    weights = np.where(selection, _smooth(distances * metre_spacing / width), 0.)
    return weights.reshape(-1)
