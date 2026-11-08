"""Cold review data for bounded terrain changes, not invented river geometry."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import load_runoff_exchange
from terrain_pipeline.td_bounded_conditioning import validate_conditioning


def read_pin(directory, pin):
    path = (directory / pin["path"]).resolve(strict=True)
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("review artifact escapes the comparison directory")
    if file_sha256(path) != pin["sha256"]:
        raise ValueError("review input hash mismatch")
    return path


def terminal_catalog(hierarchy):
    arrays = hierarchy["arrays"]
    bed = arrays["height_m"]
    columns = bed.shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    owners = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    counts = np.bincount(owners[valid], minlength=len(arrays["node_parent"]))
    results = []
    for cell in np.flatnonzero(valid & (arrays["receiver"] < 0)):
        row, column = divmod(int(cell), columns)
        leaf = int(owners[cell])
        results.append({"cell_id": int(cell), "leaf_id": leaf,
            "xyz_m": [origin[0] + column * spacing, float(bed[row, column]), origin[1] + row * spacing],
            "area_m2": float(counts[leaf] * spacing**2),
            "kind": "engineering_boundary" if arrays["open_boundary_mask"].ravel()[cell] else "retained_internal_sink",
            "natural_outlet_verified": False})
    return results


def event_summary(directory, record, topology):
    results = []
    for case in record["cases"]:
        level = case["levels"][-1]
        pin = level["event"]
        event = load_runoff_exchange(read_pin(directory, pin), expected_sha256=pin["sha256"],
                                    expected_identity=pin["identity_sha256"], topology=topology)
        arrays = event["arrays"]
        forward, reverse = arrays["face_forward_m3"].sum(axis=0), arrays["face_reverse_m3"].sum(axis=0)
        faces = [{"face_id": face["face_id"], "cell_ids": face["cell_ids"], "leaf_ids": face["leaf_ids"],
                  "sill_m": face["sill_m"], "forward_m3": float(forward[position]),
                  "reverse_m3": float(reverse[position]), "net_m3": float(forward[position] - reverse[position])}
                 for position, face in enumerate(topology["faces"]) if forward[position] + reverse[position] > 1e-6]
        results.append({"name": case["name"], "event": pin, "active_physical_faces": faces,
            "outlets": [{**boundary, "outflow_m3": float(arrays["engineering_boundary_outflow_m3"][:, position].sum())}
                        for position, boundary in enumerate(topology["engineering_boundaries"])],
            "times_s": (np.arange(event["metadata"]["steps"] + 1) * event["metadata"]["timestep_s"]).tolist(),
            "total_surface_volume_m3": arrays["surface_volume_m3"].sum(axis=1).tolist(),
            "engineering_outflow_per_interval_m3": arrays["engineering_boundary_outflow_m3"].sum(axis=1).tolist(),
            "semantics": "saved basin exchanges, not river centerlines or fine-channel velocities"})
    return results


def render(path, original, candidates, spacing):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, TwoSlopeNorm

    terrain = LightSource(azdeg=315, altdeg=45).hillshade(original, dx=spacing, dy=spacing)
    figure, axes = plt.subplots(2, 2, figsize=(14, 11), constrained_layout=True)
    extent = [0., original.shape[1] * spacing / 1000., original.shape[0] * spacing / 1000., 0.]
    axes.flat[0].imshow(terrain, cmap="gray", extent=extent)
    axes.flat[0].set_title("Original TD: unchanged storage/spill baseline")
    artist = None
    for axis, (name, bed, summary) in zip(list(axes.flat)[1:], candidates):
        axis.imshow(terrain, cmap="gray", extent=extent)
        delta = np.ma.masked_where(bed == original, bed - original)
        artist = axis.imshow(delta, cmap="RdBu", norm=TwoSlopeNorm(vmin=-4., vcenter=0., vmax=1.),
                             interpolation="nearest", extent=extent)
        axis.set_title(f"{name}: {np.count_nonzero(bed != original)} changed cells\n"
                       f"{summary['basin_count']} basins; max catchment {summary['largest_static_catchment_area_m2']/1e6:.3f} km2")
    for axis in axes.flat:
        axis.set_xlabel("Local east (km)")
        axis.set_ylabel("Local south (km)")
    if artist is not None:
        figure.colorbar(artist, ax=list(axes.flat), label="Initial bed change (m): red=cut, blue=fill", shrink=.75)
    figure.suptitle("Bounded initial terrain conditioning, not event erosion or a certified river network")
    figure.savefig(path, dpi=120)
    plt.close(figure)


def export(directory, expected_sha256, expected_audit_sha256, *, audit_name="independent-audit.json"):
    directory = Path(directory).resolve(strict=True)
    index_path = directory / "index.json"
    if file_sha256(index_path) != expected_sha256:
        raise ValueError("comparison index pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if Path(audit_name).name != audit_name or not audit_name.endswith(".json"):
        raise ValueError("audit must be a local JSON filename")
    audit_path = directory / audit_name
    if file_sha256(audit_path) != expected_audit_sha256:
        raise ValueError("independent audit pin mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["index_sha256"] != expected_sha256 or audit["status"] != "passed":
        raise ValueError("review requires the matching independent audit")
    output = directory / "review"
    if output.exists():
        raise FileExistsError(output)
    pin = index["configuration"]["hierarchy"]
    baseline = load_basin_hierarchy(pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    original = baseline["arrays"]["height_m"]
    cases = [{"candidate_id": "baseline", "terminals": terminal_catalog(baseline),
              "drainage": index["candidates"][0]["drainage"], "events_reused": True,
              "baseline_evidence": index["configuration"]["baseline_index"]}]
    plots = []
    with patch("terrain_pipeline.td_bounded_conditioning.build_conditioning_candidates", side_effect=AssertionError("cold export")), \
            patch("terrain_pipeline.td_basin_runoff_exchange.simulate_runoff_exchange", side_effect=AssertionError("cold export")):
        for record in index["candidates"][1:]:
            pin = record["conditioning"]
            bundle = load_bundle(read_pin(directory, pin), expected_sha256=pin["sha256"], validator=validate_conditioning)
            if bundle["identity_sha256"] != pin["identity_sha256"]:
                raise ValueError("conditioning identity mismatch")
            changed = np.flatnonzero(bundle["arrays"]["height_m"].ravel() != original.ravel())
            item = {"candidate_id": record["candidate_id"], "conditioning": pin, "changed_cell_ids": changed.tolist(),
                    "changed_height_m": bundle["arrays"]["height_m"].ravel()[changed].tolist(),
                    "delta_m": (bundle["arrays"]["height_m"].ravel()[changed] - original.ravel()[changed]).tolist(),
                    "drainage": record["drainage"], "geometry_metadata": bundle["metadata"]}
            if record["changed_cells"]:
                pin = record["hierarchy"]
                hierarchy = load_basin_hierarchy(read_pin(directory, pin), expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
                pin = record["topology"]
                topology = load_overflow_topology(read_pin(directory, pin), expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
                item["terminals"] = terminal_catalog(hierarchy)
                item["events"] = event_summary(directory, record, topology)
            else:
                item.update(terminals=cases[0]["terminals"], events_reused=True)
            cases.append(item)
            plots.append((record["candidate_id"], bundle["arrays"]["height_m"], record["drainage"]))
    review = {"schema": "td-conditioning-cold-review-v1", "index_sha256": expected_sha256,
              "audit_sha256": file_sha256(audit_path), "recommended_diagnostic_candidate": audit["recommended_diagnostic_candidate"],
              "shape": list(original.shape), "spacing_m": baseline["metadata"]["spacing_m"],
              "origin_m_xz": baseline["metadata"]["origin_m_xz"], "original_height_m": original.tolist(),
              "candidates": cases, "solver_advanced": False, "hydraulic_ready": False,
              "natural_outlet_verified": False, "publishable": False, "permanent_trunk_ready": False}
    payload = json.dumps(review, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 64 * 1024**2:
        raise MemoryError("review exceeds 64MiB")
    output.mkdir()
    publish_bytes(output / "review.json", payload)
    render(output / "bed-comparison.png", original, plots, baseline["metadata"]["spacing_m"])
    manifest = {"review": {"path": "review.json", "sha256": file_sha256(output / "review.json"), "bytes": len(payload)},
                "image": {"path": "bed-comparison.png", "sha256": file_sha256(output / "bed-comparison.png")},
                "export_code_sha256": file_sha256(Path(__file__)), "cold_read": True, "solver_advanced": False}
    publish_bytes(output / "index.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return {"directory": str(output), **manifest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--audit-name", default="independent-audit.json")
    arguments = parser.parse_args()
    print(json.dumps(export(arguments.directory, arguments.index_sha256, arguments.audit_sha256,
                            audit_name=arguments.audit_name)))
