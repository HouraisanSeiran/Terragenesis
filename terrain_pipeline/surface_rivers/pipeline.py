"""Versioned offline surface-routing product; independent of the game generator."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from .contracts import GridInput
from terrain_pipeline.drainage import route as route
from terrain_pipeline.drainage import accumulate as accumulate
from terrain_pipeline.channel_geometry import carve_channels
from .postvalidate import geometry_issues

RECIPE = "surface-routing-irregular-channel-v6"


@dataclass(frozen=True)
class SurfaceRiverProduct:
    input_height: np.ndarray
    height: np.ndarray
    vdm_dy: np.ndarray
    water_surface: np.ndarray
    discharge: np.ndarray
    receiver: np.ndarray
    channel_mask: np.ndarray
    flowline_mask: np.ndarray
    width_blocks: np.ndarray
    unresolved_mask: np.ndarray
    outlet_mask: np.ndarray
    metadata: dict


def process(grid: GridInput, threshold_q: float, max_incision: float = 4.0,
            diagnostics=None) -> SurfaceRiverProduct:
    routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks,
                    origin_world_xz=grid.origin, world_seed=grid.world_seed)
    budget = accumulate(routing, grid.runoff, grid.spacing_blocks)
    if abs(budget.residual) > 1e-7 * max(1.0, budget.input_total):
        raise AssertionError("Surface drainage did not conserve input flow")
    channels = carve_channels(grid.height, routing.receiver, routing.order,
                              budget.discharge, grid.spacing_blocks,
                              threshold_q, max_incision, diagnostics)
    leak, disconnected = geometry_issues(channels.height, channels.water_surface,
                                         channels.flowline_mask,
                                         routing.receiver.reshape(grid.height.shape),
                                         grid.outlet_mask)
    unresolved = channels.unresolved_mask | leak | disconnected
    if diagnostics is not None:
        diagnostics.mark("postvalidate_leak", leak, propagated=True)
        diagnostics.mark("postvalidate_disconnected", disconnected, propagated=True)
    water = channels.water_surface.copy()
    water[unresolved] = np.nan
    channels = type(channels)(channels.height, water, channels.channel_mask,
                              channels.flowline_mask, channels.width_blocks,
                              channels.incision,
                              unresolved)
    raw = grid.height.astype(np.float64)
    height = channels.height
    metadata = {
        "recipe": RECIPE,
        "routing_algorithm": "irregular_Delaunay_priority_flood_v1",
        "world_seed": int(grid.world_seed),
        "origin_world_xz": list(grid.origin),
        "spacing_blocks": grid.spacing_blocks,
        "threshold_q": threshold_q,
        "max_incision": max_incision,
        "input_total": budget.input_total,
        "outlet_total": budget.outlet_total,
        "residual": budget.residual,
        "unresolved_cells": int(channels.unresolved_mask.sum()),
        "leak_cells": int(leak.sum()),
        "disconnected_flowline_cells": int(disconnected.sum()),
        "complete_water_surface": not bool(channels.unresolved_mask.any()),
        "limitation": "bounded window with explicit outlets; unresolved water is not a completed river",
    }
    return SurfaceRiverProduct(raw, height, height - raw, channels.water_surface,
                               budget.discharge.astype(np.float64),
                               routing.receiver.reshape(raw.shape), channels.channel_mask,
                               channels.flowline_mask, channels.width_blocks,
                               channels.unresolved_mask, grid.outlet_mask, metadata)


def save(path: Path, product: SurfaceRiverProduct) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "input_height": product.input_height,
        "processed_height": product.height,
        "vdm_dy": product.vdm_dy,
        "water_surface": product.water_surface,
        "discharge": product.discharge,
        "receiver": product.receiver,
        "channel_mask": product.channel_mask,
        "flowline_mask": product.flowline_mask,
        "width_blocks": product.width_blocks,
        "unresolved_mask": product.unresolved_mask,
        "outlet_mask": product.outlet_mask,
        "metadata": np.array(json.dumps(product.metadata, sort_keys=True)),
    }
    with target.open("xb") as output:
        np.savez_compressed(output, **payload)
