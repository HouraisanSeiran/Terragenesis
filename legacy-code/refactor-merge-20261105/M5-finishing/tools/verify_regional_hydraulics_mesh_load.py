"""Cold saved physical columns/display correspondence; no geometry preparation or solver."""

import json
from pathlib import Path
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.regional_hydraulics_archive import read_arrays, strict_json
from terrain_pipeline.regional_hydraulics_mesh import validate_water_columns
from terrain_pipeline.regional_surface_source import load_source


def check(directory, *, expected_manifest_sha256):
    directory = Path(directory)
    if file_sha256(directory / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external trusted mesh manifest")
    manifest = strict_json(directory / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        if Path(name).name != name or file_sha256(directory / name) != digest:
            raise ValueError("mesh authenticated artifact")
    source = load_source(ROOT / "verification/regional-source/run-20261001T095258008789Z/source.npz", expected_sha256="ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da")
    if "saved-mesh-index.json" not in manifest["artifacts"] or not (directory / "saved-mesh-index.json").is_file():
        raise ValueError("saved mesh index is required")
    index = strict_json(directory / "saved-mesh-index.json")
    if index["source_identity"] != source["identity_sha256"] or not isinstance(index["snapshots"], list) or not index["snapshots"]:
        raise ValueError("nonempty authenticated mesh keyframe declaration required")
    declared_times = {float(item["time_s"]): item for item in index["snapshots"]}
    if len(declared_times) != len(index["snapshots"]):
        raise ValueError("duplicate declared mesh keyframe")
    for item in index["snapshots"]:
        if set(item) != {"time_s", "path", "sha256", "omitted_volume_m3", "solver_volume_m3"}:
            raise ValueError("exact declared mesh keyframe schema")
        path = item["path"]
        if Path(path).name != path or path not in manifest["artifacts"] or file_sha256(directory / path) != item["sha256"]:
            raise ValueError("declared mesh keyframe artifact binding")
    case = ROOT / index["source_case_directory"]
    if file_sha256(case / "manifest.json") != index["source_case_manifest_sha256"] or index["source_case_manifest_sha256"] != manifest["case_manifest_sha256"]:
        raise ValueError("mesh source case binding")
    case_manifest = strict_json(case / "manifest.json")
    with zipfile.ZipFile(case / "states.npz") as archive:
        with archive.open("time_s.npy") as stream:
            version = np.lib.format.read_magic(stream)
            header = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or dtype != np.float64:
                raise ValueError("mesh source bounded saved state header")
            count = shape[0]
    states = read_arrays(case / "states.npz", {"time_s": ((count,), "float64"),
        "depth_m": ((count, 256, 256), "float64"), "initial_depth_m": ((256, 256), "float64"),
        "ledger": ((count, 5), "float64"), "final_internal_q_m3_s": ((130560,), "float64"),
        "final_boundary_q_m3_s": ((1024,), "float64")}, expected_sha256=case_manifest["artifacts"]["states.npz"])
    times, depths = states["time_s"], states["depth_m"]
    proofs = []
    for name, digest in manifest["artifacts"].items():
        if not name.startswith("physical-water-") or not name.endswith(".npz"):
            continue
        state_index = int(name.removeprefix("physical-water-").removesuffix(".npz"))
        depth = depths[state_index]
        wet = int((depth > 0).sum())
        packet = {"arrays": read_arrays(directory / name, {"vertices_xyz_m": ((wet * 8, 3), "float64"),
            "triangles": ((wet * 12, 3), "int64"), "cell_id": ((wet,), "int64"), "cell_volume_m3": ((wet,), "float64")},
            expected_sha256=digest), "metadata": strict_json(directory / name.replace(".npz", ".json"))}
        if packet["metadata"]["time_s"] != times[state_index]:
            raise ValueError("mesh saved physical time")
        proof = validate_water_columns(packet, trusted_height=source["arrays"]["height_m"], saved_depth=depth,
            source_identity=source["identity_sha256"], trusted_spacing_m=30., trusted_origin_m_xz=source["metadata"]["origin_m_xz"])
        proofs.append({"state_index": state_index, "time_s": float(times[state_index]), **proof})
    if not proofs:
        raise ValueError("mesh index must contain at least one authenticated physical water archive")
    if not proofs:
        raise ValueError("physical water proof set cannot be empty")
    proof_times = {item["time_s"] for item in proofs}
    if proof_times != set(declared_times):
        raise ValueError("declared keyframes must all have physical-column proof")
    display_names = []
    for name in manifest["artifacts"]:
        if not (name.startswith("saved-water-") or name.startswith("consumer-full-water-")) or not name.endswith(".json"):
            continue
        if (directory / name).stat().st_size > 16 * 1024**2:
            raise ValueError("mesh display bounded JSON")
        display = json.loads((directory / name).read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite display")))
        display_names.append(name)
        physical_name = display["physical_archive"]
        state_index = int(physical_name.removeprefix("physical-water-").removesuffix(".npz"))
        depth = depths[state_index]
        threshold = display["display_threshold_m"]
        if threshold not in (0., .001) or display["source_identity"] != source["identity_sha256"] or display["time_s"] != times[state_index]:
            raise ValueError("mesh display identity/threshold/time")
        ids = np.flatnonzero((depth.ravel() > 0) & (depth.ravel() >= threshold))
        vertices = np.asarray(display["vertices_xyz_m"], np.float64).reshape(-1, 4, 3)
        triangles = np.asarray(display["triangles"], np.int64).reshape(-1, 3)
        if not np.array_equal(ids, display["display_cell_ids"]) or vertices.shape != (len(ids), 4, 3) or not np.array_equal(triangles, (np.array([[0, 2, 1], [0, 3, 2]])[None] + np.arange(len(ids))[:, None, None] * 4).reshape(-1, 3)):
            raise ValueError("mesh display support/topology")
        rows, columns = np.divmod(ids, 256)
        origin = source["metadata"]["origin_m_xz"]
        expected_x = origin[0] + columns[:, None] * 30 + np.array([-15., 15., 15., -15.])
        expected_z = origin[1] + rows[:, None] * 30 + np.array([-15., -15., 15., 15.])
        stage = (source["arrays"]["height_m"] + depth).ravel()[ids]
        if not np.array_equal(vertices[:, :, 0], expected_x) or not np.array_equal(vertices[:, :, 2], expected_z) or not np.array_equal(vertices[:, :, 1], np.repeat(stage[:, None], 4, axis=1)):
            raise ValueError("mesh display source coordinates/stage")
        shown = float(depth.ravel()[ids].sum() * 900.)
        total = float(depth.sum() * 900.)
        if not np.isclose(display["display_volume_m3"], shown, atol=1e-8, rtol=1e-12) or not np.isclose(display["solver_volume_m3"], total, atol=1e-8, rtol=1e-12) or not np.isclose(display["omitted_volume_m3"], total - shown, atol=1e-8, rtol=1e-12) or display["omitted_wet_cells"] != int((depth > 0).sum()) - len(ids):
            raise ValueError("mesh display filtering ledger")
    if set(display_names) != {item["path"] for item in index["snapshots"]}:
        raise ValueError("declared display keyframes must be exactly covered")
    return {"manifest_sha256": expected_manifest_sha256, "physical_states": proofs,
        "scope": "all_saved_column_source_geometry_volume_and_display_filter_correspondence"}


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    result = check(directory, expected_manifest_sha256=sys.argv[2])
    publish_bytes(directory.parent / (directory.name + "-cold.json"), json.dumps(result, indent=2).encode("ascii"))
    print(json.dumps(result), flush=True)
