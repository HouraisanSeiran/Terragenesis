"""Accepted v8 receiver evidence to isolated one-round sediment candidates."""

from dataclasses import asdict
from collections import deque
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index, _load, _json, _memory
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import save_td_source as save_td_source
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.geology import load_material_field
from terrain_pipeline.td_basin_morphology import generate_morphology, save_morphology, load_morphology, DEFAULT_PARAMETERS
from terrain_pipeline.td_surface_reaches import _hash, _plain, _freeze

ROOT = Path(__file__).resolve().parents[1]
MATERIAL_PATH = ROOT / "verification/td-basin-generation/B-20261001T184152639830Z/material/material.npz"
MATERIAL_SHA = "598d50701e02c9419ebc8ec47e1cc46a881e869e58d8837ac38a3eac45cf7b3a"
MATERIAL_ID = "8500191a992740ba4645d2e039ea00dd7a161108a8a680ef58122b3782cd2157"
SCHEMA = "td-accepted-water-morphology-v1"
PHYSICS = dict(substep_s=1.25, face_conductance_m_s=.6, surface_evaporation_mm_h=.15,
               wet_threshold_m=1e-9, max_substeps=100000, max_work_face_steps=6000000000)
FLAGS = dict(hydraulic_ready=False, transient_converged=False, morphology_flux_ready=False,
             natural_outlet_verified=False, publishable=False)
KINDS = {"valley_incision": "breach", "source_deposition": "deposition"}


def _inputs(input_index, acceptance_arguments, source_record, material_record, scope, expected_parameters, expected_runoff):
    if scope not in ("original_td", "synthetic_fixture"):
        raise ValueError("explicit known candidate scope required")
    accepted = load_hour_pages_index(input_index, **acceptance_arguments)
    if not all(value["numerical_gate_passed"] for value in accepted["scenarios"].values()):
        raise ValueError("both complete numerical 1mm/1percent gates required")
    source = load_td_source_bundle(**source_record)
    hierarchy = load_basin_hierarchy(**acceptance_arguments["hierarchy_record"])
    material = load_material_field(**material_record)
    topology, geometry = hierarchy["arrays"], source["arrays"]
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"] or any(not np.array_equal(topology[name], geometry[name]) for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask")):
        raise ValueError("original source/hierarchy bed and masks identity mismatch")
    for name in ("spacing_m", "origin_m_xz"):
        if hierarchy["metadata"][name] != source["metadata"][name] or material["metadata"][name] != source["metadata"][name]:
            raise ValueError("material/source/hierarchy grid mismatch")
    if material["metadata"]["shape"] != list(geometry["height_m"].shape) or not np.array_equal(material["arrays"]["protected_mask"], geometry["protected_mask"]):
        raise ValueError("material/source coverage mismatch")
    if np.any(geometry["protected_mask"]) or not np.all(geometry["valid_mask"]):
        raise ValueError("protected/unknown domain rejected for this candidate scope")
    if scope == "original_td":
        if Path(material_record["path"]).resolve() != MATERIAL_PATH.resolve() or material_record["expected_sha256"] != MATERIAL_SHA or material_record["expected_identity"] != MATERIAL_ID or source["metadata"]["source_sha256"] != PRIMARY_SHA256:
            raise ValueError("original TD requires fixed primary and issue52 material pins")
        parameters, runoff = PHYSICS, asdict(RunoffParameters())
        if expected_parameters not in (None, PHYSICS) or expected_runoff not in (None, runoff):
            raise ValueError("original TD physical configuration cannot be overridden")
    else:
        if geometry["height_m"].size > 4096 or expected_parameters is None or expected_runoff is None:
            raise ValueError("tiny fixture needs explicit predeclared physical configuration")
        parameters, runoff = dict(expected_parameters), dict(expected_runoff)
    index = _json(dict(path=str(input_index), expected_sha256=acceptance_arguments["expected_sha256"]))
    for scenario in ("ordinary", "strong"):
        first = _load(index["scenarios"][scenario]["pages"]["1.25"][0]["storage"])
        if first["metadata"]["parameters"] != parameters or first["metadata"]["runoff_parameters"] != runoff:
            raise ValueError("accepted physical configuration differs from predeclaration")
        if scope == "original_td":
            forcing = _json(acceptance_arguments["forcing_records"][scenario])
            if forcing["rain_mm_h"] != [10. if scenario == "ordinary" else 30.] * 6 + [0.] * 18:
                raise ValueError("original TD forcing differs from frozen scenario")
        del first
    record = index["scenarios"]["ordinary"]["pages"]["1.25"][-1]["checkpoint"]
    checkpoint = _load(record, True)
    return accepted, source, hierarchy, material, checkpoint, record


def _check_morphology(morphology, source, hierarchy, material, checkpoint):
    arrays, metadata = morphology["arrays"], morphology["metadata"]
    original = source["arrays"]
    opened = np.flatnonzero(original["open_boundary_mask"].ravel() & (hierarchy["arrays"]["receiver"] == -1)).tolist()
    if metadata["parameters"] != {**DEFAULT_PARAMETERS, "engineering_open_boundary_cell_ids": opened} or metadata["material_parameters"] != material["metadata"]["parameters"]:
        raise ValueError("candidate deviates from frozen morphology parameters")
    for name in ("spacing_m", "origin_m_xz"):
        if metadata[name] != source["metadata"][name]:
            raise ValueError("candidate material coordinates changed")
    if not np.array_equal(arrays["valid_mask"], original["valid_mask"]) or not np.array_equal(arrays["protected_mask"], original["protected_mask"]):
        raise ValueError("candidate source masks changed")
    receiver = hierarchy["arrays"]["receiver"]
    bed = original["height_m"].ravel()
    slope = np.zeros(len(bed))
    sources = np.flatnonzero(receiver >= 0)
    slope[sources] = (bed[sources] - bed[receiver[sources]]) / source["metadata"]["spacing_m"]
    volume = checkpoint["arrays"]["cumulative_routed_volume_m3"].reshape(original["height_m"].shape)
    duration = checkpoint["arrays"]["cumulative_wet_duration_s"].reshape(volume.shape)
    potential = .15 * material["arrays"]["erodibility"] * material["arrays"]["weak_path_preference"]
    potential *= np.log1p(volume / 1000) * (-np.expm1(-duration / 3600)) * np.sqrt(slope.reshape(volume.shape))
    erosion = np.minimum(potential, material["arrays"]["erodible_thickness_m"])
    remaining = material["arrays"]["erodible_thickness_m"] - erosion
    if not np.allclose(arrays["erosion_depth_m"], erosion, rtol=1e-12, atol=1e-12) or not np.allclose(arrays["remaining_erodible_thickness_m"], remaining, rtol=1e-12, atol=1e-12):
        raise ValueError("candidate erosion/thickness does not match actual water/material")
    count = len(receiver)
    indegree = np.bincount(receiver[sources], minlength=count)
    queue = deque(np.flatnonzero(indegree == 0).tolist())
    incoming = np.zeros(count)
    transported = np.zeros(count)
    deposited = np.zeros(count)
    stored = np.zeros(count)
    exported = np.zeros(count)
    area = source["metadata"]["spacing_m"] ** 2
    config = material["metadata"]["parameters"]
    solid = erosion.ravel() * area * (1 - config["source_porosity"])
    capacity = np.where((volume > 0) & (duration > 0), .002 * volume, 0).ravel()
    deposit_cap = 4 * area * (1 - config["deposit_porosity"])
    processed = 0
    while queue:
        cell = queue.popleft()
        processed += 1
        available = incoming[cell] + solid[cell]
        target = receiver[cell]
        movable = min(available, capacity[cell])
        if target >= 0:
            transported[cell] = movable
            incoming[target] += movable
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
        elif cell in opened:
            exported[cell] = movable
        else:
            movable = 0.
        remainder = max(0., available - movable)
        if metadata["candidate_kind"] == "deposition" and incoming[cell] > 0:
            deposited[cell] = min(remainder, incoming[cell], deposit_cap)
        stored[cell] = remainder - deposited[cell]
    if processed != count:
        raise ValueError("candidate receiver cycle")
    for name, expected in (("incoming_solid_m3", incoming), ("transported_solid_m3", transported),
                           ("deposited_solid_m3", deposited), ("stored_solid_m3", stored), ("exported_solid_m3", exported)):
        if not np.allclose(arrays[name].ravel(), expected, rtol=1e-12, atol=1e-12):
            raise ValueError("candidate frozen transport/deposition allocation mismatch: " + name)


def _pin(path, bundle):
    return dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"])


def _options(input_index, acceptance_arguments, source_record, material_record, scope, expected_parameters, expected_runoff):
    return dict(input_index=str(input_index), acceptance_arguments=_plain(acceptance_arguments), source_record=dict(source_record),
        material_record=dict(material_record), scope=scope, expected_parameters=expected_parameters, expected_runoff=expected_runoff)


def _recheck(options):
    records = [options["source_record"], options["material_record"], options["acceptance_arguments"]["hierarchy_record"],
        options["acceptance_arguments"]["run_inputs_record"], options["acceptance_arguments"]["execution_resource_record"],
        *options["acceptance_arguments"]["forcing_records"].values(),
        dict(path=options["input_index"], expected_sha256=options["acceptance_arguments"]["expected_sha256"])]
    if any(file_sha256(record["path"]) != record["expected_sha256"] for record in records):
        raise ValueError("pinned input changed during candidate processing")
    if _memory()[1] is None:
        raise ValueError("private memory peak evidence required before publication")


def _write_index(path, value):
    value["identity_sha256"] = _hash(value)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("candidate manifest budget exceeded")
    publish_bytes(path, payload)


def export_accepted_water_morphology(input_index, directory, *, acceptance_arguments, source_record, material_record,
                                     scope="original_td", expected_parameters=None, expected_runoff=None):
    options = _options(input_index, acceptance_arguments, source_record, material_record, scope, expected_parameters, expected_runoff)
    accepted, source, hierarchy, material, checkpoint, checkpoint_record = _inputs(**options)
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".water-morphology-", dir=directory.parent))
    try:
        records = {"baseline": dict(source=source_record, hierarchy=acceptance_arguments["hierarchy_record"],
            recoupling_required=False, geometry_changed=False, source_solid_m3=0.)}
        arrays = source["arrays"]
        topology = hierarchy["arrays"]
        opened = np.flatnonzero(arrays["open_boundary_mask"].ravel() & (topology["receiver"] == -1)).tolist()
        for candidate_id, kind in KINDS.items():
            morphology = generate_morphology(arrays["height_m"], arrays["valid_mask"], topology["receiver"],
                checkpoint["arrays"]["cumulative_routed_volume_m3"], checkpoint["arrays"]["cumulative_wet_duration_s"],
                spacing_m=source["metadata"]["spacing_m"], materials=material,
                parameters=dict(engineering_open_boundary_cell_ids=opened), candidate_kind=kind)
            destination = temporary / candidate_id
            save_morphology(morphology, destination / "morphology.npz")
            derived = make_td_source(morphology["arrays"]["height_m"], spacing_m=source["metadata"]["spacing_m"],
                origin_m_xz=source["metadata"]["origin_m_xz"], valid_mask=arrays["valid_mask"], protected_mask=arrays["protected_mask"],
                open_boundary_mask=arrays["open_boundary_mask"], source_sha256=source_record["expected_sha256"])
            save_td_source(destination / "source.npz", derived)
            source_pin = _pin(destination / "source.npz", derived)
            morphology_pin = _pin(destination / "morphology.npz", morphology)
            source_pin["path"] = str(directory / candidate_id / "source.npz")
            morphology_pin["path"] = str(directory / candidate_id / "morphology.npz")
            records[candidate_id] = dict(source=source_pin, morphology=morphology_pin, ledger=dict(morphology["metadata"]["ledger"]),
                recoupling_required=True, geometry_changed=bool(np.any(morphology["arrays"]["height_delta_m"] != 0)),
                topology_rebuild_pending=True, physical_channel_verified=False)
            del morphology, derived
        result = dict(schema=SCHEMA, stage="geometry_only", inputs=options,
            original_source_identity=source["identity_sha256"], original_primary_sha256=source["metadata"]["source_sha256"],
            material_identity=material["identity_sha256"], ordinary_fine_final_checkpoint=checkpoint_record,
            acceptance={key: _plain(value) for key, value in accepted.items() if key != "resource"},
            candidates=records, selection="baseline pending", generation_rounds=1, flags=FLAGS,
            semantics="Finite water/material heuristic; incision is existing-receiver valley erosion, not saddle escape or physical channel width. Closed basins retained. New source and topology require new hydrology after v9 actualTD execution equivalence gate; old v2 coupling unused.")
        _recheck(options)
        _write_index(temporary / "index.json", result)
        _recheck(options)
        temporary.rename(directory)
        return _freeze(result)
    except BaseException:
        shutil.rmtree(temporary)
        raise


def load_accepted_water_morphology(path, *, expected_sha256, expected_identity, input_index, acceptance_arguments, source_record,
                                  material_record, scope="original_td", expected_parameters=None, expected_runoff=None):
    result = _json(dict(path=str(path), expected_sha256=expected_sha256))
    unsigned = {key: value for key, value in result.items() if key != "identity_sha256"}
    if result.get("schema") != SCHEMA or result.get("stage") != "geometry_only" or result.get("identity_sha256") != expected_identity or _hash(unsigned) != expected_identity:
        raise ValueError("candidate manifest external identity/schema rejected")
    options = _options(input_index, acceptance_arguments, source_record, material_record, scope, expected_parameters, expected_runoff)
    accepted, source, hierarchy, material, checkpoint, cp_record = _inputs(**options)
    if result["inputs"] != _plain(options) or result["selection"] != "baseline pending" or result["flags"] != FLAGS or result["ordinary_fine_final_checkpoint"] != cp_record or set(result["candidates"]) != {"baseline", *KINDS}:
        raise ValueError("candidate input/readiness identity mismatch")
    if result["original_source_identity"] != source["identity_sha256"] or result["material_identity"] != material["identity_sha256"] or result["acceptance"] != {key: _plain(value) for key, value in accepted.items() if key != "resource"}:
        raise ValueError("candidate original chain mismatch")
    if result["original_primary_sha256"] != source["metadata"]["source_sha256"] or result["generation_rounds"] != 1 or result["candidates"]["baseline"] != dict(source=source_record, hierarchy=acceptance_arguments["hierarchy_record"], recoupling_required=False, geometry_changed=False, source_solid_m3=0.):
        raise ValueError("baseline source/provenance claim rejected")
    root = Path(path).absolute().parent
    for candidate_id, kind in KINDS.items():
        record = result["candidates"][candidate_id]
        for role in ("source", "morphology"):
            target = Path(record[role]["path"])
            if target.is_symlink() or target.absolute() != root / candidate_id / (role + ".npz"):
                raise ValueError("candidate artifact unsafe layout")
        morphology = load_morphology(**record["morphology"])
        derived = load_td_source_bundle(**record["source"])
        arrays = morphology["arrays"]
        _check_morphology(morphology, source, hierarchy, material, checkpoint)
        if morphology["metadata"]["candidate_kind"] != kind or morphology["metadata"]["material_identity_sha256"] != material["identity_sha256"] or record["ledger"] != morphology["metadata"]["ledger"]:
            raise ValueError("candidate material/ledger identity mismatch")
        if not np.array_equal(arrays["original_height_m"], source["arrays"]["height_m"]) or not np.array_equal(arrays["height_m"], derived["arrays"]["height_m"]) or not np.array_equal(arrays["receiver"], hierarchy["arrays"]["receiver"]):
            raise ValueError("candidate original/derived bed chain mismatch")
        for name, key in (("routed_volume_m3", "cumulative_routed_volume_m3"), ("wet_duration_s", "cumulative_wet_duration_s")):
            if not np.array_equal(arrays[name].ravel(), checkpoint["arrays"][key]):
                raise ValueError("candidate actual receiver evidence mismatch")
        if derived["metadata"]["source_sha256"] != source_record["expected_sha256"] or record["recoupling_required"] is not True or record["topology_rebuild_pending"] is not True:
            raise ValueError("candidate provenance/recoupling claim rejected")
        if record["geometry_changed"] is not bool(np.any(arrays["height_delta_m"] != 0)) or record["physical_channel_verified"] is not False:
            raise ValueError("candidate geometry/certification mismatch")
        for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
            if not np.array_equal(derived["arrays"][name], source["arrays"][name]):
                raise ValueError("derived source masks changed")
        for name in ("spacing_m", "origin_m_xz"):
            if derived["metadata"][name] != source["metadata"][name]:
                raise ValueError("derived source grid changed")
        del morphology, derived
    _recheck(options)
    return _freeze(result)


def rebuild_accepted_candidate(path, directory, *, candidate_id, **load_arguments):
    if candidate_id not in KINDS:
        raise ValueError("explicit derived candidate required")
    accepted = load_accepted_water_morphology(path, **load_arguments)
    source_record = _plain(accepted["candidates"][candidate_id]["source"])
    source = load_td_source_bundle(**source_record)
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".candidate-topology-", dir=directory.parent))
    try:
        hierarchy = build_basin_hierarchy(source)
        save_basin_hierarchy(temporary / "hierarchy.npz", hierarchy)
        record = _pin(temporary / "hierarchy.npz", hierarchy)
        record["path"] = str(directory / "hierarchy.npz")
        result = dict(schema="td-accepted-candidate-topology-v1", candidate_id=candidate_id,
            parent_manifest=dict(path=str(path), expected_sha256=load_arguments["expected_sha256"], expected_identity=load_arguments["expected_identity"]),
            source=source_record, hierarchy=record, recoupling_required=True, selection="baseline pending", flags=FLAGS)
        _recheck(_plain(accepted["inputs"]))
        if file_sha256(source_record["path"]) != source_record["expected_sha256"]:
            raise ValueError("derived source changed during rebuild")
        _write_index(temporary / "index.json", result)
        temporary.rename(directory)
        return _freeze(result)
    except BaseException:
        shutil.rmtree(temporary)
        raise
