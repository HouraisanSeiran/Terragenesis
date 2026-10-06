"""Face connections for diagonally routed channels; validated after placement."""
import numpy as np


def bridge_diagonals(source, bed, water, corridor, flowline, receiver, max_incision,
                     diagnostics=None):
    rows, cols = source.shape
    bed, water, corridor = bed.copy(), water.copy(), corridor.copy()
    bad = []
    for cell, target in enumerate(receiver):
        if target < 0 or not flowline.flat[cell] or not flowline.flat[target]:
            continue
        z, x = divmod(cell, cols)
        tz, tx = divmod(int(target), cols)
        if abs(tz - z) != 1 or abs(tx - x) != 1:
            continue
        if not (np.isfinite(water[z, x]) and np.isfinite(water[tz, tx])):
            bad.append((cell, int(target)))
            if diagnostics is not None:
                diagnostics.mark_cell("bridge_missing_water", cell, propagated=True)
            continue
        options = []
        for bz, bx in ((z, tx), (tz, x)):
            stage = min(float(water[z, x]), float(water[tz, tx]))
            if flowline[bz, bx]:
                if np.isfinite(water[bz, bx]) and stage <= water[bz, bx] <= water[z, x]:
                    options.append((0., bz, bx, bed[bz, bx], water[bz, bx]))
                continue
            desired = min(float(bed[bz, bx]), stage - .15)
            cut_bed = max(float(source[bz, bx]) - max_incision, desired)
            if cut_bed < stage - 1e-6:
                options.append((float(bed[bz, bx] - cut_bed), bz, bx, cut_bed, stage))
        if not options:
            bad.append((cell, int(target)))
            if diagnostics is not None:
                diagnostics.mark_cell("bridge_no_face_option", cell)
            continue
        _, bz, bx, cut_bed, stage = min(options)
        bed[bz, bx], corridor[bz, bx] = cut_bed, True
        water[bz, bx] = stage
    return bed, water, corridor, bad
