"""Area-based channel evidence on an existing irregular receiver DAG."""
import numpy as np
from .metric_lowland_runoff import LowlandRunoffConfig, lowland_geometry, _close, _first_object


def classify_saved_graph(height, land, receiver, upstream_order, contributing_cells, spacing_m, *, config=None):
    """Return channels and first downstream capture; all runoff stays on the saved DAG.

    Area is a unit-runoff proxy, not evidence of calibrated perennial discharge.
    The supplied order must be upstream first. No receiver is changed.
    """
    config = config or LowlandRunoffConfig()
    height = np.asarray(height)
    land = np.asarray(land, dtype=bool).ravel()
    receiver = np.asarray(receiver).ravel()
    order = np.asarray(upstream_order).ravel()
    area = np.asarray(contributing_cells).ravel()
    if height.ndim != 2 or any(a.size != height.size for a in (land, receiver, order, area)):
        raise ValueError('incompatible graph and terrain')
    relief, slope, lowland = lowland_geometry(height, spacing_m, config)
    threshold = np.where(lowland.ravel(), config.lowland_initiation_area_m2,
                         config.upland_initiation_area_m2)
    seeds = land & (area * float(spacing_m ** 2) >= threshold)
    channel = _close(seeds, receiver, order) & land
    owner, _ = _first_object(channel.astype(np.uint8), receiver, order)
    return dict(lowland=lowland, relief=relief, slope=slope,
                channel=channel, capture=owner)
