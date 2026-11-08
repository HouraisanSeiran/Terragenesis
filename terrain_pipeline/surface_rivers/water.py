"""Cross-section water placement for bounded offline river geometry."""
import numpy as np
from .bridge import flow_tangent


def safe_water(source, bed, corridor, flowline, receiver, unresolved, max_incision,
               diagnostics=None):
    rows, cols = source.shape
    water = np.full(source.shape, np.nan)
    owner_cells = {}
    stages = np.full(source.size, np.nan)
    incision_strength = source - bed
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
        dz, dx = flow_tangent(cell, receiver, donors, cols, incision_strength)
        length = np.hypot(dz, dx)
        if length == 0.:
            unresolved[cell] = True
            continue
        grid_length = max(abs(dz), abs(dx))
        normal_z, normal_x = dx / grid_length, -dz / grid_length
        sections = []
        for step in range(-2, 3):
            nz, nx = int(round(z + step * normal_z)), int(round(x + step * normal_x))
            if 0 <= nz < rows and 0 <= nx < cols and corridor[nz, nx]:
                sections.append((step, nz, nx))
        stage = float(bed[z, x] + min(.6, .45 * (source[z, x] - bed[z, x])))
        banks = []
        for sign in (-1, 1):
            edge = max(step for step, _, _ in sections) if sign == 1 else min(step for step, _, _ in sections)
            for distance in range(abs(edge) + 1, max(rows, cols) + 1):
                nz = int(round(z + sign * distance * normal_z))
                nx = int(round(x + sign * distance * normal_x))
                if 0 <= nz < rows and 0 <= nx < cols and not corridor[nz, nx]:
                    banks.append(float(bed[nz, nx]))
                    break
        if banks:
            stage = min(stage, min(banks) - .05)
        for _, nz, nx in sections:
            bed[nz, nx] = max(source[nz, nx] - max_incision,
                              min(bed[nz, nx], stage - .15))
        if any(bed[nz, nx] >= stage for _, nz, nx in sections):
            unresolved[cell] = True
            if diagnostics is not None:
                diagnostics.mark_cell("cross_section_bed_above_stage", cell)
            continue
        boundary_target = cell
        while receiver[boundary_target] >= 0:
            boundary_target = int(receiver[boundary_target])
        boundary_z, boundary_x = divmod(boundary_target, cols)
        open_boundary_section = (receiver[boundary_target] < 0
            and min(z, x, rows - 1 - z, cols - 1 - x) <= 3
            and min(boundary_z, boundary_x, rows - 1 - boundary_z, cols - 1 - boundary_x) == 0)
        if len(banks) != 2 and not (banks and open_boundary_section):
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
                stages[target] = stages[cell]
    claims = [[] for _ in range(source.size)]
    for owner, cells in owner_cells.items():
        if not unresolved[owner]:
            for nz, nx in cells:
                claims[nz * cols + nx].append(owner)
    for index, owners in enumerate(claims):
        if owners:
            level = min(stages[o] for o in owners)
            bed.flat[index] = max(source.flat[index] - max_incision, min(bed.flat[index], level - .15))
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
