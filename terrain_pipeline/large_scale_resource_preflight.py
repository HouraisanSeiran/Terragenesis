"""Resource gates for large surface-network experiments.

The preflight deliberately distinguishes bounded terrain reads from global
routing state.  It prevents a 4096² run from being mistaken for a streamed
solver when the current benchmark still keeps graph arrays in memory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResourcePreflight:
    size: int
    cells: int
    terrain_windowed: bool
    graph_state_bytes: int
    estimated_peak_bytes: int
    max_bytes: int
    runnable: bool
    reason: str


def estimate_graph_state_bytes(size: int) -> int:
    if type(size) is not int or size < 2:
        raise ValueError("size must be an integer >= 2")
    cells = size * size
    # receiver int64, indegree int32, order int64, accumulation float64,
    # river_id int64, plus a conservative 20% allocator/intermediate margin.
    canonical = cells * (8 + 4 + 8 + 8 + 8)
    return (canonical * 120 + 99) // 100


def preflight(size: int, *, max_mib: int = 512) -> ResourcePreflight:
    if type(max_mib) is not int or max_mib <= 0:
        raise ValueError("max_mib must be positive")
    cells = size * size
    graph_state = estimate_graph_state_bytes(size)
    max_bytes = max_mib * 1024 * 1024
    runnable = graph_state <= max_bytes
    reason = ("within current global-state budget"
              if runnable else
              "requires streamed graph state before full benchmark")
    return ResourcePreflight(size, cells, True, graph_state, graph_state,
                             max_bytes, runnable, reason)


def report(size: int, *, max_mib: int = 512) -> dict:
    return asdict(preflight(size, max_mib=max_mib))
