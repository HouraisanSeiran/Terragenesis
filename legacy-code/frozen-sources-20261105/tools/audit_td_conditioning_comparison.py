"""Cold independent geometry, forcing and water-ledger conditioning audit."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import load_runoff_exchange
from terrain_pipeline.td_basin_source import load_td_source, load_td_source_bundle
from terrain_pipeline.td_bounded_conditioning import DEFAULT_PARAMETERS, load_conditioning
from terrain_pipeline.td_material_field import load_material_field
from tools.audit_td_runoff_exchange import audit_arrays, verify_controls

BASELINE_SHA = "cd78c2f2ce9c6a1abbd98ae7ee528079dfb2ee1b5ce2905458e64137aa868e5f"
BASELINE_AUDIT_SHA = "821309de91dcd634193d622c910e4fe976f2e9e3602aa311cfe73d30ac342ff6"
SPILL_SHA = "f1d6e89b3bb642f6ede52d231fa340bb41a8a03aa479ab4e889c648f361565af"
CASES = {"normal-spatial-recession-24h": (30., 86400.),
         "strong-spatial-recession-6h": (120., 21600.)}
CANDIDATES = ("baseline", "limited_fill", "limited_breach", "mixed")
CODE = {"terrain_pipeline/td_bounded_conditioning.py", "terrain_pipeline/td_basin_source.py",
        "terrain_pipeline/td_basin_hierarchy.py", "terrain_pipeline/td_basin_overflow.py",
        "terrain_pipeline/td_basin_runoff_exchange.py", "terrain_pipeline/td_basin_overflow_radau.py",
        "terrain_pipeline/rainfall_runoff.py", "tools/prepare_td_conditioning_comparison.py"}
FLAGS = {"hydraulic_ready", "natural_outlet_verified", "publishable", "transient_converged",
         "full_coupled_timestep_refinement_passed", "permanent_trunk_ready", "tailwater_verified",
         "continuous_fine_corridor_ready", "natural", "hydraulic", "dynamic_erosion_or_deposition"}
FORBIDDEN = (
    "terrain_pipeline.td_bounded_conditioning.build_conditioning_candidates",
    "terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy",
    "terrain_pipeline.td_basin_overflow.build_overflow_topology",
    "terrain_pipeline.td_basin_overflow.simulate_overflow",
    "terrain_pipeline.td_basin_runoff_exchange.simulate_runoff_exchange",
    "terrain_pipeline.td_basin_runoff_exchange.simulate_rainfall_runoff",
    "terrain_pipeline.td_basin_runoff_exchange.Radau",
    "terrain_pipeline.td_basin_overflow_radau.simulate_radau_overflow",
    "terrain_pipeline.td_basin_overflow_radau.Radau",
    "terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff",
    "terrain_pipeline.td_material_field.make_material_field",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, "duplicate JSON key: " + name)
            result[name] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    path = Path(path)
    require(path.stat().st_size <= 128 * 1024**2, "JSON input exceeds 128MiB")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)


def check_flags(value):
    if isinstance(value, dict):
        for name, child in value.items():
            if name in FLAGS:
                require(child is False, "uncertified flag must remain false: " + name)
            check_flags(child)
    elif isinstance(value, list):
        for child in value:
            check_flags(child)


def pinned_path(pin, base, seen, *, local=False):
    supplied = Path(pin["path"])
    resolved = (base / supplied).resolve(strict=True)
    boundary = base.resolve() if local else ROOT.resolve()
    require(resolved.is_relative_to(boundary), "input path escapes permitted directory")
    expected = pin["sha256"]
    require(isinstance(expected, str) and len(expected) == 64 and
            all(character in "0123456789abcdef" for character in expected), "invalid SHA256 pin")
    require(file_sha256(resolved) == expected, "input SHA256 mismatch: " + str(resolved))
    if "bytes" in pin:
        require(pin["bytes"] == resolved.stat().st_size, "stored input size mismatch")
    seen[resolved] = expected
    return resolved


def pinned_json(pin, base, seen, *, local=False):
    return read_json(pinned_path(pin, base, seen, local=local))


def numeric_equal(actual, expected, name):
    require(type(actual) in (int, float) and math.isfinite(actual) and
            math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8),
            "stored summary differs from arrays: " + name)


def array_equal(actual, expected, name):
    require(np.array_equal(actual, expected), "saved array mismatch: " + name)


def audit_drainage(hierarchy):
    arrays = hierarchy["arrays"]
    valid = arrays["valid_mask"].ravel()
    owners = arrays["contribution_owner"].ravel()
    terminals = np.flatnonzero(valid & (arrays["receiver"] < 0))
    boundary = terminals[arrays["open_boundary_mask"].ravel()[terminals]]
    counts = np.bincount(owners[valid], minlength=len(arrays["node_parent"]))
    largest = int(counts.argmax())
    area = float(hierarchy["metadata"]["spacing_m"]) ** 2
    return {"basin_count": len(terminals), "largest_static_catchment_area_m2": float(counts[largest] * area),
            "largest_static_catchment_leaf_id": largest, "engineering_outlet_terminal_count": len(boundary),
            "static_boundary_draining_area_m2": float(np.isin(owners[valid], owners[boundary]).sum() * area),
            "retained_internal_terminal_count": len(terminals) - len(boundary),
            "semantics": "bed-receiver connectivity only; no claim of permanent river, wet flow, or natural sea outlet"}


def audit_topology(hierarchy, topology):
    arrays, curves = hierarchy["arrays"], topology["arrays"]
    metadata = topology["metadata"]
    require(metadata["schema"] == "td-original-bed-basin-overflow-v1" and
            metadata["source_identity_sha256"] == hierarchy["metadata"]["source_identity_sha256"] and
            metadata["hierarchy_identity_sha256"] == hierarchy["identity_sha256"],
            "new-bed topology source/hierarchy mismatch")
    for name in ("spacing_m", "origin_m_xz"):
        require(metadata[name] == hierarchy["metadata"][name], "topology grid mismatch")
    active = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    owners, bed = arrays["contribution_owner"].ravel(), arrays["height_m"].ravel()
    leaves = np.unique(owners[active])
    array_equal(curves["leaf_ids"], leaves, "actual contribution leaves")
    offsets = curves["curve_offsets"]
    require(offsets.dtype.kind in "iu" and len(offsets) == len(leaves) + 1 and offsets[0] == 0 and
            np.all(np.diff(offsets) > 0) and offsets[-1] == len(curves["curve_level_m"]) ==
            len(curves["curve_area_m2"]), "invalid saved topology curve offsets")
    area = metadata["spacing_m"] ** 2
    for position, leaf in enumerate(leaves):
        heights, counts = np.unique(np.sort(bed[active & (owners == leaf)]), return_counts=True)
        start, end = offsets[position:position + 2]
        array_equal(curves["curve_level_m"][start:end], heights, "new-bed sorted leaf levels")
        array_equal(curves["curve_area_m2"][start:end], counts * area, "new-bed leaf level areas")
        numeric_equal(float(curves["leaf_area_m2"][position]), float(counts.sum() * area), "leaf area")
    pairs = {}
    leaf_set = set(map(int, leaves))
    columns = arrays["height_m"].shape[1]
    for position, cells in enumerate(arrays["face_cells"]):
        first, second = map(int, cells)
        left, right = int(owners[first]), int(owners[second])
        if left == right or left not in leaf_set or right not in leaf_set:
            continue
        pair = tuple(sorted((left, right)))
        points = []
        for cell in (first, second):
            row, column = divmod(cell, columns)
            point = (metadata["origin_m_xz"][0] + column * metadata["spacing_m"],
                     bed[cell], metadata["origin_m_xz"][1] + row * metadata["spacing_m"])
            points.append([float(value).hex() for value in point])
        face_id = "face:" + digest([metadata["source_identity_sha256"], sorted(points)])
        record = {"face_index": position, "face_id": face_id, "leaf_ids": list(pair),
                  "cell_ids": [first, second], "sill_m": float(max(bed[first], bed[second]))}
        if pair not in pairs or (record["sill_m"], face_id) < (pairs[pair]["sill_m"], pairs[pair]["face_id"]):
            pairs[pair] = record
    require(topology["faces"] == list(pairs.values()), "saved faces differ from actual lowest new-bed D4 sills")
    boundaries = []
    rows = arrays["height_m"].shape[0]
    for cell in np.flatnonzero(arrays["open_boundary_mask"].ravel()):
        leaf = int(owners[cell])
        if leaf not in leaf_set:
            continue
        row, column = divmod(int(cell), columns)
        sides = int(row == 0) + int(row == rows - 1) + int(column == 0) + int(column == columns - 1)
        boundaries.append({"cell_id": int(cell), "leaf_id": leaf, "sill_m": float(bed[cell]),
                           "width_m": sides * metadata["spacing_m"], "face_count": sides})
    require(topology["engineering_boundaries"] == boundaries, "new-bed engineering boundary mismatch")
    require(metadata["leaf_count"] == len(leaves) and metadata["physical_face_count"] == len(pairs) and
            metadata["engineering_boundary_face_count"] == len(boundaries), "topology counts mismatch")


def aggregate_rain(grid, hierarchy, topology):
    arrays = hierarchy["arrays"]
    active = arrays["valid_mask"] & ~arrays["protected_mask"]
    owners = arrays["contribution_owner"][active]
    leaves = topology["arrays"]["leaf_ids"]
    factors = []
    for leaf in leaves:
        values = grid[active][owners == leaf]
        require(values.size > 0, "leaf lacks immutable rainfall support")
        factors.append(float(values.sum() / values.size))
    return np.asarray(factors)


def audit_conditioning(bundle, candidate_id, source, hierarchy, materials, requests):
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    base = source["arrays"]
    require(metadata["schema"] == "td-bounded-conditioning-v1" and metadata["candidate_id"] == candidate_id,
            "conditioning schema/candidate mismatch")
    require(metadata["source_identity_sha256"] == source["identity_sha256"] and
            metadata["source_metadata"] == source["metadata"] and
            metadata["hierarchy_identity_sha256"] == hierarchy["identity_sha256"] and
            metadata["material_identity_sha256"] == materials["identity_sha256"] and
            metadata["spill_identity_sha256"] == requests["identity_sha256"], "conditioning parent identity mismatch")
    for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
        array_equal(arrays[name], base[name], "immutable conditioning " + name)
    array_equal(arrays["original_height_m"], base["height_m"], "original bed")
    array_equal(arrays["erodible_thickness_m"], materials["arrays"]["erodible_thickness_m"], "material thickness")
    array_equal(arrays["contribution_owner"], hierarchy["arrays"]["contribution_owner"], "parent contribution")
    array_equal(arrays["receiver"].ravel(), hierarchy["arrays"]["receiver"], "parent receiver")
    owner = arrays["contribution_owner"]
    unknown = np.where(owner >= 0, hierarchy["arrays"]["node_unknown_contact"][np.maximum(owner, 0)], True)
    array_equal(arrays["unknown_contact_mask"], unknown, "unknown-contact coverage")
    delta = arrays["height_m"] - base["height_m"]
    array_equal(arrays["delta_m"], delta, "conditioning delta")
    blocked = ~base["valid_mask"] | base["protected_mask"] | unknown
    require(not np.any(delta[blocked]), "conditioning changed invalid/protected/unknown cells")
    require(not np.any(delta[base["open_boundary_mask"]]), "conditioning changed engineering open-boundary cells")
    config = metadata["parameters"]
    require(config == DEFAULT_PARAMETERS and metadata["seed"] == config["seed"] and
            metadata["budget_status"] == "explicit_generative_uncalibrated",
            "conditioning differs from frozen default budgets/seed or budget designation")
    require(np.all(-delta <= config["max_cut_m"]) and np.all(delta <= config["max_fill_m"]) and
            np.all(-delta <= arrays["erodible_thickness_m"]), "independent per-cell cut/fill/thickness budget failed")
    require(metadata["material_parameters"] == materials["metadata"]["parameters"], "material parameters changed")
    spacing = source["metadata"]["spacing_m"]
    cut, fill = (float(np.maximum(sign * delta, 0).sum() * spacing**2) for sign in (-1, 1))
    require(cut <= config["max_cut_m3"] and fill <= config["max_fill_m3"], "independent total geometry budget failed")
    material = metadata["material_parameters"]
    cut_solid = cut * (1 - material["source_porosity"])
    fill_solid = fill * (1 - material["deposit_porosity"])
    density = material["solid_density_kg_m3"]
    ledger = {"cut_geometry_m3": cut, "fill_geometry_m3": fill, "cut_solid_m3": cut_solid,
              "fill_solid_m3": fill_solid, "external_initial_material_input_solid_m3": fill_solid,
              "external_initial_material_output_solid_m3": cut_solid,
              "net_external_initial_material_input_solid_m3": fill_solid - cut_solid,
              "external_initial_material_input_kg": fill_solid * density,
              "external_initial_material_output_kg": cut_solid * density,
              "net_external_initial_material_input_kg": (fill_solid - cut_solid) * density,
              "internal_material_transfer_solid_m3": 0.,
              "semantics": "initial geometry only; cut exported and fill externally supplied; no dynamic erosion or deposition"}
    require(set(metadata["geometry_ledger"]) == set(ledger), "solid ledger fields mismatch")
    for name, value in ledger.items():
        if isinstance(value, str):
            require(metadata["geometry_ledger"][name] == value, "external material semantics changed")
        else:
            numeric_equal(metadata["geometry_ledger"][name], value, name)
    paths = {record["face_id"]: record for record in requests["paths"] if record["status"] == "bounded_candidate_request"}
    treatments = metadata["accepted_treatments"] + metadata["rejected_treatments"]
    require(len(treatments) == len(paths) and len({item["face_id"] for item in treatments}) == len(paths),
            "conditioning treatment coverage or duplicates mismatch")
    for treatment in treatments:
        original = paths[treatment["face_id"]]
        for name in ("path_cell_ids", "directed_face_cell_ids", "source_basin_id", "destination_basin_id", "sill_m"):
            require(treatment[name] == original[name], "treatment differs from pinned spill path")
        ordinary = [item for item in original["bounded_candidate_requests"] if item["case"] == "normal-24h"]
        require(len(ordinary) == 1 and treatment["request_identity_sha256"] == ordinary[0]["identity_sha256"] and
                treatment["ordinary_water_volume_m3"] == ordinary[0]["routed_volume_m3"],
                "treatment not weighted by pinned ordinary request")
        kind = "fill" if candidate_id == "limited_fill" else "breach"
        if candidate_id == "mixed":
            random_bytes = hashlib.sha256((str(config["seed"]) + ":" + treatment["face_id"] + ":kind").encode("ascii")).digest()
            kind = "fill" if (int.from_bytes(random_bytes[:8], "big") + 1) / (2**64 + 2) < .5 else "breach"
        require(treatment["kind"] == kind, "treatment mode or mixed assignment changed")
    require(len(metadata["accepted_treatments"]) <= config["max_treatments"], "treatment count exceeds budget")
    original = base["height_m"].ravel()
    expected = original.copy()
    occupied = np.zeros(original.size, bool)
    for treatment in metadata["accepted_treatments"]:
        path = np.asarray(treatment["path_cell_ids"], dtype=np.int64)
        if treatment["kind"] == "fill":
            cells = np.flatnonzero((owner.ravel() == treatment["source_basin_id"]) & (original < treatment["sill_m"]))
            target = np.full(len(cells), treatment["sill_m"])
            support = np.union1d(path, cells)
        else:
            cells = path
            target = original[cells].copy()
            for position in range(1, len(cells)):
                target[position] = min(original[cells[position]], target[position - 1] - spacing * config["min_slope"])
            require(target[0] == original[cells[0]] and target[-1] == original[cells[-1]], "breach changed fixed anchors")
            support = path
        require(not occupied[support].any() and not blocked.ravel()[support].any(), "overlap or blocked treatment support")
        change = target - original[cells]
        numeric_equal(treatment["cut_geometry_m3"], float(np.maximum(-change, 0).sum() * spacing**2), "treatment cut")
        numeric_equal(treatment["fill_geometry_m3"], float(np.maximum(change, 0).sum() * spacing**2), "treatment fill")
        occupied[support] = True
        expected[cells] = original[cells] + change
    array_equal(arrays["height_m"].ravel(), expected, "independent accepted-treatment bed")
    return {"changed_cells": int(np.count_nonzero(delta)), "absolute_delta_sum_m": float(np.abs(delta).sum()),
            "geometry_ledger": ledger, "accepted_treatment_count": len(metadata["accepted_treatments"]),
            "external_material_source": "explicit generative initial supply, not observed sediment or event erosion"}


def audit_event(event, topology, level, name, factor, runoff_parameters):
    arrays, metadata = event["arrays"], event["metadata"]
    verify_controls(event, level)
    rate, duration = CASES[name]
    steps = int(duration / 300.)
    require(metadata["duration_s"] == duration and metadata["timestep_s"] == 300. and metadata["steps"] == steps,
            "event duration/save interval mismatch")
    require(metadata["runoff_metadata"]["source_id"] == name, "event case source identity mismatch")
    rain = np.zeros((steps, len(factor)))
    rain[:steps // 2] = rate * factor
    require(np.allclose(arrays["rain_mm_h"], rain, rtol=1e-13, atol=1e-13), "actual rain differs from immutable grid aggregation")
    array_equal(arrays["area_m2"], topology["arrays"]["leaf_area_m2"], "rainfall areas")
    expected_volume = arrays["rain_mm_h"] * arrays["area_m2"] / 1000. * (300. / 3600.)
    require(np.allclose(arrays["rain_volume_m3"], expected_volume, rtol=1e-12, atol=1e-8), "actual rain-volume conversion mismatch")
    require(set(level) == {"level", "controls", "event", "rain_m3", "boundary_outflow_m3", "final_surface_m3", "work"},
            "unexpected unverified event summary fields")
    require(metadata["runoff_metadata"]["parameters"] == runoff_parameters,
            "event runoff parameters differ from explicit configuration")
    array_equal(arrays["soil_mm"][0], np.full(len(factor), 30.), "initial soil moisture 30mm")
    for store in ("fast_mm", "slow_mm", "surface_volume_m3"):
        require(not np.any(arrays[store][0]), "initial fast/slow/surface inventory is not zero: " + store)
    for store in ("soil", "fast", "slow"):
        require(metadata["runoff_metadata"]["parameters"]["initial_" + store + "_mm"] == (30. if store == "soil" else 0.),
                "initial runoff parameter differs from baseline physics")
    require(metadata["parameters"] == {"timestep_s": 300., "duration_s": duration,
            "face_conductance_m_s": .6, "boundary_conductance_m_s": .6}, "surface physical parameters changed")
    ledger = audit_arrays(topology, event)
    numeric_equal(level["rain_m3"], float(arrays["rain_volume_m3"].sum()), "event rain summary")
    numeric_equal(level["boundary_outflow_m3"], float(arrays["engineering_boundary_outflow_m3"].sum()), "boundary summary")
    numeric_equal(level["final_surface_m3"], float(arrays["surface_volume_m3"][-1].sum()), "final surface summary")
    require(level["work"] == metadata["work"], "event work summary differs from saved metadata")
    return ledger


def compare_events(first, second):
    require(first["identity_sha256"] != second["identity_sha256"], "nominee repeats one event as two refinement levels")
    for name in ("parameters", "runoff_metadata", "topology_identity_sha256", "hierarchy_identity_sha256", "source_identity_sha256"):
        require(first["metadata"][name] == second["metadata"][name], "nominee physics or forcing metadata changed")
    for name in ("rain_mm_h", "area_m2", "outflow_volume_m3", "soil_mm", "fast_mm", "slow_mm"):
        array_equal(first["arrays"][name], second["arrays"][name], "nominee same forcing " + name)
    coarse, fine = first["arrays"], second["arrays"]
    stage = float(np.max(np.abs(coarse["stage_m"] - fine["stage_m"])))
    coarse_net = np.cumsum(coarse["face_forward_m3"] - coarse["face_reverse_m3"], axis=0)
    fine_net = np.cumsum(fine["face_forward_m3"] - fine["face_reverse_m3"], axis=0)
    numerator = np.abs(coarse_net - fine_net).sum(axis=1)
    denominator = np.abs(fine_net).sum(axis=1)
    relative = float(np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0).max())
    zero_reference_ok = not np.any((denominator == 0) & (numerator > 1e-8))
    passed = stage <= .001 and relative <= .01 and zero_reference_ok
    return {"max_stage_error_m": stage, "max_cumulative_net_relative_l1": relative,
            "zero_reference_passed": bool(zero_reference_ok), "surface_time_refinement_passed": bool(passed),
            "thresholds": {"stage_m": .001, "cumulative_net_relative_l1": .01},
            "scope": "fixed 300s runoff; surface-integrator refinement only"}


def audit_saved(directory, expected_sha256, seen):
    index = pinned_json({"path": "index.json", "sha256": expected_sha256}, directory, seen, local=True)
    require(index["schema"] == "td-bounded-conditioning-comparison-v1" and
            index["status"] == "ready_for_independent_audit" and index["selected_candidate"] == "baseline",
            "comparison schema/status or baseline selection mismatch")
    for name in ("hydraulic_ready", "natural_outlet_verified", "publishable", "full_coupled_timestep_refinement_passed", "permanent_trunk_ready"):
        require(index.get(name) is False, "missing or promoted comparison flag: " + name)
    check_flags(index)
    config = index["configuration"]
    require(read_json(directory / "configuration.json") == config, "configuration file differs from index")
    seen[directory / "configuration.json"] = file_sha256(directory / "configuration.json")
    require(set(config["code_sha256"]) == CODE and config["max_new_solves"] == 8 and
            config["runoff_parameters"] == asdict(RunoffParameters()) and
            config["initial_water"] == "same default soil moisture (30mm), zero fast/slow/surface; initialized on each new bed, not transferred from old events",
            "configuration code coverage, solve budget or initial-water contract mismatch")
    for name, expected in config["code_sha256"].items():
        pinned_path({"path": name, "sha256": expected}, ROOT, seen)
    require(config["baseline_index"]["sha256"] == BASELINE_SHA and
            config["baseline_audit"]["sha256"] == BASELINE_AUDIT_SHA and config["spill_index"]["sha256"] == SPILL_SHA,
            "frozen parent pins changed")
    baseline = pinned_json(config["baseline_index"], ROOT, seen)
    baseline_audit = pinned_json(config["baseline_audit"], ROOT, seen)
    require(baseline["schema"] == "td-runoff-exchange-refinement-v1" and baseline_audit["status"] == "passed" and
            baseline_audit["index_sha256"] == BASELINE_SHA and baseline_audit["cold_read"] is True and
            baseline_audit["solver_advanced"] is False, "pinned baseline audit not accepted")
    check_flags(baseline)
    check_flags(baseline_audit)
    spills = pinned_json(config["spill_index"], ROOT, seen)
    require(spills["schema"] == "td-stable-spill-paths-preparation-v1", "spill schema mismatch")
    check_flags(spills)
    spill_directory = Path(config["spill_index"]["path"]).parent
    requests = pinned_json(spills["requests"], spill_directory, seen, local=True)
    require(requests["schema"] == "td-stable-spill-paths-v1" and requests["identity_sha256"] ==
            spills["request_report_identity_sha256"] == digest({name: value for name, value in requests.items() if name != "identity_sha256"}),
            "spill request identity mismatch")
    for pin in spills["source_pins"]:
        pinned_path(pin, ROOT, seen)
    hierarchy_pin = next(pin for pin in spills["source_pins"] if pin["path"].endswith("hierarchy.npz"))
    require(config["hierarchy"] == hierarchy_pin and config["baseline_topology"] == baseline["configuration"]["topology"],
            "baseline hierarchy/topology pin mismatch")
    hierarchy = load_basin_hierarchy(pinned_path(hierarchy_pin, ROOT, seen), expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    topology_pin = config["baseline_topology"]
    topology = load_overflow_topology(pinned_path(topology_pin, ROOT, seen), expected_sha256=topology_pin["sha256"],
                                     expected_identity=topology_pin["identity_sha256"])
    source = load_td_source()
    require(hierarchy["metadata"]["source_identity_sha256"] == source["identity_sha256"] and
            requests["source_identity_sha256"] == source["identity_sha256"] and
            requests["hierarchy_identity_sha256"] == hierarchy["identity_sha256"] and
            requests["topology_identity_sha256"] == topology["identity_sha256"], "baseline source chain mismatch")
    material_pin = spills["material"]
    materials = load_material_field(pinned_path(material_pin, spill_directory, seen, local=True),
        expected_sha256=material_pin["sha256"], expected_identity=material_pin["identity_sha256"])
    rain_saved = pinned_json(config["rainfall_grid"], directory, seen, local=True)
    grid = np.asarray(rain_saved["factor"], dtype=np.float64)
    require(list(grid.shape) == rain_saved["shape"] == list(source["arrays"]["height_m"].shape) and
            rain_saved["source_identity_sha256"] == source["identity_sha256"] and
            np.isfinite(grid).all() and np.all(grid >= 0), "rainfall grid shape/source/values mismatch")
    curves = topology["arrays"]
    bottoms = curves["curve_level_m"][curves["curve_offsets"][:-1]]
    factors = .7 + .6 * (bottoms - bottoms.min()) / max(float(np.ptp(bottoms)), 1.)
    factors /= float(np.average(factors, weights=curves["leaf_area_m2"]))
    lookup = dict(zip(map(int, curves["leaf_ids"]), factors))
    original_grid = np.zeros_like(grid)
    active = hierarchy["arrays"]["valid_mask"] & ~hierarchy["arrays"]["protected_mask"]
    original_grid[active] = [lookup[int(leaf)] for leaf in hierarchy["arrays"]["contribution_owner"][active]]
    array_equal(grid, original_grid, "immutable original-bed rainfall grid")
    records = index["candidates"]
    require([record["candidate_id"] for record in records] == list(CANDIDATES), "four candidate coverage/order mismatch")
    baseline_drainage = audit_drainage(hierarchy)
    baseline_record = records[0]
    require(baseline_record == {"candidate_id": "baseline", "drainage": baseline_drainage,
            "events_reused": True, "changed_cells": 0, "source_identity_sha256": source["identity_sha256"]},
            "baseline stored summary mismatch")
    results = [{"candidate_id": "baseline", "status": "pinned-baseline-audit-reused", "drainage": baseline_drainage}]
    scores, all_identities, total_work, solve_count, physical = [], set(), 0, 0, None
    nominated = index["nominated_candidate"]
    require(nominated in CANDIDATES, "invalid nominee")
    all_refined_passed = True
    for record in records[1:]:
        candidate_id = record["candidate_id"]
        pin = record["conditioning"]
        bundle = load_conditioning(pinned_path(pin, directory, seen, local=True),
                                   expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        check_flags(bundle["metadata"])
        geometry = audit_conditioning(bundle, candidate_id, source, hierarchy, materials, requests)
        require(record["geometry_metadata"] == bundle["metadata"] and record["changed_cells"] == geometry["changed_cells"],
                "stored conditioning summary mismatch")
        result = {"candidate_id": candidate_id, "geometry": geometry, "cases": []}
        if not geometry["changed_cells"]:
            require(record["status"] == "unchanged_no_solve" and not record["cases"] and
                    record["drainage"] == baseline_drainage and not {"source", "hierarchy", "topology"}.intersection(record),
                    "unchanged candidate contains new solves or false drainage")
            result.update(status="unchanged-no-solve", drainage=baseline_drainage)
            results.append(result)
            continue
        require(record["status"] == "same_bed_events_saved", "changed candidate lacks same-bed event status")
        pin = record["source"]
        derived = load_td_source_bundle(pinned_path(pin, directory, seen, local=True),
                                       expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        array_equal(derived["arrays"]["height_m"], bundle["arrays"]["height_m"], "source bed equals conditioning")
        require(derived["metadata"] == source["metadata"] and derived["identity_sha256"] != source["identity_sha256"],
                "derived source grid/provenance or identity mismatch")
        for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
            array_equal(derived["arrays"][name], source["arrays"][name], "derived source mask " + name)
        pin = record["hierarchy"]
        derived_hierarchy = load_basin_hierarchy(pinned_path(pin, directory, seen, local=True),
            expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        require(derived_hierarchy["metadata"]["source_identity_sha256"] == derived["identity_sha256"] and
                derived_hierarchy["metadata"]["source_metadata"] == derived["metadata"], "new hierarchy source identity mismatch")
        for name, array in derived["arrays"].items():
            array_equal(derived_hierarchy["arrays"][name], array, "new hierarchy bed/mask " + name)
        pin = record["topology"]
        derived_topology = load_overflow_topology(pinned_path(pin, directory, seen, local=True),
            expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        check_flags(derived["metadata"])
        check_flags(derived_hierarchy["metadata"])
        check_flags(derived_topology["metadata"])
        audit_topology(derived_hierarchy, derived_topology)
        drainage = audit_drainage(derived_hierarchy)
        require(record["drainage"] == drainage, "stored drainage summary differs from saved hierarchy")
        result["drainage"] = drainage
        if drainage["basin_count"] < baseline_drainage["basin_count"] and drainage["largest_static_catchment_area_m2"] >= baseline_drainage["largest_static_catchment_area_m2"]:
            scores.append((-drainage["largest_static_catchment_area_m2"], drainage["basin_count"], geometry["absolute_delta_sum_m"], candidate_id))
        require([case["name"] for case in record["cases"]] == list(CASES), "candidate ordinary/strong coverage mismatch")
        factor = aggregate_rain(grid, derived_hierarchy, derived_topology)
        for case in record["cases"]:
            expected_levels = [0, 1] if candidate_id == nominated else [0]
            require([level["level"] for level in case["levels"]] == expected_levels, "candidate actual refinement coverage mismatch")
            events, level_reports = [], []
            for level in case["levels"]:
                pin = level["event"]
                path = pinned_path(pin, directory, seen, local=True)
                require(read_json(path.with_suffix(".json")) == level, "saved event sidecar differs from index summary")
                seen[path.with_suffix(".json")] = file_sha256(path.with_suffix(".json"))
                event = load_runoff_exchange(path, expected_sha256=pin["sha256"],
                                            expected_identity=pin["identity_sha256"], topology=derived_topology)
                check_flags(event["metadata"])
                require(event["identity_sha256"] not in all_identities, "reused event identity in different solves")
                all_identities.add(event["identity_sha256"])
                ledger = audit_event(event, derived_topology, level, case["name"], factor, config["runoff_parameters"])
                parameters = {name: value for name, value in event["metadata"]["parameters"].items() if name != "duration_s"}
                event_physical = (parameters, event["metadata"]["runoff_metadata"]["parameters"])
                if physical is None:
                    physical = event_physical
                require(physical == event_physical, "candidate physical parameters differ")
                total_work += event["metadata"]["work"]["rhs_evaluations"] * (len(factor) + len(derived_topology["faces"]))
                solve_count += 1
                events.append(event)
                level_reports.append({"level": level["level"], "identity_sha256": event["identity_sha256"], "ledger": ledger})
            case_result = {"name": case["name"], "levels": level_reports}
            if len(events) == 2:
                comparison = compare_events(*events)
                case_result["comparison"] = comparison
                all_refined_passed &= comparison["surface_time_refinement_passed"]
            result["cases"].append(case_result)
            del events
        coarse_record = dict(record, cases=[dict(case, levels=case["levels"][:1]) for case in record["cases"]])
        record_path = directory / candidate_id / "record.json"
        require(read_json(record_path) == coarse_record, "candidate saved coarse record differs from arrays/index")
        seen[record_path] = file_sha256(record_path)
        result["status"] = "same-bed-ledger-passed"
        if candidate_id == nominated:
            result["status"] = "surface-refinement-passed" if all_refined_passed else "surface-refinement-failed"
        results.append(result)
    expected_nominee = min(scores)[-1] if scores else "baseline"
    require(nominated == expected_nominee, "stored nominee differs from independent drainage/disturbance score")
    resources = index["resources"]
    for name in ("new_solves", "counted_rhs_work", "peak_rss_bytes"):
        require(type(resources[name]) is int and resources[name] >= 0, "invalid resource count: " + name)
    require(resources["new_solves"] == solve_count <= 8 and resources["counted_rhs_work"] == total_work <= 6_000_000_000 and
            0 < resources["peak_rss_bytes"] <= 1024**3 and resources["rss_limit_bytes"] == 1024**3 and
            resources["rhs_work_limit"] == 6_000_000_000 and resources["monitor_error"] is None,
            "resource summary/1GiB/6e9/eight-solve budget mismatch")
    require(type(resources["elapsed_s"]) in (int, float) and math.isfinite(resources["elapsed_s"]) and resources["elapsed_s"] >= 0,
            "invalid reported elapsed time")
    passed = all_refined_passed
    larger_catchment = bool(scores and -min(scores)[0] > baseline_drainage["largest_static_catchment_area_m2"])
    return {"status": "passed" if passed else "diagnostic_failure", "candidates": results,
            "nominated_candidate": nominated, "recommended_diagnostic_candidate": nominated if passed else "baseline",
            "selected_candidate": "baseline", "resources": resources,
            "independent_counted_rhs_work": total_work, "independent_new_solves": solve_count,
            "baseline_audit_reused": config["baseline_audit"],
            "larger_static_main_catchment": larger_catchment,
            "improvement_scope": "larger static catchment, not a certified trunk" if larger_catchment else "local connectivity only; no larger main catchment or trunk claimed",
            "nomination_scores": [{"candidate_id": score[-1], "largest_static_catchment_area_m2": -score[0],
                                   "basin_count": score[1], "absolute_delta_sum_m": score[2]} for score in sorted(scores)],
            "resource_scope": "work recomputed from saved counters; RSS/time are reported sampling, not independently reconstructed runtime telemetry; monitor starts after conditioning builder and limits are checked after solves"}


def audit(directory, expected_sha256, *, report_name="independent-audit.json"):
    require(isinstance(report_name, str) and Path(report_name).name == report_name and
            "/" not in report_name and "\\" not in report_name and
            report_name.endswith(".json") and len(report_name) > len(".json"),
            "audit report must be a local basename.json filename")
    directory = Path(directory).resolve(strict=True)
    report_path = directory / report_name
    if report_path.exists():
        raise FileExistsError(report_path)
    seen = {Path(__file__).resolve(): file_sha256(Path(__file__)),
            ROOT / "tools/audit_td_runoff_exchange.py": file_sha256(ROOT / "tools/audit_td_runoff_exchange.py")}
    report = {"schema": "td-conditioning-comparison-independent-audit-v1", "index_sha256": expected_sha256,
              "cold_read": True, "solver_advanced": False, "geometry_built": False,
              "scope": "initial generative conditioning, same-bed ledgers and nominee fixed-forcing surface refinement; not product acceptance",
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
              "full_coupled_timestep_refinement_passed": False, "permanent_trunk_ready": False,
              "tailwater_verified": False, "continuous_fine_corridor_ready": False}
    try:
        with ExitStack() as guards:
            for target in FORBIDDEN:
                guards.enter_context(patch(target, side_effect=AssertionError("cold audit forbids solving/building: " + target)))
            report.update(audit_saved(directory, expected_sha256, seen))
            for path, expected in seen.items():
                require(file_sha256(path) == expected, "input changed during cold audit: " + str(path))
    except (ValueError, KeyError, TypeError, IndexError, OSError, AssertionError) as error:
        report.update(status="diagnostic_failure", recommended_diagnostic_candidate="baseline",
                      selected_candidate="baseline", failure_type=type(error).__name__, failure_reason=str(error))
    report["audit_code_sha256"] = file_sha256(Path(__file__))
    report["water_audit_code_sha256"] = seen[ROOT / "tools/audit_td_runoff_exchange.py"]
    report["verified_file_count"] = len(seen)
    report["recommendation_semantics"] = "review recommendation only; original selected candidate remains baseline; no publication or natural certification"
    publish_bytes(report_path, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--report-name", default="independent-audit.json")
    arguments = parser.parse_args()
    result = audit(arguments.directory, arguments.index_sha256, report_name=arguments.report_name)
    print(json.dumps({name: result.get(name) for name in ("status", "recommended_diagnostic_candidate", "failure_reason")}, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
