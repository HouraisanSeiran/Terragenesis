"""Independent finite-graph accumulation (DeepSeek dd4c8df9, input gates reviewed)."""
import numpy as np


def independent_accumulation(receiver, local_q, valid, unknown_seed):
    if (receiver.dtype != np.int64 or local_q.dtype != np.float64 or
            valid.dtype != np.bool_ or unknown_seed.dtype != np.bool_):
        raise TypeError('dtype')
    if receiver.ndim != 2 or local_q.ndim != 2 or valid.ndim != 2 or unknown_seed.ndim != 2:
        raise ValueError('ndim')
    if receiver.shape != local_q.shape or receiver.shape != valid.shape or receiver.shape != unknown_seed.shape:
        raise ValueError('shape')
    n = receiver.size
    if not 1 <= n <= 1787569:
        raise ValueError('independent graph cell budget')
    if not np.all(np.isfinite(local_q)):
        raise ValueError('finite')
    if not np.all(local_q >= 0):
        raise ValueError('nonnegative')
    if np.any((receiver < -1) | (receiver >= n)):
        raise ValueError('receiver range')
    invalid = ~valid
    if np.any(receiver[invalid] != -1) or np.any(local_q[invalid] != 0) or np.any(unknown_seed[invalid]):
        raise ValueError('invalid entries')
    if not valid.ravel()[receiver[valid & (receiver >= 0)]].all():
        raise ValueError('inactive receiver target')
    selfmask = valid & (receiver >= 0) & (receiver == np.arange(n).reshape(receiver.shape))
    if np.any(selfmask):
        raise ValueError('self edge')
    r = receiver.ravel()
    v = valid.ravel()
    q = local_q.ravel().copy()
    dirty = unknown_seed.ravel().copy()
    src = np.flatnonzero(v & (r >= 0))
    tgt = r[src]
    indeg = np.bincount(tgt, minlength=n)
    frontier = np.flatnonzero(v & (indeg == 0))
    processed = 0
    while frontier.size:
        processed += frontier.size
        f = frontier[r[frontier] >= 0]
        targets = r[f]
        np.add.at(q, targets, q[f])
        np.logical_or.at(dirty, targets, dirty[f])
        np.add.at(indeg, targets, -1)
        candidates = np.unique(targets)
        frontier = candidates[indeg[candidates] == 0]
    if processed != int(v.sum()):
        raise ValueError('cycle')
    if not np.all(np.isfinite(q)):
        raise ValueError('nonfinite')
    return q.reshape(local_q.shape), (v & ~dirty).reshape(local_q.shape), processed
