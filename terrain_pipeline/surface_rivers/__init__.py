"""Deterministic offline surface drainage on a height grid."""

from .contracts import AccumulationResult, GridInput, RoutingResult
from terrain_pipeline.drainage import accumulate as accumulate
from terrain_pipeline.drainage import channel_mask as channel_mask
from terrain_pipeline.drainage import route as route

__all__ = ["AccumulationResult", "GridInput", "RoutingResult", "accumulate", "channel_mask", "route"]
