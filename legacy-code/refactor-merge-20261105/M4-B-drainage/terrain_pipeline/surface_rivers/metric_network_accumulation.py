"""Deterministic diagnostic discharge on a bounded, assembled receiver graph.

The caller certifies receiver consistency across tiles. This module neither routes
terrain nor infers natural outlets. Known contributions and upstream completeness
are distinct; no storage, physical time integration or hydraulic certification is
provided. Canonical flat-index wave ordering makes storage/load order irrelevant.
"""
import math

import numpy as np


MAX_NETWORK_CELLS = 16_777_216


def accumulate_network_discharge(receiver, local_q_m3_s, valid_mask, *,
                                 terminal_kind, upstream_unknown_mask=None,
                                 max_cells=MAX_NETWORK_CELLS):
    """Sum each valid cell's local m3/s once over the finite joint topology.

    ``upstream_unknown_mask`` marks missing external contributions; it propagates
    downstream without inventing water. ``terminal_kind`` describes where known
    water ends, independently of whether its upstream catchment is complete.
    Inputs are never modified; illegal topology, budgets and overflow are refused.
    """
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError('max_cells must be a positive integer')
    if (not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64
            or receiver.ndim != 2 or not 1 <= receiver.size <= max_cells):
        raise ValueError('bounded nonempty int64 [z,x] receiver required')
    shape = receiver.shape
    for array, dtype, label in ((local_q_m3_s, np.float64, 'local_q_m3_s'),
                                (valid_mask, np.bool_, 'valid_mask')):
        if not isinstance(array, np.ndarray) or array.dtype != dtype or array.shape != shape:
            raise ValueError(label + ' must have matching shape and exact dtype')
    if (not isinstance(terminal_kind, np.ndarray) or terminal_kind.shape != shape
            or terminal_kind.dtype.kind != 'U'):
        raise ValueError('matching Unicode terminal_kind array required')
    if not valid_mask.any():
        raise ValueError('at least one valid cell required')
    if not np.isfinite(local_q_m3_s).all() or np.any(local_q_m3_s < 0):
        raise ValueError('local_q_m3_s must be finite and nonnegative')
    if np.any(local_q_m3_s[~valid_mask] != 0) or np.any(receiver[~valid_mask] != -1):
        raise ValueError('inactive cells must have zero local Q and receiver -1')
    if upstream_unknown_mask is None:
        dirty = np.zeros(receiver.size, bool)
    else:
        if (not isinstance(upstream_unknown_mask, np.ndarray)
                or upstream_unknown_mask.dtype != np.bool_
                or upstream_unknown_mask.shape != shape):
            raise ValueError('matching boolean upstream_unknown_mask required')
        if np.any(upstream_unknown_mask[~valid_mask]):
            raise ValueError('inactive cells cannot seed unknown upstream')
        dirty = upstream_unknown_mask.ravel().copy()

    rec = receiver.ravel()
    valid = valid_mask.ravel()
    kinds = terminal_kind.ravel()
    n = rec.size
    if np.any(rec < -1) or np.any(rec >= n):
        raise ValueError('receiver index outside grid')
    live = valid & (rec >= 0)
    sources = np.flatnonzero(live)
    targets = rec[sources]
    if np.any(sources == targets) or np.any(~valid[targets]):
        raise ValueError('self receiver or inactive receiver target')
    terminal = valid & ~live
    if np.any(kinds[~valid] != 'inactive') or np.any(kinds[live] != 'interior'):
        raise ValueError('inactive and nonterminal policy mismatch')
    if not np.isin(kinds[terminal], ('retained', 'open_outflow', 'unknown_boundary')).all():
        raise ValueError('terminal destination must be declared')

    def finite_sum(values, label):
        with np.errstate(over='ignore', invalid='ignore'):
            total = float(np.sum(values, dtype=np.float64))
        if not math.isfinite(total):
            raise ValueError(label + ' overflows float64')
        return total

    input_total = finite_sum(local_q_m3_s, 'input total')
    flow = local_q_m3_s.ravel().copy()
    pending = np.bincount(targets, minlength=n).astype(np.int64, copy=False)
    frontier = np.flatnonzero(valid & (pending == 0))
    processed = 0
    while frontier.size:
        processed += int(frontier.size)
        src = frontier[rec[frontier] >= 0]
        dst = rec[src]
        if not src.size:
            break
        # Sources are settled before receivers. Repeated confluences must count
        # every donor; fancy-index -= silently drops duplicate decrements.
        with np.errstate(over='ignore', invalid='ignore'):
            np.add.at(flow, dst, flow[src])
        if not np.isfinite(flow[dst]).all():
            raise ValueError('routed known discharge overflows float64')
        np.logical_or.at(dirty, dst, dirty[src])
        np.subtract.at(pending, dst, 1)
        frontier = np.unique(dst[pending[dst] == 0])
    valid_count = int(valid.sum())
    if processed != valid_count:
        raise ValueError('receiver graph contains a cycle')

    terminal_q = np.where(terminal, flow, 0.)
    totals = {kind: finite_sum(terminal_q[kinds == kind], kind)
              for kind in ('retained', 'open_outflow', 'unknown_boundary')}
    # Subtract individually: adding the terminal totals first can overflow even
    # when each input total and the physically zero residual are representable.
    residual = input_total
    for kind in ('retained', 'open_outflow', 'unknown_boundary'):
        residual -= totals[kind]
    if not math.isfinite(residual):
        raise ValueError('water balance residual overflows float64')
    return {
        'known_routed_q_m3_s': flow.reshape(shape),
        'complete_mask': (valid & ~dirty).reshape(shape),
        'terminal_q_m3_s': terminal_q.reshape(shape),
        'input_total_m3_s': input_total,
        'open_outflow_m3_s': totals['open_outflow'],
        'retained_m3_s': totals['retained'],
        'unknown_pending_m3_s': totals['unknown_boundary'],
        'residual_m3_s': residual,
        'valid_cells': valid_count,
        'processed_cells': processed,
        'policy': 'finite_joint_graph_known_discharge_canonical_waves_v1',
    }
