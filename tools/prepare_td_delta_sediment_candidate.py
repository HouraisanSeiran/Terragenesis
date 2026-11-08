"""Bind a fixed TD reach's saved solid export to an imposed local delta candidate."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import load_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_product import load_channel_product
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta_sediment_product import (
    build_delta_sediment_candidate, load_delta_sediment_candidate, save_delta_sediment_candidate,
)
from terrain_pipeline.surface_rivers.metric_sediment import load_sediment
from terrain_pipeline.channel_geometry import receiver_distances

ROOT = Path(__file__).resolve().parents[1]


def _terminal_inlet(geometry, terrain, terminal):
    arrays = geometry["arrays"]
    donors = np.flatnonzero(arrays["receiver"] == terminal)
    if not len(donors):
        raise ValueError("export terminal requires a real upstream receiver edge")
    donor = min(map(int, donors), key=lambda node: (int(arrays["source_node_cell_ids"][node]), node))
    columns = terrain.elevation_m.shape[1]
    path = tuple(divmod(int(arrays["source_node_cell_ids"][node]), columns) for node in (donor, terminal))
    direction = arrays["node_xz_m"][terminal] - arrays["node_xz_m"][donor]
    length = float(np.linalg.norm(direction))
    if not np.isfinite(length) or length <= 0.:
        raise ValueError("export terminal requires a positive-length source edge")
    direction = direction / length
    controls = np.asarray([[terrain.x0_m + column * terrain.dx_m,
                            terrain.z0_m + row * terrain.dz_m] for row, column in path])
    if float((controls[1] - controls[0]) @ direction) <= 0.:
        raise ValueError("source edge direction cannot separate upstream and terminal control cells")
    origin = controls.mean(axis=0)
    rows, cols = np.ogrid[:terrain.elevation_m.shape[0], :columns]
    projection = ((terrain.x0_m + cols * terrain.dx_m - origin[0]) * direction[0]
                  + (terrain.z0_m + rows * terrain.dz_m - origin[1]) * direction[1])
    wet = terrain.valid_mask & (projection >= 0.)
    land = terrain.valid_mask & ~wet
    evidence = {"upstream_node": donor, "main_path_cells": [list(cell) for cell in path],
                "donor_selection": "minimum_source_cell_id_then_node_id_among_terminal_receivers",
                "imposed_shoreline_origin_xz_m": origin.tolist(),
                "imposed_downstream_unit_direction_xz": direction.tolist(),
                "imposed_water_half_plane": "nonnegative_projection_along_actual_terminal_edge",
                "shoreline_origin_semantics": "midpoint_of_source_control_cells"}
    return land, wet, path, evidence


def prepare(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    gd = ROOT / "verification/td-river-geometry/m5-20261008-06"
    sd = ROOT / "verification/td-river-sediment/m6-20261008-03"
    gm = json.loads((gd / "acceptance.json").read_text(encoding="utf-8"))
    sm = json.loads((sd / "acceptance.json").read_text(encoding="utf-8"))
    gp, sp = gm["artifacts"]["td_fine"], sm["artifacts"]["td_fine"]
    geometry = load_channel_geometry(gd / gp["path"], expected_sha256=gp["sha256"], expected_identity=gp["identity_sha256"])
    sediment = load_sediment(sd / sp["path"], expected_sha256=sp["sha256"])
    if sediment["identity_sha256"] != sp["identity_sha256"]:
        raise ValueError("fixed sediment identity mismatch")
    wp = sd / "td-new-geometry-water.npz"
    water = load_channel_product(wp, expected_sha256=file_sha256(wp),
                                 expected_identity=sediment["metadata"]["hydraulic_identity_sha256"],
                                 legacy_receiver_distance_m=receiver_distances(
                                     geometry["arrays"]["node_xz_m"], geometry["arrays"]["receiver"]))
    a = geometry["arrays"]
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **geometry["metadata"]["terrain_metadata"])
    terminals = np.flatnonzero(sediment["arrays"]["domain_open_boundary"])
    if len(terminals) != 1:
        raise ValueError("fixed single-export TD reach required")
    terminal = int(terminals[0])
    land, wet, main_path, inlet_evidence = _terminal_inlet(geometry, terrain, terminal)
    candidate = build_delta_sediment_candidate(
        terrain, land, wet, main_path, geometry, water, sediment,
        terminal)
    path = output / "candidate.npz"
    save_delta_sediment_candidate(path, candidate)
    cold = load_delta_sediment_candidate(path, expected_sha256=file_sha256(path))
    report = {"status": "candidate", "cold_read_passed": cold["identity_sha256"] == candidate["identity_sha256"],
              "artifact_sha256": file_sha256(path), "identity_sha256": candidate["identity_sha256"],
              "terrain_identity_sha256": terrain.identity_sha256,
              "water_identity_sha256": water["identity_sha256"], "sediment_identity_sha256": sediment["identity_sha256"],
              "terminal_node": terminal, "solid_supply_m3": candidate["metadata"]["sediment_supply_solid_m3"],
              "inlet_evidence": inlet_evidence,
              "interpretation": "real TD elevation and witnessed single-terminal water/sediment export; caller imposed land/water at terminal; no certified natural mouth",
              "topology_mutation": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output / "report.json", json.dumps(report, indent=2, allow_nan=False).encode())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))
