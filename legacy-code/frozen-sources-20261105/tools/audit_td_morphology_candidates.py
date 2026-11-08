import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta_product import load_delta_candidate_product
from terrain_pipeline.surface_rivers.metric_morphology_events import event_from_record
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, load_td_source


SCHEMA = "td-real-morphology-candidate-set-v1"
ARTIFACTS = {
    "cutoff": ("cutoff.npz", "td-cutoff-candidate-artifact-v1", {"shortcut_xz_m", "loop_xz_m"}),
    "bank_pointbar": ("bank-pointbar.npz", "td-bank-pointbar-candidate-artifact-v1", {"height_delta_m", "erosion_mask", "deposit_mask"}),
    "braided": ("braided.npz", "td-braided-candidate-artifact-v1", {"bar_mask", "height_delta_m", "flow_split"}),
    "alluvial_fan": ("alluvial-fan.npz", "td-alluvial-fan-candidate-artifact-v1", {"height_delta_m", "deposit_mask", "footprint"}),
    "floodplain": ("floodplain.npz", "td-floodplain-candidate-artifact-v1", {"inundation_mask", "height_delta_m"}),
}
EVENT_TYPES = {
    "cutoff": "cutoff",
    "bank_pointbar": "bank_migration",
    "braided": "bifurcation",
    "alluvial_fan": "alluvial_fan",
    "floodplain": "floodplain_inundation",
}
FALSE_CAPABILITIES = {
    "hydraulic": False,
    "hydrodynamics": False,
    "natural_outlet": False,
    "publishable": False,
    "routing_graph_written": False,
    "topology_mutation": False,
    "sediment_recompute": False,
}
LEDGER_KEYS = {"deposited_solid_m3", "exported_solid_m3", "unresolved_solid_m3", "cut_rock_m3", "fill_m3", "porous_deposit_m3"}
REFERENCE_REPORT = Path(__file__).resolve().parents[1] / "verification/reference-routing/td256-20261009-01/report.json"
PARENT_GEOMETRY_IDENTITY = hashlib.sha256(b"td256-local-morphology-candidate-v1").hexdigest()


def _sha(path):
    return file_sha256(path)


def _canonical_summary(summary):
    body = dict(summary)
    body.pop("summary_body_sha256", None)
    return json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def _require_sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _all_false(value, name):
    if not isinstance(value, dict):
        raise ValueError(name + " must be an object")
    if any(not isinstance(item, bool) or item for item in value.values()):
        raise ValueError(name + " contains an enabled capability")


def _ledger(value, name):
    if not isinstance(value, dict) or set(value) != LEDGER_KEYS:
        raise ValueError(name + " has an invalid material ledger")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not np.isfinite(item) or item < 0. for item in value.values()):
        raise ValueError(name + " has a non-finite material ledger")


def _event(metadata, kind, graph, geometry):
    event = event_from_record(metadata["event_record"])
    if event.event_type != EVENT_TYPES[kind] or event.status != "candidate":
        raise ValueError(kind + " event identity/type mismatch")
    if event.parent_graph_identity_sha256 != graph or event.parent_geometry_identity_sha256 != geometry:
        raise ValueError(kind + " event parent identity mismatch")
    if event.identity_sha256 != metadata["event_record"]["identity_sha256"]:
        raise ValueError(kind + " event identity mismatch")
    if event.material_ledger:
        _ledger(dict(event.material_ledger), kind + " event")
    return event


def _validate_inputs(record):
    arrays, metadata = record["arrays"], record["metadata"]
    expected = {"terrain_elevation_m", "terrain_valid_mask", "land_mask", "water_mask", "delta_path_cells", "centerline_xz_m"}
    if set(arrays) != expected or metadata.get("schema") != "td-real-morphology-input-v1":
        raise ValueError("inputs schema or arrays mismatch")
    shape = arrays["terrain_elevation_m"].shape
    if arrays["terrain_elevation_m"].dtype != np.float64 or arrays["terrain_elevation_m"].ndim != 2 or not np.isfinite(arrays["terrain_elevation_m"]).all():
        raise ValueError("inputs terrain is invalid")
    for name in ("terrain_valid_mask", "land_mask", "water_mask"):
        if arrays[name].dtype != bool or arrays[name].shape != shape:
            raise ValueError("inputs mask is invalid: " + name)
    if np.any((arrays["land_mask"] | arrays["water_mask"]) & ~arrays["terrain_valid_mask"]):
        raise ValueError("inputs classify unknown terrain")
    if np.any(arrays["land_mask"] & arrays["water_mask"]):
        raise ValueError("inputs land and water overlap")
    if arrays["delta_path_cells"].dtype != np.int64 or arrays["delta_path_cells"].ndim != 2 or arrays["delta_path_cells"].shape[1] != 2:
        raise ValueError("inputs delta path is invalid")
    if arrays["centerline_xz_m"].dtype != np.float64 or arrays["centerline_xz_m"].ndim != 2 or arrays["centerline_xz_m"].shape[1] != 2 or not np.isfinite(arrays["centerline_xz_m"]).all():
        raise ValueError("inputs centerline is invalid")
    for name in ("source_identity_sha256", "source_file_sha256", "terrain_identity_sha256",
                 "parent_graph_identity_sha256", "parent_geometry_identity_sha256"):
        _require_sha(metadata.get(name), "inputs " + name)
    if (not isinstance(metadata.get("origin_x_m"), (int, float)) or
            not isinstance(metadata.get("origin_z_m"), (int, float)) or
            not isinstance(metadata.get("spacing_m"), (int, float)) or metadata["spacing_m"] <= 0.):
        raise ValueError("inputs metric coordinates are invalid")
    if tuple(metadata.get("window_shape_zx", ())) != shape:
        raise ValueError("inputs window shape mismatch")
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("inputs identity mismatch")


def _validate_generic(record, kind, shape, graph, geometry, terrain_identity, valid_mask=None):
    arrays, metadata = record["arrays"], record["metadata"]
    _, schema, expected_arrays = ARTIFACTS[kind]
    if set(arrays) != expected_arrays or metadata.get("schema") != schema or metadata.get("status") != "candidate":
        raise ValueError(kind + " schema or arrays mismatch")
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError(kind + " identity mismatch")
    if metadata.get("source_identity_sha256") is None or metadata.get("parent_graph_identity_sha256") != graph or metadata.get("parent_geometry_identity_sha256") != geometry:
        raise ValueError(kind + " parent identity mismatch")
    _require_sha(metadata["source_identity_sha256"], kind + " source identity")
    event = _event(metadata, kind, graph, geometry)
    _all_false(metadata.get("capabilities"), kind + " capabilities")
    for name, value in arrays.items():
        if value.shape != shape:
            if kind == "cutoff" and value.ndim == 2 and value.shape[1] == 2:
                continue
            if kind == "braided" and name == "flow_split" and value.ndim == 1:
                continue
            raise ValueError(kind + " array shape mismatch: " + name)
    for name in ("height_delta_m",):
        if name not in arrays:
            continue
        value = arrays[name]
        if (value.dtype != np.float64 or not np.isfinite(value).all()
                or kind != "bank_pointbar" and np.any(value < 0.)):
            raise ValueError(kind + " height delta is invalid")
        if valid_mask is not None and np.any((value != 0.) & ~valid_mask):
            raise ValueError(kind + " modifies unknown terrain")
    for name in ("erosion_mask", "deposit_mask", "bar_mask", "footprint", "inundation_mask"):
        if name in arrays and (arrays[name].dtype != bool or arrays[name].shape != shape):
            raise ValueError(kind + " mask is invalid: " + name)
    if "height_delta_m" in arrays:
        delta = arrays["height_delta_m"]
        if kind == "bank_pointbar":
            if np.any(arrays["erosion_mask"] & arrays["deposit_mask"]):
                raise ValueError(kind + " erosion/deposit masks overlap")
            if np.any((delta < 0.) & ~arrays["erosion_mask"]) or np.any((delta > 0.) & ~arrays["deposit_mask"]):
                raise ValueError(kind + " height delta is outside its masks")
        elif kind in ("braided", "alluvial_fan"):
            mask = arrays["bar_mask"] if kind == "braided" else arrays["deposit_mask"]
            if np.any((delta > 0.) != mask):
                raise ValueError(kind + " deposit mask does not match height delta")
    if "material_ledger" in metadata:
        _ledger(metadata["material_ledger"], kind + " metadata")
        if dict(event.material_ledger) != metadata["material_ledger"]:
            raise ValueError(kind + " event/material ledger mismatch")
    if "solid_ledger" in metadata:
        ledger = metadata["solid_ledger"]
        if not isinstance(ledger, dict) or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0. for value in ledger.values()):
            raise ValueError(kind + " solid ledger is invalid")
    if kind == "cutoff" and (arrays["shortcut_xz_m"].dtype != np.float64 or arrays["loop_xz_m"].dtype != np.float64 or not np.isfinite(arrays["shortcut_xz_m"]).all() or not np.isfinite(arrays["loop_xz_m"]).all()):
        raise ValueError("cutoff coordinates are invalid")
    if kind == "braided" and (arrays["flow_split"].dtype != np.float64 or not np.isfinite(arrays["flow_split"]).all()):
        raise ValueError("braided flow split is invalid")
    if metadata.get("terrain_identity_sha256", terrain_identity) != terrain_identity:
        raise ValueError(kind + " terrain identity mismatch")


def _code_pins():
    paths = [Path(__file__), Path(load_delta_candidate_product.__code__.co_filename), Path(load_td_source.__code__.co_filename)]
    return {str(path.resolve()): _sha(path) for path in paths}


def audit(package):
    package = Path(package).resolve()
    summary_path = package / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema") != SCHEMA or summary.get("status") != "candidate_set":
        raise ValueError("summary schema/status mismatch")
    _require_sha(summary.get("summary_body_sha256"), "summary body")
    if hashlib.sha256(_canonical_summary(summary)).hexdigest() != summary["summary_body_sha256"]:
        raise ValueError("summary body hash mismatch")
    source = summary["source"]
    source_path = Path(source["path"])
    if _sha(source_path) != source["sha256"]:
        raise ValueError("source file SHA mismatch")
    if source_path.resolve() != PRIMARY_PATH.resolve() or source["sha256"] != PRIMARY_SHA256:
        raise ValueError("candidate package source is not the fixed TD primary source")
    loaded_source = load_td_source()
    if loaded_source["identity_sha256"] != source["identity_sha256"]:
        raise ValueError("external source identity mismatch")
    inputs_info = summary["artifacts"]["inputs"]
    inputs_path = package / inputs_info["path"]
    inputs = load_bundle(inputs_path, expected_sha256=inputs_info["sha256"], validator=_validate_inputs)
    if inputs["identity_sha256"] != inputs_info["identity_sha256"]:
        raise ValueError("inputs identity pin mismatch")
    arrays, metadata = inputs["arrays"], inputs["metadata"]
    if metadata["source_identity_sha256"] != source["identity_sha256"] or metadata["source_file_sha256"] != source["sha256"]:
        raise ValueError("inputs source identity mismatch")
    graph = summary["parent_graph_identity_sha256"]
    geometry = summary["parent_geometry_identity_sha256"]
    _require_sha(graph, "parent graph identity")
    _require_sha(geometry, "parent geometry identity")
    if REFERENCE_REPORT.is_file():
        reference = json.loads(REFERENCE_REPORT.read_text(encoding="utf-8"))
        if graph != reference.get("graph_identity_sha256"):
            raise ValueError("parent graph identity is not the pinned TD reference graph")
    if geometry != PARENT_GEOMETRY_IDENTITY:
        raise ValueError("parent geometry identity is not the pinned local geometry")
    if metadata["parent_graph_identity_sha256"] != graph or metadata["parent_geometry_identity_sha256"] != geometry:
        raise ValueError("inputs parent identity mismatch")
    terrain = TerrainGrid(
        arrays["terrain_elevation_m"], arrays["terrain_valid_mask"],
        metadata["origin_x_m"], metadata["origin_z_m"], metadata["spacing_m"], metadata["spacing_m"],
        "generated_terrain", source["identity_sha256"], source["sha256"],
        vertical_datum="sea_zero_m", model_version="Terrain Diffusion", generation_seed=20261001,
        condition_summary="pinned TD source window", source_path=str(PRIMARY_PATH))
    if terrain.identity_sha256 != summary["terrain_identity_sha256"] or metadata["terrain_identity_sha256"] != terrain.identity_sha256:
        raise ValueError("terrain identity mismatch")
    delta_info = summary["artifacts"]["delta"]
    delta_path = package / delta_info["path"]
    delta = load_delta_candidate_product(delta_path, expected_sha256=delta_info["sha256"])
    if delta["identity_sha256"] != delta_info["identity_sha256"]:
        raise ValueError("delta identity pin mismatch")
    if delta["metadata"]["parent_graph_identity_sha256"] != graph or delta["metadata"]["parent_geometry_identity_sha256"] != geometry or delta["metadata"]["terrain_identity_sha256"] != summary["terrain_identity_sha256"]:
        raise ValueError("delta parent identity mismatch")
    if not np.array_equal(delta["arrays"]["terrain_elevation_m"], arrays["terrain_elevation_m"]) or not np.array_equal(delta["arrays"]["terrain_valid_mask"], arrays["terrain_valid_mask"]):
        raise ValueError("delta terrain differs from inputs")
    if not np.array_equal(delta["arrays"]["land_mask"], arrays["land_mask"]) or not np.array_equal(delta["arrays"]["water_mask"], arrays["water_mask"]):
        raise ValueError("delta masks differ from inputs")
    for kind in ARTIFACTS:
        info = summary["artifacts"][kind]
        path = package / info["path"]
        record = load_bundle(path, expected_sha256=info["sha256"], validator=lambda value, item=kind: _validate_generic(value, item, arrays["terrain_elevation_m"].shape, graph, geometry, summary["terrain_identity_sha256"], arrays["terrain_valid_mask"]))
        if record["identity_sha256"] != info["identity_sha256"]:
            raise ValueError(kind + " identity pin mismatch")
    _all_false(summary.get("capabilities"), "summary capabilities")
    return {"schema": "td-real-morphology-candidate-audit-v1", "status": "passed", "package": str(package), "source": source, "summary_body_sha256": summary["summary_body_sha256"], "artifacts": {name: dict(summary["artifacts"][name]) for name in summary["artifacts"]}, "code_pins": _code_pins(), "failures": []}


def write_audit(package, output):
    output = Path(output).resolve()
    target = output / "audit.json"
    if target.exists():
        raise FileExistsError(target)
    try:
        result = audit(package)
    except Exception as error:
        result = {"schema": "td-real-morphology-candidate-audit-v1", "status": "refused", "package": str(Path(package).resolve()), "code_pins": _code_pins(), "failures": [f"{type(error).__name__}: {error}"]}
    output.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_audit(args.package, args.output)
    print(json.dumps({"status": result["status"], "output": str((args.output / "audit.json").resolve())}, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
