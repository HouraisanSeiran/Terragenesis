"""Independently check frozen TD candidate reaches and draw a scientific review figure."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def read_json(path, digest):
    if file_sha256(path) != digest:
        raise ValueError("external JSON SHA mismatch")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def identity(record):
    values = {key: value for key, value in record.items() if key != "identity_sha256"}
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def subtree_areas(arrays, spacing):
    usable = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    receiver = arrays["receiver"].copy()
    receiver[~usable] = -1
    donors = [[] for cell in range(len(receiver))]
    for cell in np.flatnonzero(usable):
        target = receiver[cell]
        if target >= 0 and not usable[target]:
            receiver[cell] = -1
        elif target >= 0:
            donors[target].append(int(cell))
    areas = np.zeros(len(receiver))
    visited = np.zeros(len(receiver), bool)
    roots = np.flatnonzero(usable & (receiver < 0))
    for root in roots:
        stack = [(int(root), False)]
        while stack:
            cell, returning = stack.pop()
            if returning:
                areas[cell] = spacing ** 2 + sum(areas[donor] for donor in donors[cell])
            else:
                if visited[cell]:
                    raise ValueError("duplicate forest traversal")
                visited[cell] = True
                stack.append((cell, True))
                stack.extend((donor, False) for donor in donors[cell])
    if not np.array_equal(visited, usable):
        raise ValueError("receiver forest has cyclic or unreachable cells")
    np.testing.assert_allclose(areas[roots].sum(), usable.sum() * spacing ** 2, rtol=1e-13)
    return usable, receiver, areas


def audit(scan_path, scan_sha256, destination):
    scan = read_json(scan_path, scan_sha256)
    topology, metadata = read_record(scan["inputs"]["hierarchy"])
    water, water_metadata = read_record(scan["inputs"]["storage"])
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    bed = topology["height_m"].ravel()
    rows, columns = topology["height_m"].shape
    usable, receiver, areas = subtree_areas(topology, spacing)
    reports = []
    networks = []
    shared_ids = {}
    for case in scan["cases"]:
        network = read_json(case["path"], case["expected_sha256"])
        if identity(network) != case["expected_identity"] or network["identity_sha256"] != case["expected_identity"]:
            raise ValueError("reach identity mismatch")
        threshold = case["threshold_area_m2"]
        if network["threshold_area_m2"] != threshold:
            raise ValueError("threshold mismatch")
        expected_edges = set(map(int, np.flatnonzero(usable & (areas >= threshold) & (receiver >= 0))))
        selected_donors = np.zeros(len(receiver), int)
        np.add.at(selected_donors, receiver[list(expected_edges)], 1)
        observed_edges = []
        reach_lengths = []
        max_slope = 0.0
        for reach in network["reaches"]:
            cells = reach["cell_ids"]
            if len(cells) < 2 or len(reach["edges"]) != len(cells) - 1:
                raise ValueError("invalid reach lengths")
            if len(cells) > 2 and np.any(selected_donors[cells[1:-1]] != 1):
                raise ValueError("compressed chain contains a junction")
            np.testing.assert_allclose(reach["contributing_area_m2"], areas[cells], rtol=0, atol=1e-8)
            expected_xyz = [[origin[0] + cell % columns * spacing, bed[cell], origin[1] + cell // columns * spacing] for cell in cells]
            np.testing.assert_array_equal(reach["xyz_m"], expected_xyz)
            for donor, target, edge in zip(cells, cells[1:], reach["edges"]):
                if receiver[donor] != target or edge["donor_cell_id"] != donor or edge["target_cell_id"] != target:
                    raise ValueError("receiver edge mismatch")
                if abs(donor // columns - target // columns) + abs(donor % columns - target % columns) != 1:
                    raise ValueError("non-D4 edge")
                if bed[target] > bed[donor]:
                    raise ValueError("uphill candidate")
                max_slope = max(max_slope, (bed[donor] - bed[target]) / spacing)
                observed_edges.append(donor)
                if donor in shared_ids and shared_ids[donor] != edge["edge_id"]:
                    raise ValueError("edge identity changed with threshold")
                shared_ids[donor] = edge["edge_id"]
                face = edge["face_index"]
                pair = topology["face_cells"][face]
                if set(map(int, pair)) != {donor, target}:
                    raise ValueError("face provenance mismatch")
                flux = edge["stored_flux"]
                forward, reverse = float(water["face_forward_m3"][face]), float(water["face_reverse_m3"][face])
                along, against = (forward, reverse) if pair[0] == donor else (reverse, forward)
                for field, expected in (("forward_m3", forward), ("reverse_m3", reverse), ("net_face_m3", forward - reverse),
                                        ("gross_m3", forward + reverse), ("along_receiver_m3", along), ("against_receiver_m3", against),
                                        ("net_receiver_m3", along - against), ("forward_active_s", water["active_forward_s"][face]),
                                        ("reverse_active_s", water["active_reverse_s"][face])):
                    if flux[field] != expected:
                        raise ValueError("saved directional flux mismatch")
            reach_lengths.append((len(cells) - 1) * spacing)
        if len(set(observed_edges)) != len(observed_edges) or set(observed_edges) != expected_edges:
            raise ValueError("missing or repeated selected edge")
        expected_anchors = set(map(int, np.flatnonzero(usable & (areas >= threshold) & ((selected_donors != 1) | (receiver < 0)))))
        if {node["cell_id"] for node in network["nodes"]} != expected_anchors:
            raise ValueError("anchor coverage mismatch")
        terminals = Counter(node["terminal_kind"] for node in network["nodes"] if node["kind"] == "terminal")
        reports.append({"threshold_area_m2": threshold, "selected_edges": len(observed_edges), "reach_count": len(reach_lengths),
                        "node_count": len(network["nodes"]), "terminal_counts": dict(terminals),
                        "total_reach_length_m": sum(reach_lengths), "maximum_reach_length_m": max(reach_lengths, default=0),
                        "max_d4_bed_slope": max_slope, "checks_passed": True, "pin": case})
        networks.append(network)
    destination = Path(destination)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    figure, axes = plt.subplots(1, len(networks), figsize=(16, 5), constrained_layout=True)
    extent = [(origin[0] - spacing / 2) / 1000, (origin[0] + (columns - .5) * spacing) / 1000,
              (origin[1] + (rows - .5) * spacing) / 1000, (origin[1] - spacing / 2) / 1000]
    for axis, network, report in zip(axes, networks, reports):
        raster = axis.imshow(topology["height_m"], extent=extent, cmap="terrain")
        lines = [np.array(reach["xyz_m"])[:, [0, 2]] / 1000 for reach in network["reaches"]]
        axis.add_collection(LineCollection(lines, colors="#005eff", linewidths=1.1))
        terminals = [node for node in network["nodes"] if node["terminal_kind"] == "internal_basin"]
        axis.scatter([node["xyz_m"][0] / 1000 for node in terminals], [node["xyz_m"][2] / 1000 for node in terminals],
                     s=12, c="#dc2929", marker="o")
        axis.set_title(f"{report['threshold_area_m2'] / 1e6:g} km²: {report['reach_count']} reaches")
        axis.set_xlabel("X (km)")
        axis.set_ylabel("Z south (km)")
    figure.colorbar(raster, ax=list(axes), label="Bed elevation (m)", shrink=.8)
    figure.suptitle("Frozen Terrain Diffusion: static area candidates / red = internal basin terminals\n30 m D4 grid; no inferred channel widths or water surfaces")
    import io
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=160)
    plt.close(figure)
    publish_bytes(destination / "candidate-reaches.png", buffer.getvalue())
    result = {"schema": "td-independent-reach-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "scan": {"path": str(scan_path), "expected_sha256": scan_sha256}, "cases": reports,
              "valid_area_m2": float(usable.sum() * spacing ** 2), "solver_advanced": False,
              "contribution_algorithm": "independent terminal-rooted donor-tree postorder traversal",
              "hydraulic_ready": False, "natural_outlet_verified": False,
              "figure_sha256": file_sha256(destination / "candidate-reaches.png"), "auditor_sha256": file_sha256(__file__),
              "limitations": "Independent static area/chain/bed/face-flux checks. Retained internal basin breaks prevent a single outlet network. Native grid lines are review geometry, not resolved channels."}
    publish_bytes(destination / "report.json", json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode())
    print(json.dumps({"output": str(destination), "cases": [{key: case[key] for key in ("threshold_area_m2", "reach_count", "terminal_counts", "checks_passed")} for case in reports]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--scan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    audit(arguments.scan, arguments.scan_sha256, arguments.output)
