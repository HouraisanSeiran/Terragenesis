"""Deterministic offline surface drainage on a height grid."""

from .contracts import AccumulationResult, GridInput, RoutingResult
from .drainage import accumulate, channel_mask, route

__all__ = ["AccumulationResult", "GridInput", "RoutingResult", "accumulate", "channel_mask", "route"]
