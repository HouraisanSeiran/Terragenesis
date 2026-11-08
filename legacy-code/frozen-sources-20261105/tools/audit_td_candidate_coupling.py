"""Independently inspect pinned candidate geometry, rebuilt graph and rain recoupling."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_breach, audit_hierarchy, audit_morphology, audit_storage, near, read_saved


def read_record(record):
    arrays, metadata = read_saved(record["path"], record["expected_sha256"])
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if metadata.get("format_version") == 1:
        digest = hashlib.sha256(canonical(metadata).encode("utf-8"))
        for name, values in sorted(arrays.items()):
            digest.update(name.encode("utf-8"))
            digest.update(values.dtype.str.encode("ascii"))
            digest.update(canonical(list(values.shape)).encode("ascii"))
            digest.update(np.ascontiguousarray(values).tobytes())
        actual_identity = digest.hexdigest()
    else:
        array_digests = {}
        for name, values in sorted(arrays.items()):
            digest = hashlib.sha256()
            digest.update(str(values.shape).encode("ascii"))
            digest.update(values.dtype.str.encode("ascii"))
            digest.update(values.tobytes(order="C"))
            array_digests[name] = digest.hexdigest()
        actual_identity = hashlib.sha256(canonical({"metadata": metadata, "arrays": array_digests}).encode("utf-8")).hexdigest()
    if actual_identity != record["expected_identity"]:
        raise ValueError("independent candidate input identity mismatch")
    return arrays, metadata


def audit_candidates(index_path, index_sha256, baseline_records, output):
    index_path = Path(index_path).resolve(strict=True)
    if file_sha256(index_path) != index_sha256:
        raise ValueError("external candidate index pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    source, source_metadata = read_record(baseline_records["source"])
    topology, topology_metadata = read_record(baseline_records["hierarchy"])
    material, material_metadata = read_record(baseline_records["material"])
    ordinary, ordinary_metadata = read_record(baseline_records["ordinary"])
    actual_volume = ordinary["routed_volume_m3"].copy()
    actual_duration = ordinary["wet_duration_s"].copy()
    actual_forward = ordinary["face_forward_m3"].copy()
    actual_reverse = ordinary["face_reverse_m3"].copy()
    actual_forward_duration = ordinary["active_forward_s"].copy()
    actual_reverse_duration = ordinary["active_reverse_s"].copy()
    del ordinary
    candidate_ids = [record["candidate_id"] for record in index["candidates"]]
    if len(candidate_ids) != len(set(candidate_ids)) or candidate_ids.count("baseline") != 1:
        raise ValueError("candidate IDs are not unique with one baseline")
    if index["selected_candidate_id"] not in candidate_ids:
        raise ValueError("selected candidate does not exist")
    original = source["height_m"]
    spacing = source_metadata["spacing_m"]
    results = []
    for record in index["candidates"]:
        candidate_id = record["candidate_id"]
        if candidate_id == "baseline":
            for role in ("source", "hierarchy", "ordinary", "strong"):
                if record[role + "_identity_sha256"] != baseline_records[role]["expected_identity"]:
                    raise ValueError("candidate baseline external identity mismatch")
            continue
        for role in ("morphology", "source", "hierarchy", "ordinary", "strong"):
            if role in record:
                path = Path(record[role]["path"]).resolve(strict=True)
                if not path.is_relative_to(index_path.parent):
                    raise ValueError("candidate artifact escapes fixed result directory")
        geometry, geometry_metadata = read_record(record["morphology"])
        np.testing.assert_array_equal(geometry["original_height_m"], original)
        np.testing.assert_array_equal(geometry["valid_mask"], source["valid_mask"])
        np.testing.assert_array_equal(geometry["protected_mask"], source["protected_mask"])
        if geometry_metadata["material_identity_sha256"] != baseline_records["material"]["expected_identity"]:
            raise ValueError("candidate material identity mismatch")
        saddle = candidate_id.startswith("saddle_breach")
        sediment = audit_breach(geometry, geometry_metadata) if saddle else audit_morphology(geometry, geometry_metadata)
        if saddle:
            path = geometry["path_cell_ids"]
            evidence = geometry_metadata["hydro_face_evidence"]
            first, second = evidence["face_cell_ids"]
            faces = topology["face_cells"]
            matched = np.flatnonzero(((faces[:, 0] == first) & (faces[:, 1] == second)) | ((faces[:, 0] == second) & (faces[:, 1] == first)))
            if len(matched) != 1:
                raise ValueError("saddle face does not exist in original D4 graph")
            face_id = int(matched[0])
            forward = faces[face_id, 0] == first
            volume = (actual_forward if forward else actual_reverse)[face_id]
            duration = (actual_forward_duration if forward else actual_reverse_duration)[face_id]
            near(geometry["path_routed_volume_m3"], volume, absolute=0, relative=0)
            near(geometry["path_wet_duration_s"], duration, absolute=0, relative=0)
            if evidence["hydro_identity_sha256"] != baseline_records["ordinary"]["expected_identity"]:
                raise ValueError("saddle evidence does not bind the actual ordinary water")
            anchor = geometry_metadata["downstream_anchor_evidence"]
            leaf = int(topology["contribution_owner"].ravel()[first])
            if leaf != anchor["source_basin_id"] or topology["node_open_boundary"][leaf] or topology["node_unknown_contact"][leaf]:
                raise ValueError("saddle source leaf is not the declared closed basin")
            if topology["face_merge_node"][face_id] != topology["node_parent"][leaf]:
                raise ValueError("saddle is not source leaf parent merge")
            near(topology["face_level_m"][face_id], topology["node_upper_m"][leaf], absolute=1e-8, relative=0)
            tail = np.asarray(anchor["tail_cell_ids"])
            np.testing.assert_array_equal(topology["receiver"][tail[:-1]], tail[1:])
            if tail[0] != path[-1] or topology["receiver"][tail[-1]] != -1 or int(topology["contribution_owner"].ravel()[tail[-1]]) != anchor["destination_basin_id"]:
                raise ValueError("saddle anchor tail does not match complete original receiver")
            sediment["external_face_evidence_independently_verified"] = True
        else:
            np.testing.assert_array_equal(geometry["receiver"], topology["receiver"])
            expected_volume = actual_volume.reshape(geometry["routed_volume_m3"].shape)
            expected_duration = actual_duration.reshape(geometry["wet_duration_s"].shape)
            near(geometry["routed_volume_m3"], expected_volume, absolute=0, relative=0)
            near(geometry["wet_duration_s"], expected_duration, absolute=0, relative=0)
            slope = np.zeros(original.size)
            routed_cells = np.flatnonzero(topology["receiver"] >= 0)
            slope[routed_cells] = (original.ravel()[routed_cells] - original.ravel()[topology["receiver"][routed_cells]]) / spacing
            potential = (.15 * material["erodibility"] * material["weak_path_preference"]
                         * np.log1p(actual_volume.reshape(original.shape) / 1000)
                         * (-np.expm1(-actual_duration.reshape(original.shape) / 3600)) * np.sqrt(slope.reshape(original.shape)))
            expected = np.minimum(potential, material["erodible_thickness_m"])
            expected[~source["valid_mask"] | source["protected_mask"]] = 0
            near(geometry["erosion_depth_m"], expected, absolute=1e-12, relative=1e-12)
        derived = geometry["height_m"].copy()
        changed = int(np.count_nonzero(derived != original))
        if changed != record["changed_cells"]:
            raise ValueError("candidate changed cell summary mismatch")
        result = {"candidate_id": candidate_id, "changed_cells": changed, "sediment": sediment,
                  "material_ledger_source_matches": True, "geometry_driver_is_actual_saved_water": True}
        del geometry
        if not changed:
            if any(role in record for role in ("source", "hierarchy", "ordinary", "strong")):
                raise ValueError("unchanged rejected geometry has unnecessary new solved state")
            results.append(result)
            continue
        candidate_source, candidate_source_metadata = read_record(record["source"])
        np.testing.assert_array_equal(candidate_source["height_m"], derived)
        for field in ("valid_mask", "protected_mask", "open_boundary_mask"):
            np.testing.assert_array_equal(candidate_source[field], source[field])
        for field in ("origin_m_xz", "spacing_m", "source_sha256"):
            if candidate_source_metadata[field] != source_metadata[field]:
                raise ValueError("candidate changed source coordinate or provenance")
        candidate_topology, candidate_topology_metadata = read_record(record["hierarchy"])
        np.testing.assert_array_equal(candidate_topology["height_m"], derived)
        if candidate_topology_metadata["source_identity_sha256"] != record["source"]["expected_identity"]:
            raise ValueError("candidate rebuilt graph not bound to new geometry")
        result["topology"] = audit_hierarchy(candidate_topology, candidate_topology_metadata)
        result["water"] = {}
        for scenario in ("ordinary", "strong"):
            water, water_metadata = read_record(record[scenario])
            baseline, baseline_metadata = read_record(baseline_records[scenario])
            for field in ("rain_mm_h",):
                np.testing.assert_array_equal(water[field], baseline[field])
            for field in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                np.testing.assert_array_equal(water[field][0], baseline[field][0])
            for field in ("runoff_parameters", "dt_s", "substep_s", "algorithm"):
                if water_metadata[field] != baseline_metadata[field]:
                    raise ValueError("candidate changed forcing, initial soil or numerical algorithm")
            del baseline
            if water_metadata["hierarchy_identity_sha256"] != record["hierarchy"]["expected_identity"]:
                raise ValueError("candidate water uses stale topology")
            np.testing.assert_array_equal(water["height_m"], derived)
            for field in ("face_cells", "receiver", "boundary_cells"):
                np.testing.assert_array_equal(water[field], candidate_topology[field])
            result["water"][scenario] = audit_storage(water, water_metadata)
            del water
        result["candidate_specific_sensitivity_verified"] = record.get("candidate_sensitivity_verified", False)
        result["selected_in_saved_index"] = index["selected_candidate_id"] == candidate_id
        results.append(result)
        del candidate_source, candidate_topology
    selected = [record for record in index["candidates"] if record.get("selected")]
    if len(selected) != 1 or selected[0]["candidate_id"] != index["selected_candidate_id"]:
        raise ValueError("selection marker is inconsistent")
    if selected[0]["candidate_id"] != "baseline" and not (selected[0].get("gates_passed") and selected[0].get("candidate_sensitivity_verified") and selected[0].get("improved")):
        raise ValueError("selected derived candidate lacks its own gates")
    report = {"schema": "td-candidate-independent-coupling-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "index_path": str(index_path), "index_sha256": index_sha256, "auditor_sha256": file_sha256(__file__),
              "baseline_records": baseline_records, "selected_candidate_id": index["selected_candidate_id"],
              "candidates": results, "natural_outlet_verified": False, "hydraulic_ready": False,
              "scope": "saved geometry, source sediment, D4 topology and two-rain recoupling; sensitivity flags require separately pinned proof"}
    publish_bytes(output, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--baseline-inputs", type=Path, required=True)
    parser.add_argument("--baseline-inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if file_sha256(args.baseline_inputs) != args.baseline_inputs_sha256:
        raise ValueError("external baseline index pin mismatch")
    records = json.loads(args.baseline_inputs.read_text(encoding="utf-8"))["inputs"]
    report = audit_candidates(args.index, args.index_sha256, records, args.output)
    print(json.dumps({"selected": report["selected_candidate_id"], "candidates": len(report["candidates"])}))


if __name__ == "__main__":
    main()
