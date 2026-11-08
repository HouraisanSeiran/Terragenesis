"""Graph-dependent building blocks for split native derived hydrology.

This module is incomplete: checkpointed phase entry points are not yet provided.
"""
import numpy as np
from numba import njit

from terrain_pipeline.new_world_stage1 import _label_pools


@njit(cache=True)
def graph_dependent_stage(bed, valid, ocean, unknown, filled, rank, ptr, edges,
                          rows, cols, labels, stack, anchors, capacity, counts,
                          spill, seeds):
    """Accumulate pool statistics in reference DFS order and ingress seeds.

    ``labels`` must already contain the result of ``_label_pools`` and the
    four pool arrays must have exactly the returned pool count. All arrays are
    caller-owned, allowing the graph and stack to be unmapped after this call.
    """
    n = bed.size
    for start in range(n):
        label = labels[start]
        if label < 0:
            continue
        anchors[label] = start
        capacity[label] = 0.
        counts[label] = 0
        spill[label] = filled[start]
        labels[start] = -label - 2
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            counts[label] += 1
            capacity[label] += (filled[cell] - bed[cell]) * 900.
            if rank[cell] < rank[anchors[label]]:
                anchors[label] = cell
            for edge in range(ptr[cell], ptr[cell + 1]):
                target = edges[edge]
                if labels[target] == label:
                    labels[target] = -label - 2
                    stack[size] = target
                    size += 1
    for cell in range(n):
        if labels[cell] < -1:
            labels[cell] = -labels[cell] - 2
    seeds[:] = False
    for cell in range(n):
        if not valid[cell]:
            continue
        if unknown[cell]:
            seeds[cell] = True
        if not ocean[cell]:
            for edge in range(ptr[cell], ptr[cell + 1]):
                neighbor = edges[edge]
                if not valid[neighbor] or unknown[neighbor]:
                    seeds[cell] = True
            row, col = cell // cols, cell % cols
            if row == 0 or col == 0 or row == rows - 1 or col == cols - 1:
                seeds[cell] = True
                for edge in range(ptr[cell], ptr[cell + 1]):
                    neighbor = edges[edge]
                    if valid[neighbor] and not ocean[neighbor]:
                        seeds[neighbor] = True
