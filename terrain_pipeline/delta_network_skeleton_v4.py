"""Channel skeleton for the complex delta network v4.

v4 changes only the land building (``delta_network_terrain_v4``): the review of v3 against the reference
images found the skeleton (loops, levels, mouths, junction density) inside the reference range, so the
skeleton is the v3 skeleton, re-exported under the v4 name.  Same parameters -> the same graph as v3
(identical seeds: the seed purposes keep their v3 names, so v3 and v4 share one skeleton per variant).
"""
from __future__ import annotations

from terrain_pipeline import delta_network_skeleton_v3 as _sk3
from terrain_pipeline.delta_network_skeleton_v3 import (  # noqa: F401
    NODE_KINDS, activity_profile, edge_points, event_profile, skeleton_metrics_v3, validate_graph, width_of)

DeltaParamsV4 = _sk3.DeltaParamsV3
build_delta_network_v4 = _sk3.build_delta_network_v3
skeleton_metrics_v4 = _sk3.skeleton_metrics_v3

__all__ = ['DeltaParamsV4', 'build_delta_network_v4', 'skeleton_metrics_v4', 'validate_graph', 'activity_profile',
           'event_profile', 'edge_points', 'width_of', 'NODE_KINDS']
