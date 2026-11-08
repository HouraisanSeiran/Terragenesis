"""Independent original-bed water/material reductions for accepted candidates."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_basin_generation import near


def audit_fields(arrays, metadata, source, topology, material, material_metadata, checkpoint, spacing):
    bed = source["height_m"]
    valid = source["valid_mask"]
    if not valid.all() or source["protected_mask"].any():
        raise ValueError("independent candidate audit requires known unprotected coverage")
    for name in ("original_height_m", "valid_mask", "protected_mask"):
        expected = bed if name == "original_height_m" else source[name]
        np.testing.assert_array_equal(arrays[name], expected)
    receiver = topology["receiver"]
    np.testing.assert_array_equal(arrays["receiver"], receiver)
    for name, cumulative in (("routed_volume_m3", "cumulative_routed_volume_m3"),
                             ("wet_duration_s", "cumulative_wet_duration_s")):
        np.testing.assert_array_equal(arrays[name].ravel(), checkpoint[cumulative])
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    if np.any(targets >= bed.size) or np.any(receiver < -1):
        raise ValueError("invalid independent receiver")
    rows, columns = np.divmod(donors, bed.shape[1])
    target_rows, target_columns = np.divmod(targets, bed.shape[1])
    if np.any(abs(rows - target_rows) + abs(columns - target_columns) != 1):
        raise ValueError("non-D4 independent receiver")
    slope = np.zeros(bed.size)
    slope[donors] = (bed.ravel()[donors] - bed.ravel()[targets]) / spacing
    if np.any(slope < 0):
        raise ValueError("original-bed uphill receiver")
    parameters = metadata["parameters"]
    expected_config = dict(erosion_scale_m=.15, reference_volume_m3=1000., reference_duration_s=3600.,
        transport_ratio=.002, max_deposit_depth_m=4., max_work_cells=1048576,
        engineering_open_boundary_cell_ids=np.flatnonzero(source["open_boundary_mask"].ravel() & (receiver == -1)).tolist())
    if parameters != expected_config or metadata["material_parameters"] != material_metadata["parameters"]:
        raise ValueError("independent frozen morphology configuration differs")
    volume = checkpoint["cumulative_routed_volume_m3"].reshape(bed.shape)
    duration = checkpoint["cumulative_wet_duration_s"].reshape(bed.shape)
    wet = (volume > 0) & (duration > 0)
    potential = .15 * material["erodibility"] * material["weak_path_preference"]
    potential *= np.log1p(volume / 1000.) * (-np.expm1(-duration / 3600.)) * np.sqrt(slope.reshape(bed.shape))
    erosion = np.where(wet, np.minimum(potential, material["erodible_thickness_m"]), 0.)
    area = spacing ** 2
    config = material_metadata["parameters"]
    source_geometry = erosion * area
    source_solid = source_geometry * (1 - config["source_porosity"])
    incoming = np.zeros(bed.size)
    transported = np.zeros(bed.size)
    deposited = np.zeros(bed.size)
    stored = np.zeros(bed.size)
    exported = np.zeros(bed.size)
    degree = np.bincount(targets, minlength=bed.size)
    queue = deque(np.flatnonzero(degree == 0).tolist())
    capacity = np.where(wet, .002 * volume, 0.).ravel()
    limit = 4. * area * (1 - config["deposit_porosity"])
    opened = source["open_boundary_mask"].ravel() & (receiver == -1)
    kind = metadata["candidate_kind"]
    if kind not in ("breach", "deposition"):
        raise ValueError("unknown independent morphology kind")
    visited = 0
    while queue:
        donor = queue.popleft()
        visited += 1
        available = incoming[donor] + source_solid.ravel()[donor]
        movable = min(available, capacity[donor])
        target = receiver[donor]
        if target >= 0:
            transported[donor] = movable
            incoming[target] += movable
            degree[target] -= 1
            if degree[target] == 0:
                queue.append(int(target))
        elif opened[donor]:
            exported[donor] = movable
        else:
            movable = 0.
        remainder = max(0., available - movable)
        if kind == "deposition" and incoming[donor] > 0:
            deposited[donor] = min(remainder, incoming[donor], limit)
        stored[donor] = remainder - deposited[donor]
    if visited != bed.size:
        raise ValueError("independent receiver cycle")
    deposit_geometry = deposited.reshape(bed.shape) / (1 - config["deposit_porosity"])
    deposit_depth = deposit_geometry / area
    expected = {"erosion_depth_m": erosion, "remaining_erodible_thickness_m": material["erodible_thickness_m"] - erosion,
        "source_geometry_m3": source_geometry, "source_solid_m3": source_solid,
        "source_mass_kg": source_solid * config["solid_density_kg_m3"],
        "incoming_solid_m3": incoming.reshape(bed.shape), "transported_solid_m3": transported.reshape(bed.shape),
        "deposited_solid_m3": deposited.reshape(bed.shape), "stored_solid_m3": stored.reshape(bed.shape),
        "exported_solid_m3": exported.reshape(bed.shape), "deposit_geometry_m3": deposit_geometry,
        "deposit_depth_m": deposit_depth, "height_delta_m": deposit_depth - erosion,
        "height_m": bed + deposit_depth - erosion}
    np.testing.assert_array_equal(arrays["engineering_open_boundary_mask"], opened.reshape(bed.shape))
    expected["cell_residual_m3"] = source_solid + incoming.reshape(bed.shape) - transported.reshape(bed.shape) - deposited.reshape(bed.shape) - stored.reshape(bed.shape) - exported.reshape(bed.shape)
    differences = {}
    for name, values in expected.items():
        near(arrays[name], values, absolute=1e-9, relative=1e-12)
        differences[name] = float(abs(arrays[name] - values).max(initial=0))
    ledger = {name: math.fsum(expected[name].ravel().tolist()) for name in metadata["ledger"] if name != "solid_residual_m3"}
    residual = math.fsum([ledger["source_solid_m3"], -ledger["deposited_solid_m3"], -ledger["stored_solid_m3"], -ledger["exported_solid_m3"]])
    near(metadata["ledger"]["solid_residual_m3"], residual)
    for name, value in ledger.items():
        near(metadata["ledger"][name], value)
    if abs(residual) > 1e-6 + ledger["source_solid_m3"] * 1e-10:
        raise ValueError("independent global solid budget failed")
    return dict(kind=kind, ledger=ledger, independent_solid_residual_m3=residual,
        changed_cells=int(np.count_nonzero(expected["height_delta_m"])),
        eroded_cells=int(np.count_nonzero(erosion)), deposited_cells=int(np.count_nonzero(deposit_depth)),
        max_erosion_m=float(erosion.max(initial=0)), max_deposit_m=float(deposit_depth.max(initial=0)),
        closed_terminal_count=int(np.count_nonzero((receiver == -1) & ~opened)),
        max_field_differences=differences, frozen_sediment_allocation_verified=True)


def audit(path, expected_sha256, acceptance_path, acceptance_sha256):
    path, acceptance_path = Path(path).resolve(strict=True), Path(acceptance_path).resolve(strict=True)
    if file_sha256(path) != expected_sha256 or file_sha256(acceptance_path) != acceptance_sha256:
        raise ValueError("independent external manifest pin mismatch")
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    options = manifest["inputs"]
    if (acceptance.get("schema") != "td-independent-final-continuation-acceptance-v1" or
            acceptance.get("all_saved_numerical_gates_passed") is not True or
            acceptance.get("original_inputs_and_frozen_code_unchanged") is not True or
            options["acceptance_arguments"] != acceptance["acceptance_arguments"] or
            options["input_index"] != acceptance["input_index"]):
        raise ValueError("candidate does not bind fully accepted continuation")
    for record in acceptance["numerical_reports"].values():
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("independent numerical audit changed")
    from terrain_pipeline.td_accepted_water_morphology import load_accepted_water_morphology
    load_accepted_water_morphology(path, expected_sha256=expected_sha256, expected_identity=manifest["identity_sha256"], **options)
    source, source_metadata = read_record(options["source_record"])
    topology, unused = read_record(options["acceptance_arguments"]["hierarchy_record"])
    material, material_metadata = read_record(options["material_record"])
    checkpoint, unused = read_record(manifest["ordinary_fine_final_checkpoint"])
    results = {}
    for candidate_id in ("valley_incision", "source_deposition"):
        record = manifest["candidates"][candidate_id]
        arrays, metadata = read_record(record["morphology"])
        results[candidate_id] = audit_fields(arrays, metadata, source, topology, material, material_metadata,
            checkpoint, source_metadata["spacing_m"])
        derived, unused = read_record(record["source"])
        np.testing.assert_array_equal(derived["height_m"], arrays["height_m"])
    memory = psutil.Process().memory_info()
    resources = dict(peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)),
                     peak_private_bytes=getattr(memory, "peak_pagefile", None))
    if resources["peak_private_bytes"] is None or max(resources.values()) > 1073741824:
        raise MemoryError("independent candidate audit requires bounded RSS/private evidence")
    if file_sha256(path) != expected_sha256 or file_sha256(acceptance_path) != acceptance_sha256:
        raise ValueError("candidate audit input changed during read")
    return dict(schema="td-independent-accepted-morphology-v1", input_manifest=str(path),
        input_sha256=expected_sha256, independent_continuation=str(acceptance_path),
        independent_continuation_sha256=acceptance_sha256, scope=options["scope"], candidates=results,
        resources=resources, solver_advanced=False, recoupling_required=True, selection="baseline pending",
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
        auditor_sha256=file_sha256(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--acceptance-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.manifest, arguments.expected_sha256, arguments.acceptance, arguments.acceptance_sha256)
    output = ROOT / "verification/td-basin-generation" / ("independent-accepted-morphology-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(output=str(output), candidates=result["candidates"])))
