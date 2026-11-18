"""Face-connected raster support for finite graph edges; bounded after placement."""
import numpy as np


def flow_tangent(cell, receiver, donors, cols, strength):
    """Smooth raster section orientation across short irregular graph steps."""
    upstream = downstream = cell
    for _ in range(3):
        if receiver[downstream] >= 0:
            downstream = int(receiver[downstream])
        if donors[upstream]:
            upstream = max(donors[upstream], key=lambda node: strength.flat[node])
    uz, ux = divmod(upstream, cols)
    dz, dx = divmod(downstream, cols)
    return dz - uz, dx - ux


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
        if abs(tz - z) + abs(tx - x) <= 1:
            continue
        if not (np.isfinite(water[z, x]) and np.isfinite(water[tz, tx])):
            bad.append((cell, int(target)))
            if diagnostics is not None:
                diagnostics.mark_cell("bridge_missing_water", cell, propagated=True)
            continue
        stage = min(float(water[z, x]), float(water[tz, tx]))
        steps = max(abs(tz - z), abs(tx - x))
        anchors = [(int(round(z + step * (tz - z) / steps)),
                    int(round(x + step * (tx - x) / steps))) for step in range(steps + 1)]
        edits = []
        failed = False

        def candidate(bz, bx):
            if flowline[bz, bx]:
                if np.isfinite(water[bz, bx]) and stage <= water[bz, bx] <= water[z, x]:
                    return (0., bz, bx, bed[bz, bx], water[bz, bx])
                return None
            desired = min(float(bed[bz, bx]), stage - .15)
            cut_bed = max(float(source[bz, bx]) - max_incision, desired)
            if cut_bed < stage - 1e-6:
                return (float(bed[bz, bx] - cut_bed), bz, bx, cut_bed, stage)
            return None

        for index in range(1, len(anchors)):
            pz, px = anchors[index - 1]
            bz, bx = anchors[index]
            if abs(bz - pz) == 1 and abs(bx - px) == 1:
                options = [option for option in (candidate(pz, bx), candidate(bz, px)) if option is not None]
                if not options:
                    failed = True
                    break
                edits.append(min(options))
            if index < len(anchors) - 1:
                option = candidate(bz, bx)
                if option is None:
                    failed = True
                    break
                edits.append(option)
        if failed:
            bad.append((cell, int(target)))
            if diagnostics is not None:
                diagnostics.mark_cell("bridge_no_face_option", cell)
            continue
        for _, bz, bx, cut_bed, level in edits:
            bed[bz, bx], corridor[bz, bx] = cut_bed, True
            water[bz, bx] = level
    return bed, water, corridor, bad
