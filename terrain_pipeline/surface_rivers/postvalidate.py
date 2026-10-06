"""Final geometry checks independent of routing and carving."""
from collections import deque
import numpy as np


def geometry_issues(height, water, flowline, receiver, outlet_mask):
    wet = np.isfinite(water)
    rows, cols = wet.shape
    leak = wet & (water <= height + 1e-6)
    for cell, target in enumerate(np.asarray(receiver).reshape(-1)):
        if target >= 0 and wet.flat[cell] and wet.flat[target]:
            if water.flat[target] > water.flat[cell] + 1e-6:
                leak.flat[cell] = leak.flat[target] = True
    for z, x in zip(*np.nonzero(wet)):
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if 0 <= nz < rows and 0 <= nx < cols and not wet[nz, nx]:
                if height[nz, nx] < water[z, x] - 1e-6:
                    leak[z, x] = True
    seen = np.zeros(wet.shape, bool)
    todo = deque(map(tuple, np.argwhere(wet & outlet_mask)))
    for z, x in todo:
        seen[z, x] = True
    while todo:
        z, x = todo.popleft()
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if 0 <= nz < rows and 0 <= nx < cols and wet[nz, nx] and not seen[nz, nx]:
                seen[nz, nx] = True
                todo.append((nz, nx))
    return leak, flowline & ~seen
