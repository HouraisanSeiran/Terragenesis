"""Independently reduce original-grid nodes, actual face flow and candidate sections."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def audit(prototype_path, expected_sha256):
    path = Path(prototype_path).resolve(strict=True)
    if path.stat().st_size > 1024 * 1024 or file_sha256(path) != expected_sha256:
        raise ValueError("geometry prototype external report pin/budget mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    topology, topology_metadata = read_record(report["inputs"]["hierarchy"])
    page, page_metadata = read_record(report["inputs"]["hour_page"])
    arrays, metadata = read_record(report["geometry"])
    if (metadata["hierarchy_identity"] != report["inputs"]["hierarchy"]["expected_identity"] or
            metadata["hour_page_identity"] != report["inputs"]["hour_page"]["expected_identity"] or
            metadata["forcing_identity"] != page_metadata["forcing_identity"] or
            metadata["start_s"] != page_metadata["start_s"] or metadata["end_s"] != page_metadata["end_s"]):
        raise ValueError("independent geometry source/time chain mismatch")
    for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        np.testing.assert_array_equal(page[name], topology[name])
    node_ids = np.flatnonzero(topology["valid_mask"].ravel())
    receiver = topology["receiver"][node_ids]
    np.testing.assert_array_equal(arrays["node_cell_ids"], node_ids)
    np.testing.assert_array_equal(arrays["node_receiver_cell_ids"], receiver)
    edges = np.column_stack((node_ids[receiver >= 0], receiver[receiver >= 0]))
    np.testing.assert_array_equal(arrays["edge_cell_ids"], edges)
    positions = np.searchsorted(node_ids, edges)
    origin = topology_metadata["origin_m_xz"]
    spacing = topology_metadata["spacing_m"]
    columns = topology["height_m"].shape[1]
    bed = topology["height_m"].ravel()[node_ids]
    np.testing.assert_array_equal(arrays["node_native_bed_m"], bed)
    np.testing.assert_array_equal(arrays["node_hour_end_water_depth_m"], page["depth_m"][-1, node_ids])
    np.testing.assert_array_equal(arrays["node_hour_end_surface_sample_m"], bed + page["depth_m"][-1, node_ids])
    np.testing.assert_array_equal(arrays["actual_face_cells"], topology["face_cells"])
    for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        np.testing.assert_array_equal(arrays["actual_" + name], page[name])
    flow = np.zeros(topology["height_m"].size)
    faces = topology["face_cells"]
    for source, target, volume in ((faces[:, 0], faces[:, 1], page["face_forward_m3"]),
                                  (faces[:, 1], faces[:, 0], page["face_reverse_m3"])):
        follows = topology["receiver"][source] == target
        np.add.at(flow, source[follows], volume[follows])
    np.testing.assert_array_equal(flow, page["routed_volume_m3"])
    q_mean = flow[node_ids] / 3600.
    np.testing.assert_array_equal(arrays["node_receiver_interval_mean_q_m3_s"], q_mean)
    recipe = metadata["recipe"]
    active = (q_mean > recipe["active_q_threshold_m3_s"]) & (receiver >= 0)
    ratio = q_mean / recipe["reference_q_m3_s"]
    own_width = np.where(active, np.clip(recipe["reference_width_m"] * ratio ** recipe["width_exponent"], recipe["minimum_width_m"], recipe["maximum_width_m"]), 0.)
    own_cut = np.where(active, np.clip(recipe["reference_depth_m"] * ratio ** recipe["depth_exponent"], recipe["minimum_depth_m"], recipe["maximum_depth_m"]), 0.)
    width, incision = own_width.copy(), own_cut.copy()
    for source in np.flatnonzero(active):
        target = int(np.searchsorted(node_ids, receiver[source]))
        width[target] = max(width[target], own_width[source])
        incision[target] = max(incision[target], own_cut[source])
    for name, values in (("node_width_m", width), ("node_candidate_incision_m", incision),
                         ("node_candidate_bed_m", bed - incision), ("node_geometry_active", width > 0),
                         ("node_receiver_geometry_active", active), ("edge_geometry_active", active[positions[:, 0]])):
        np.testing.assert_array_equal(arrays[name], values)
    world = np.column_stack((origin[0] + node_ids % columns * spacing, bed - incision,
                             origin[1] + node_ids // columns * spacing))
    np.testing.assert_array_equal(arrays["node_world_xyz_m"], world)
    np.testing.assert_array_equal(arrays["edge_centerline_xyz_m"], world[positions])
    boundary = np.isin(node_ids, topology["boundary_cells"])
    np.testing.assert_array_equal(arrays["node_engineering_boundary"], boundary)
    np.testing.assert_array_equal(arrays["node_internal_sink"], (receiver < 0) & ~boundary)
    sections = arrays["edge_sections_xyz_m"].reshape(len(edges), 2, 3, 3)
    np.testing.assert_array_equal(sections[:, :, 1], world[positions])
    direction = world[positions][:, 1, [0, 2]] - world[positions][:, 0, [0, 2]]
    normal = np.column_stack((-direction[:, 1], direction[:, 0])) / spacing
    for side, sign in ((0, -1), (2, 1)):
        expected_x = world[positions][:, :, 0] + sign * normal[:, None, 0] * width[positions] / 2.
        expected_z = world[positions][:, :, 2] + sign * normal[:, None, 1] * width[positions] / 2.
        np.testing.assert_array_equal(sections[:, :, side, 0], expected_x)
        np.testing.assert_array_equal(sections[:, :, side, 2], expected_z)
        np.testing.assert_array_equal(sections[:, :, side, 1], bed[positions])
    if any(metadata.get(name) is not False or report.get(name) is not False for name in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("independent geometry unsupported readiness")
    unchanged = [report["geometry"], *report["inputs"].values()]
    if file_sha256(path) != expected_sha256 or any(file_sha256(pin["path"]) != pin["expected_sha256"] for pin in unchanged):
        raise ValueError("geometry inputs changed during independent audit")
    junction_counts = np.bincount(edges[:, 1], minlength=topology["height_m"].size)
    return dict(schema="td-native-channel-independent-audit-v1", prototype_report_path=str(path), prototype_report_sha256=expected_sha256,
                geometry=report["geometry"], inputs=report["inputs"], nodes=int(len(node_ids)), edges=int(len(edges)),
                active_edges=int(active[positions[:, 0]].sum()), active_nodes=int((width > 0).sum()),
                shared_junction_nodes=int((junction_counts >= 2).sum()), internal_sinks=int(((receiver < 0) & ~boundary).sum()),
                native_geometry_and_states_checked=True, bidirectional_face_integrals_checked=True,
                no_invented_discharge_checked=True, candidate_recipe_and_shared_nodes_checked=True,
                solver_advanced=False, accepted=True, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                limitations="Single diagnostic hour; recipe sections and shared centerline nodes, no joined mesh, carved bed, continuous water or hydraulic convergence certification.",
                auditor_sha256=file_sha256(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prototype-report", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.prototype_report, args.expected_sha256)
    directory = ROOT / "verification/td-native-channel-geometry" / ("independent-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output = directory / "report.json"
    publish_bytes(output, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output), accepted=True)))
