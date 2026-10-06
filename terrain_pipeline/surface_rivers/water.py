"""Cross-section water placement for bounded offline river geometry."""
import numpy as np


def safe_water(source, bed, corridor, flowline, receiver, unresolved, max_incision,
               diagnostics=None):
    rows, cols = source.shape
    water = np.full(source.shape, np.nan)
    owner_cells = {}
    stages = np.full(source.size, np.nan)
    donors = [[] for _ in range(source.size)]
    for cell, target in enumerate(receiver):
        if target >= 0 and flowline.flat[cell]:
            donors[target].append(cell)
    for z, x in zip(*np.nonzero(flowline)):
        cell = z * cols + x
        if unresolved[cell]:
            if diagnostics is not None:
                diagnostics.mark_cell("water_skipped_prior_failure", cell, propagated=True)
            continue
        target = int(receiver[cell])
        if target >= 0:
            tz, tx = divmod(target, cols)
            dz, dx = tz - z, tx - x
        elif donors[cell]:
            uz, ux = divmod(donors[cell][0], cols)
            dz, dx = z - uz, x - ux
        else:
            unresolved[cell] = True
            if diagnostics is not None:
                diagnostics.mark_cell("outlet_without_donor", cell)
            continue
        sections = []
        for step in range(-2, 3):
            nz, nx = z + step * dx, x - step * dz
            if 0 <= nz < rows and 0 <= nx < cols and corridor[nz, nx]:
                sections.append((step, nz, nx))
        stage = float(bed[z, x] + min(.6, .45 * (source[z, x] - bed[z, x])))
        for _, nz, nx in sections:
            if not flowline[nz, nx]:
                bed[nz, nx] = max(source[nz, nx] - max_incision,
                                  min(bed[nz, nx], stage - .15))
        if any(bed[nz, nx] >= stage for _, nz, nx in sections):
            unresolved[cell] = True
            if diagnostics is not None:
                diagnostics.mark_cell("cross_section_bed_above_stage", cell)
            continue
        banks = []
        for sign in (-1, 1):
            edge = max(step for step, _, _ in sections) if sign == 1 else min(step for step, _, _ in sections)
            for distance in range(abs(edge) + 1, abs(edge) + 4):
                nz, nx = z + sign * distance * dx, x - sign * distance * dz
                if 0 <= nz < rows and 0 <= nx < cols and not corridor[nz, nx]:
                    banks.append(float(bed[nz, nx]))
                    break
        if len(banks) != 2 or stage > min(banks) + 1e-6:
            unresolved[cell] = True
            if diagnostics is not None:
                diagnostics.mark_cell("missing_bank" if len(banks) != 2 else
                                      "stage_above_bank", cell)
            continue
        stages[cell] = stage
        owner_cells[cell] = [(nz, nx) for _, nz, nx in sections]
    for cell, target in enumerate(receiver):
        if target >= 0 and flowline.flat[cell] and flowline.flat[target]:
            if not np.isfinite(stages[cell]) or not np.isfinite(stages[target]):
                unresolved[cell] = True
                if diagnostics is not None:
                    diagnostics.mark_cell("stage_missing_neighbor", cell, propagated=True)
            elif stages[target] > stages[cell] + 1e-6:
                unresolved[cell] = unresolved[target] = True
                if diagnostics is not None:
                    diagnostics.mark_cell("stage_reverse", cell)
                    diagnostics.mark_cell("stage_reverse", int(target))
    claims = [[] for _ in range(source.size)]
    for owner, cells in owner_cells.items():
        if not unresolved[owner]:
            for nz, nx in cells:
                claims[nz * cols + nx].append(owner)
    for index, owners in enumerate(claims):
        if owners:
            level = stages[index] if flowline.flat[index] else min(stages[o] for o in owners)
            if level > bed.flat[index] + 1e-6:
                water.flat[index] = level
            else:
                for owner in owners:
                    unresolved[owner] = True
                    if diagnostics is not None:
                        diagnostics.mark_cell("claim_no_clearance", owner)
    for index, owners in enumerate(claims):
        if any(unresolved[o] for o in owners):
            water.flat[index] = np.nan
            if diagnostics is not None:
                diagnostics.mark_cell("claim_owner_failed", index, propagated=True)
    if diagnostics is not None:
        missing = flowline.reshape(-1) & ~np.isfinite(water.reshape(-1)) & ~unresolved
        diagnostics.mark("flowline_without_water", missing.reshape(source.shape), propagated=True)
    unresolved |= flowline.reshape(-1) & ~np.isfinite(water.reshape(-1))
    return water, unresolved.reshape(source.shape)
