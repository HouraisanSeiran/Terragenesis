"""Invariant checks for native routing and event products (pure numpy, read-only)."""
import numpy as np


def check_routing(order, receiver, valid):
    """Return a dict of violations; empty 'errors' means the routing is consistent.

    order: valid cells with each receiver BEFORE its sources (downstream first; verified on
    native-final-routing-v1, where all receivers have smaller rank than their source).
    receiver: downstream cell index per cell, -1 for none.
    valid: boolean mask over all cells.
    """
    order = np.asarray(order)
    receiver = np.asarray(receiver)
    valid = np.asarray(valid).ravel().astype(bool)
    errors = []
    n = valid.size
    result = dict(cells=int(n), valid_cells=int(valid.sum()), order_size=int(order.size))
    negative = int(np.count_nonzero(order < 0))
    result['order_negative'] = negative
    if negative:
        errors.append('order contains %d negative entries (unfilled -1 tail)' % negative)
    if int(order.size) != int(valid.sum()):
        errors.append('order size %d != valid cell count %d' % (order.size, int(valid.sum())))
    in_range = order[(order >= 0) & (order < n)]
    if in_range.size != order.size - negative:
        errors.append('order has entries >= n')
    rank = np.full(n, -1, dtype='i8')
    if not negative and in_range.size == order.size:
        if np.unique(in_range).size != in_range.size:
            errors.append('order has duplicate cells')
        elif not np.all(valid[in_range]):
            errors.append('order contains invalid cells')
        else:
            rank[in_range] = np.arange(in_range.size)
            if int(np.count_nonzero(valid & (rank < 0))):
                errors.append('valid cells missing from order')
    if not errors:
        target = receiver[order]
        has = target >= 0
        if np.any(target[has] >= n):
            errors.append('receiver index out of range')
        else:
            src_rank = np.arange(order.size)[has]
            tgt_rank = rank[target[has]]
            bad = int(np.count_nonzero(tgt_rank >= src_rank))
            result['receiver_not_downstream'] = bad
            if bad:
                errors.append('%d receivers do not precede their source in order' % bad)
    result['errors'] = errors
    result['ok'] = not errors
    return result


def check_event_budget(manifest, rtol=1e-9):
    """Check per-interval water budgets in an event manifest dict."""
    errors = []
    budgets = manifest.get('budgets')
    if budgets is None:
        budgets = [dict(local_m3=manifest.get('local_m3'), retained_m3=manifest.get('retained_m3'), terminal_m3=manifest.get('terminal_m3'), residual_m3=manifest.get('residual_m3'))]
    rows = []
    for i, b in enumerate(budgets):
        local = b.get('local_m3')
        residual = b.get('residual_m3')
        if local is None or residual is None:
            errors.append('interval %d lacks local_m3/residual_m3' % i)
            continue
        ratio = abs(residual) / local if local else float('inf') if residual else 0.
        rows.append(dict(interval=i, local_m3=local, residual_m3=residual, relative=ratio))
        if not np.isfinite(local) or not np.isfinite(residual):
            errors.append('interval %d non-finite' % i)
        elif abs(residual) > rtol * abs(local):
            errors.append('interval %d |residual| %.6g exceeds %.1e x local %.6g' % (i, abs(residual), rtol, local))
        for key in ('retained_m3', 'terminal_m3'):
            value = b.get(key)
            if value is not None and not (value >= 0):
                errors.append('interval %d %s negative or NaN: %r' % (i, key, value))
    return dict(intervals=rows, errors=errors, ok=not errors, rtol=rtol)
