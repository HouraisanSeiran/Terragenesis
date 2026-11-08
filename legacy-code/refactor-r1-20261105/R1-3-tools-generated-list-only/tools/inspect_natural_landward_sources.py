"""Read-only coordinate inventory for a possible larger landward natural domain."""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / ".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"
FILES = {
    "scene15": SCENE,
    "saved_centerline": ROOT / ".scratch/hydrological-planning-domain/saved-bed-mouth-20261016-01/centerline.npz",
    "feedback39": ROOT / "verification/fluvial-delta/adaptive-tree-16km-20261018-02/feedback_bundle.npz",
}


def run():
    with np.load(SCENE) as saved:
        meta = json.loads(str(saved["metadata_json"]))
        base = saved["base_bed_m"].copy()
    mouth = np.asarray(meta["mouth_xz_m"])
    direction = np.asarray(meta["river_direction_xz"])
    direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    report = {"mouth_xz_m": mouth.tolist(), "direction_xz": direction.tolist(), "files": {}}
    for role, path in FILES.items():
        record = {"path": str(path)}
        with np.load(path) as saved:
            record["fields"] = {name: list(saved[name].shape) for name in saved.files}
            for name in ("metadata_json",):
                if name in saved:
                    record[name] = json.loads(str(saved[name]))
            positions = [name for name in saved.files if name in ("node_xz_m", "incoming_path_xz_m", "designed_incoming_path_xz_m")]
            for name in positions:
                points = saved[name]
                along = (points - mouth) @ direction
                cross = (points - mouth) @ normal
                selected = (along >= -600.) & (along <= 50.)
                record[name + "_local_coordinates"] = {"along_range_m": [float(along.min()), float(along.max())],
                    "cross_range_m": [float(cross.min()), float(cross.max())],
                    "near_mouth_nodes": [{"index": int(index), "along_m": float(along[index]), "cross_m": float(cross[index]),
                        "world_xz_m": points[index].tolist()} for index in np.flatnonzero(selected)]}
                if role == "saved_centerline":
                    witnesses = []
                    for station in (-560., -360., -60., 0.):
                        index = int(np.argmin(abs(along - station)))
                        cells = (points[index] - np.asarray(meta["origin_xz_m"])) / float(meta["spacing_m"])
                        sampled = float(map_coordinates(base, [[cells[1]], [cells[0]]], order=1)[0])
                        witnesses.append({"along_m": float(along[index]), "saved_profile_bed_m": float(saved["bed_m"][index]),
                            "source_base_bed_m": sampled, "profile_minus_base_m": float(saved["bed_m"][index]) - sampled,
                            "piece_index": int(saved["piece_index"][index])})
                    record["connection_bed_witnesses"] = witnesses
                    piece_ids = sorted(set(int(v) for v in saved["piece_index"][selected]))
                    record["near_mouth_piece_archives"] = [piece for piece in record["metadata_json"]["pieces"] if piece["index"] in piece_ids]
                    for piece in record["near_mouth_piece_archives"]:
                        with np.load(piece["source_path"]) as mesh:
                            piece["fields"] = {name: list(mesh[name].shape) for name in mesh.files}
        report["files"][role] = record
    output = ROOT / "verification/fluvial-delta/natural-landward-source-inventory-20261019-01"
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    report = run()
    for role, record in report["files"].items():
        print(role, record["path"])
        print("fields", record["fields"])
        for name, value in record.items():
            if name.endswith("_local_coordinates"):
                print(name, value["along_range_m"], value["cross_range_m"], "near_mouth_node_count", len(value["near_mouth_nodes"]))
