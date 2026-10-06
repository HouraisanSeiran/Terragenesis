"""Group a continuous coastal raw window by first ocean crossing."""

import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.surface_rivers import route
from tools.diagnose_river_feasibility import _boundary_connected_ocean

WINDOW = ROOT / "verification/river-feasibility/extended-20260929T114427548312Z"


def main():
    raw = next(WINDOW.glob("*size1025.npz"))
    with np.load(raw, allow_pickle=False) as archive:
        height = archive["elevation"].astype(np.float64)
    rows, cols = height.shape
    ocean = _boundary_connected_ocean(height, 0.)
    if not ocean.any():
        raise ValueError("No boundary-connected ocean")
    routing = route(height, ocean, 30.)
    land = height > 0
    land_flat = land.ravel()
    mouth = np.full(height.size, -1, dtype=np.int64)
    donors = np.zeros(height.size, dtype=np.uint8)
    for cell in routing.order:
        target = routing.receiver[cell]
        mouth[cell] = cell if ocean.flat[cell] else (mouth[target] if target >= 0 else -1)
        if target >= 0 and land_flat[cell] and land_flat[target]:
            donors[target] += 1
    boundary = np.zeros(height.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    land_ids = mouth[land_flat]
    valid = land_ids >= 0
    counts = np.bincount(land_ids[valid], minlength=height.size)
    edge_ids = mouth[(land & boundary).ravel()]
    edge_counts = np.bincount(edge_ids[edge_ids >= 0], minlength=height.size)
    junction_ids = mouth[land_flat & (donors >= 2)]
    junction_counts = np.bincount(junction_ids[junction_ids >= 0], minlength=height.size)
    outlets = np.flatnonzero(counts)
    ranked = sorted(outlets, key=lambda cell: (-int(counts[cell]), int(cell)))
    fill = routing.routing_height - height
    groups = []
    for outlet in ranked:
        members = (mouth == outlet) & land_flat
        z, x = divmod(int(outlet), cols)
        group = {"first_ocean_cell_grid_zx": [z, x],
                 "land_cells": int(counts[outlet]),
                 "land_boundary_cells": int(edge_counts[outlet]),
                 "observed_window_closed": bool(edge_counts[outlet] == 0),
                 "land_d8_donor_junction_cells": int(junction_counts[outlet]),
                 "working_fill_max_m": float(fill.ravel()[members].max()),
                 "working_fill_cells": int(np.count_nonzero(fill.ravel()[members] > 1e-9)),
                 "land_relief_m": float(np.ptp(height.ravel()[members]))}
        groups.append(group)
    report = {"raw_npz": raw.name, "shape": list(height.shape),
              "land_cells": int(np.count_nonzero(land)),
              "boundary_connected_ocean_cells": int(np.count_nonzero(ocean)),
              "unassigned_land_cells": int(np.count_nonzero(~valid)),
              "mouth_count": len(groups),
              "junction_note": "at least two land D8 donors; no discharge threshold or two-river test",
              "closure_note": "No land-boundary contact is only observed window closure, not proof of global watershed completeness",
              "mouths": groups}
    (WINDOW / "catchments.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for group in groups[:5]:
        print(group, flush=True)
    closed = [group for group in groups if group["observed_window_closed"]]
    print("closed_count", len(closed), "largest_closed", closed[0] if closed else None)
    if not closed:
        return
    candidate = closed[0]
    cz, cx = candidate["first_ocean_cell_grid_zx"]
    outlet = cz * cols + cx
    cells = (mouth == outlet) & land_flat
    discharge = np.zeros(height.size, dtype=np.float64)
    discharge[cells] = 30. ** 2 * 1e-8
    for cell in routing.order[::-1]:
        target = routing.receiver[cell]
        if cells[cell] and target >= 0:
            discharge[target] += discharge[cell]
    fill_flat = fill.ravel()
    deepest = np.flatnonzero(cells)[np.argmax(fill_flat[cells])]
    dz, dx = divmod(int(deepest), cols)
    filled = cells & (fill_flat > 1e-9)
    component = np.zeros(height.size, dtype=bool)
    stack = [int(deepest)]
    while stack:
        cell = stack.pop()
        if component[cell] or not filled[cell]:
            continue
        component[cell] = True
        z, x = divmod(cell, cols)
        for zz, xx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if 0 <= zz < rows and 0 <= xx < cols:
                neighbor = zz * cols + xx
                if filled[neighbor] and not component[neighbor]:
                    stack.append(neighbor)
    exit_cell = int(deepest)
    while routing.receiver[exit_cell] >= 0 and component[routing.receiver[exit_cell]]:
        exit_cell = int(routing.receiver[exit_cell])
    next_cell = int(routing.receiver[exit_cell])
    ez, ex = divmod(exit_cell, cols)
    nz, nx = divmod(next_cell, cols) if next_cell >= 0 else (-1, -1)
    positions = np.flatnonzero(cells)
    zs, xs = np.divmod(positions, cols)
    budget_rows = []
    for threshold in (.05, .02, .01, .005, .002):
        active = cells & (discharge >= threshold)
        channel_donors = np.zeros(height.size, dtype=np.uint8)
        for cell in routing.order:
            target = routing.receiver[cell]
            if active[cell] and target >= 0 and active[target]:
                channel_donors[target] += 1
        working = height.ravel().copy()
        for cell in routing.order[::-1]:
            target = routing.receiver[cell]
            if active[cell] and target >= 0 and (active[target] or target == outlet):
                working[target] = min(working[target], working[cell] - .01)
        cut = height.ravel()[active] - working[active]
        budget_rows.append({"threshold_m3_per_s": threshold,
                            "channel_land_cells": int(np.count_nonzero(active)),
                            "two_channel_donor_junctions": int(np.count_nonzero(active & (channel_donors >= 2))),
                            "bed_only_fixed_route_cut_max_m": float(cut.max()) if cut.size else 0.,
                            "bed_only_fixed_route_cut_p90_m": float(np.quantile(cut, .9)) if cut.size else 0.,
                            "bed_only_fixed_route_cut_above_4m_cells": int(np.count_nonzero(cut > 4. + 1e-9))})
    planning = {"selection": "largest observed-window-closed first-ocean mouth catchment",
                "mouth_grid_zx": [cz, cx], "land_cells": int(cells.sum()),
                "land_boundary_cells": int(np.count_nonzero(cells & boundary.ravel())),
                "bounding_box_grid_zx_inclusive": [[int(zs.min()), int(xs.min())],
                                                   [int(zs.max()), int(xs.max())]],
                "area_km2": float(cells.sum() * .0009),
                "outlet_discharge_m3_per_s_at_1e-8_m_per_s_runoff": float(discharge[outlet]),
                "max_working_fill": {"grid_zx": [dz, dx],
                                     "raw_elevation_relative_sea_m": float(height[dz, dx]),
                                     "working_spill_level_relative_sea_m": float(routing.routing_height[dz, dx]),
                                     "fill_m": float(fill[dz, dx])},
                "deepest_fill_component": {
                    "filled_cells_4_connected": int(np.count_nonzero(component)),
                    "receiver_exit_from_grid_zx": [ez, ex],
                    "receiver_exit_to_grid_zx": [nz, nx],
                    "exit_from_raw_elevation_relative_sea_m": float(height[ez, ex]),
                    "exit_to_raw_elevation_relative_sea_m": float(height[nz, nx]) if next_cell >= 0 else None,
                    "exit_from_working_level_relative_sea_m": float(routing.routing_height[ez, ex]),
                    "note": "Receiver exit from the deepest filled 4-connected component; not a verified basin saddle or legal spill"},
                "working_fill_cells": candidate["working_fill_cells"],
                "working_fill_note": "Priority-flood level is a routing saddle proxy; lake balance, legal spill and physical filling are untested",
                "channel_budget_scenarios": budget_rows,
                "budget_note": "Fixed-route bed-only cuts with 0.01 m per edge; excludes banks, width, water stage, protection and route changes. No feasible total terrain-correction budget established.",
                "closure_note": "Observed catchment avoids this window's land boundary; not proven complete in a global or planned irregular domain."}
    (WINDOW / "candidate-planning.json").write_text(json.dumps(planning, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(WINDOW / "candidate-domain.npz",
                        land_catchment_mask=cells.reshape(height.shape),
                        first_ocean_mouth_grid_zx=np.array([cz, cx]),
                        routing_fill_m=fill,
                        receiver=routing.receiver)
    fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
    image = np.zeros(height.shape, dtype=np.uint8)
    image[ocean] = 1
    image[land] = 2
    image[cells.reshape(height.shape)] = 3
    ax.imshow(image, cmap=matplotlib.colors.ListedColormap(
        ["#72675c", "#358eb3", "#d9d4b4", "#4c8d48"]), interpolation="nearest")
    ax.plot(cx, cz, marker="o", color="red", markersize=5)
    ax.set(xlabel="Native grid x", ylabel="Native grid z",
           title="Observed closed lowland catchment (green), sea (blue)")
    fig.savefig(WINDOW / "candidate-domain.png", dpi=160)
    plt.close(fig)
    print("candidate", planning, flush=True)


if __name__ == "__main__":
    main()
