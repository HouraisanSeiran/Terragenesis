"""Independent geometry candidates, rebuilt topology and conservative fallback gates."""

import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_source import make_td_source, save_td_source, validate_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy, validate_basin_hierarchy
from terrain_pipeline.td_basin_storage import simulate_basin_storage, save_basin_storage, validate_basin_storage
from terrain_pipeline.td_material_field import _validate_cold_material
from terrain_pipeline.td_basin_morphology import generate_morphology, save_morphology
from terrain_pipeline.td_basin_breach import generate_saddle_breach, saddle_path_face_identity, save_saddle_breach


def validate_candidate_inputs(source, hierarchy, materials, ordinary, strong):
    validate_td_source(source)
    validate_basin_hierarchy(hierarchy)
    _validate_cold_material(materials)
    for hydro in (ordinary, strong):
        validate_basin_storage(hydro)
        if hydro["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
            raise ValueError("hydrology/topology identity chain mismatch")
        if not np.array_equal(hydro["arrays"]["height_m"], source["arrays"]["height_m"]):
            raise ValueError("hydrology original bed mismatch")
        if not np.array_equal(hydro["arrays"]["receiver"], hierarchy["arrays"]["receiver"]):
            raise ValueError("hydrology receiver mismatch")
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]:
        raise ValueError("source/topology chain mismatch")
    if (materials["metadata"]["shape"] != list(source["arrays"]["height_m"].shape) or
            materials["metadata"]["origin_m_xz"] != source["metadata"]["origin_m_xz"] or
            materials["metadata"]["spacing_m"] != source["metadata"]["spacing_m"] or
            not np.array_equal(materials["arrays"]["protected_mask"], source["arrays"]["protected_mask"])):
        raise ValueError("material source grid/protection mismatch")
    for hydro in (ordinary, strong):
        for key in ("valid_mask", "face_cells", "boundary_cells"):
            if not np.array_equal(hydro["arrays"][key], hierarchy["arrays"][key]):
                raise ValueError("hydro coverage/face/boundary mismatch")
    if ordinary["metadata"]["parameters"] != strong["metadata"]["parameters"]:
        raise ValueError("ordinary/strong numerical parameter mismatch")
    return True


def _tail(receiver, start, limit=64):
    cells = [int(start)]
    while receiver[cells[-1]] >= 0:
        if len(cells) >= limit:
            return None
        next_cell = int(receiver[cells[-1]])
        if next_cell in cells:
            return None
        cells.append(next_cell)
    return cells


def find_saddle_paths(source, hierarchy, ordinary):
    topology, hydro = hierarchy["arrays"], ordinary["arrays"]
    bed = topology["height_m"].ravel()
    contribution = topology["contribution_owner"].ravel()
    parent = topology["node_parent"]
    child_count = np.bincount(parent[parent >= 0], minlength=len(parent))
    receiver = topology["receiver"]
    paths, rejected = [], []
    for face_index, face in enumerate(topology["face_cells"]):
        for outward, volume_key, duration_key in ((face, "face_forward_m3", "active_forward_s"),
                                                 (face[::-1], "face_reverse_m3", "active_reverse_s")):
            first, second = map(int, outward)
            leaf = int(contribution[first])
            if (leaf < 0 or child_count[leaf] != 0 or parent[leaf] < 0 or topology["node_open_boundary"][leaf] or
                    topology["node_unknown_contact"][leaf] or contribution[second] == leaf or
                    topology["face_merge_node"][face_index] != parent[leaf] or
                    abs(topology["face_level_m"][face_index] - topology["node_upper_m"][leaf]) > 1e-8 or
                    hydro[volume_key][face_index] <= 0 or hydro[duration_key][face_index] <= 0):
                continue
            prefix = _tail(receiver, first)
            suffix = _tail(receiver, second)
            reason = None
            if prefix is None or suffix is None:
                reason = "receiver_tail_exceeds64"
            else:
                prefix = prefix[::-1]
                lower = [index for index, cell in enumerate(suffix) if bed[cell] < bed[prefix[0]]]
                if not lower:
                    reason = "no_lower_downstream_anchor"
                else:
                    anchor_index = lower[0]
                    path = prefix + suffix[:anchor_index + 1]
                    tail = suffix[anchor_index:]
                    target = np.linspace(bed[path[0]], bed[path[-1]], len(path))
                    if len(path) > 64 or len(set(path)) != len(path):
                        reason = "path_exceeds64_or_repeated"
                    elif np.any(target > bed[path] + 1e-8):
                        reason = "straight_target_requires_fill"
                    elif bed[tail[-1]] >= bed[path[0]] or contribution[tail[-1]] == leaf:
                        reason = "tail_not_different_lower_leaf"
                    elif np.any(source["arrays"]["protected_mask"].ravel()[path + tail]):
                        reason = "protected_path_or_tail"
                    else:
                        duration = float(hydro[duration_key][face_index])
                        substep = ordinary["metadata"]["substep_s"]
                        if ordinary["metadata"]["algorithm"] == "D4-analytic-face-Strang-splitting-v2":
                            substep /= 2
                        steps = int(round(duration / substep))
                        if abs(steps * substep - duration) > 1e-8:
                            raise ValueError("face activity not integral substeps")
                        paths.append({"leaf": leaf, "face_index": face_index, "face_cell_ids": [first, second],
                            "path": path, "target": target.tolist(), "tail": tail,
                            "destination_leaf": int(contribution[tail[-1]]),
                            "volume_m3": float(hydro[volume_key][face_index]), "duration_s": duration,
                            "positive_outflow_steps": steps, "substep_s": substep,
                            "sill_m": float(topology["face_level_m"][face_index]),
                            "required_cut_m3": float(np.maximum(0, bed[path] - target).sum() * source["metadata"]["spacing_m"] ** 2)})
            if reason:
                rejected.append({"leaf": leaf, "face_index": face_index, "face_cell_ids": [first, second], "reason": reason})
    return paths, rejected


def generate_candidate_geometries(source, hierarchy, materials, ordinary, strong):
    validate_candidate_inputs(source, hierarchy, materials, ordinary, strong)
    topology = hierarchy["arrays"]
    volume, duration = ordinary["arrays"]["routed_volume_m3"], ordinary["arrays"]["wet_duration_s"]
    opened = np.flatnonzero(source["arrays"]["open_boundary_mask"].ravel() & (topology["receiver"] < 0)).tolist()
    bundles = {}
    for candidate_id, kind in (("valley_incision", "breach"), ("source_deposition", "deposition")):
        bundles[candidate_id] = generate_morphology(source["arrays"]["height_m"], source["arrays"]["valid_mask"],
            topology["receiver"], volume, duration, spacing_m=source["metadata"]["spacing_m"], materials=materials,
            parameters={"engineering_open_boundary_cell_ids": opened}, candidate_kind=kind)
    paths, rejected = find_saddle_paths(source, hierarchy, ordinary)
    for path in paths:
        material_cost = materials["arrays"]["erodibility"].ravel()[path["path"]]
        path["material_cost"] = float(np.maximum(0, source["arrays"]["height_m"].ravel()[path["path"]] - path["target"]).dot(1 / material_cost))
    paths.sort(key=lambda path: (path["sill_m"], path["required_cut_m3"], path["material_cost"], path["face_index"], path["face_cell_ids"]))
    selected = []
    seen_leaves = set()
    for path in paths:
        if path["leaf"] not in seen_leaves and len(selected) < 8:
            selected.append(path)
            seen_leaves.add(path["leaf"])
    for index, path in enumerate(selected):
        path_identity = saddle_path_face_identity(source["arrays"]["height_m"], path["path"],
            source_identity_sha256=source["identity_sha256"], topology_identity_sha256=hierarchy["identity_sha256"])
        evidence = {"hydro_identity_sha256": ordinary["identity_sha256"], "face_cell_ids": path["face_cell_ids"],
            "outward_volume_m3": path["volume_m3"], "positive_outflow_steps": path["positive_outflow_steps"], "dt_s": path["substep_s"]}
        anchor = {"topology_identity_sha256": hierarchy["identity_sha256"], "source_basin_id": path["leaf"],
            "destination_basin_id": path["destination_leaf"], "tail_cell_ids": path["tail"],
            "engineering_open_boundary": bool(source["arrays"]["open_boundary_mask"].ravel()[path["tail"][-1]])}
        bundles["saddle_breach_" + str(index)] = generate_saddle_breach(source["arrays"]["height_m"], source["arrays"]["valid_mask"],
            spacing_m=source["metadata"]["spacing_m"], materials=materials, path_cell_ids=path["path"], target_bed_m=path["target"],
            path_face_identity=path_identity, source_identity_sha256=source["identity_sha256"], topology_identity_sha256=hierarchy["identity_sha256"],
            hydro_identity_sha256=ordinary["identity_sha256"], routed_volume_m3=np.full(len(path["path"]), path["volume_m3"]),
            wet_duration_s=np.full(len(path["path"]), path["duration_s"]), hydro_face_evidence=evidence, downstream_anchor_evidence=anchor)
    return bundles, {"eligible_paths": len(paths), "selected_paths": selected, "path_rejections": rejected,
        "external_face_receiver_evidence_checked": True, "all_saddle_parameters_default": True}


def select_candidate(records, *, numerical_sensitivity_passed):
    eligible = []
    for record in records:
        if record["candidate_id"] == "baseline":
            continue
        if numerical_sensitivity_passed and record.get("gates_passed", False) and record.get("improved", False):
            eligible.append(record)
    if not eligible:
        return "baseline"
    return min(eligible, key=lambda record: (record["disturbance_m3"], record["max_abs_delta_m"], record["candidate_id"]))["candidate_id"]


def run_candidate_coupling(source, hierarchy, materials, ordinary, strong, output, *, numerical_sensitivity_passed=False,
                           refine_candidates=False):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    bundles, path_report = generate_candidate_geometries(source, hierarchy, materials, ordinary, strong)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".candidate-", dir=output.parent))
    records = [{"candidate_id": "baseline", "gates_passed": True, "selected": False,
        "source_identity_sha256": source["identity_sha256"], "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "ordinary_identity_sha256": ordinary["identity_sha256"], "strong_identity_sha256": strong["identity_sha256"],
        "hydraulic_ready": False, "publishable": False, "natural_outlet_verified": False}]

    def artifact(path, bundle):
        return {"path": str(output / path.relative_to(temporary)), "expected_sha256": file_sha256(path),
                "expected_identity": bundle["identity_sha256"]}

    try:
        for candidate_id, morphology in bundles.items():
            print("candidate " + candidate_id, flush=True)
            directory = temporary / candidate_id
            directory.mkdir()
            morphology_path = directory / "morphology.npz"
            saddle = candidate_id.startswith("saddle_breach")
            if saddle:
                save_saddle_breach(morphology, morphology_path)
            else:
                save_morphology(morphology, morphology_path)
            delta = morphology["arrays"]["height_m"] - source["arrays"]["height_m"]
            ledger = morphology["metadata"]["ledger"]
            record = {"candidate_id": candidate_id, "morphology": artifact(morphology_path, morphology),
                "changed_cells": int((delta != 0).sum()), "max_abs_delta_m": float(abs(delta).max()),
                "disturbance_m3": ledger["source_geometry_m3"] + ledger["deposit_geometry_m3"], "material_ledger": ledger,
                "numerical_sensitivity_passed": numerical_sensitivity_passed, "gates_passed": False, "improved": False,
                "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False,
                "candidate_sensitivity_verified": False,
                "rejection_reasons": ["candidate_specific_transient_sensitivity_not_verified"] if numerical_sensitivity_passed else ["baseline_strong_transient_not_converged"],
                "external_evidence_verified": saddle}
            if saddle and morphology["metadata"]["status"] == "rejected":
                record["rejection_reasons"].extend(morphology["metadata"]["rejection_reasons"])
            if not record["changed_cells"]:
                record["rejection_reasons"].append("unchanged_geometry")
                records.append(record)
                continue
            candidate_source = make_td_source(morphology["arrays"]["height_m"], spacing_m=source["metadata"]["spacing_m"],
                origin_m_xz=source["metadata"]["origin_m_xz"], valid_mask=source["arrays"]["valid_mask"],
                protected_mask=source["arrays"]["protected_mask"], open_boundary_mask=source["arrays"]["open_boundary_mask"],
                source_sha256=source["metadata"]["source_sha256"])
            candidate_topology = build_basin_hierarchy(candidate_source)
            save_td_source(directory / "source.npz", candidate_source)
            save_basin_hierarchy(directory / "hierarchy.npz", candidate_topology)
            record["source"] = artifact(directory / "source.npz", candidate_source)
            record["hierarchy"] = artifact(directory / "hierarchy.npz", candidate_topology)
            record["rebuilt_nodes"] = len(candidate_topology["arrays"]["node_parent"])
            for scenario, baseline in (("ordinary", ordinary), ("strong", strong)):
                solver = simulate_basin_storage
                if baseline["metadata"]["algorithm"] == "D4-analytic-face-Strang-splitting-v2":
                    from terrain_pipeline.td_basin_storage_implicit import simulate_basin_storage as solver
                if refine_candidates:
                    from terrain_pipeline.td_basin_storage_refinement import simulate_basin_storage as solver
                parameters = RunoffParameters(**baseline["metadata"]["runoff_parameters"])
                rain = baseline["arrays"]["rain_mm_h"].reshape((-1,) + source["arrays"]["height_m"].shape)
                initial = baseline["arrays"]["depth_m"][0].reshape(source["arrays"]["height_m"].shape)
                water = solver(candidate_topology, rain, dt_s=baseline["metadata"]["dt_s"],
                    initial_depth_m=initial, runoff_parameters=parameters, parameters=baseline["metadata"]["parameters"])
                path = directory / (scenario + ".npz")
                save_basin_storage(path, water)
                record[scenario] = artifact(path, water)
                area = source["metadata"]["spacing_m"] ** 2
                values, old = water["arrays"], baseline["arrays"]
                differences = {key: float((values[key].sum() - old[key].sum())) for key in (
                    "soil_et_m3", "surface_et_m3", "boundary_outflow_m3")}
                for key in ("soil_mm", "fast_mm", "slow_mm"):
                    differences["final_" + key + "_m3"] = float((values[key][-1].sum() - old[key][-1].sum()) * area / 1000)
                differences["final_surface_m3"] = float((values["depth_m"][-1].sum() - old["depth_m"][-1].sum()) * area)
                differences["max_cell_residual_m3"] = float(abs(values["balance_residual_m3"]).max())
                record[scenario + "_differences"] = differences
                coarse_depth = values["depth_m"].copy() if refine_candidates else None
                coarse_volume = values["routed_volume_m3"].copy() if refine_candidates else None
                del water, values
                if refine_candidates:
                    refined_parameters = dict(baseline["metadata"]["parameters"])
                    refined_parameters["substep_s"] /= 2
                    refined_parameters["max_work_face_steps"] = 6_000_000_000
                    refined = solver(candidate_topology, rain, dt_s=baseline["metadata"]["dt_s"],
                        initial_depth_m=initial, runoff_parameters=parameters, parameters=refined_parameters)
                    refined_path = directory / (scenario + "-refined.npz")
                    save_basin_storage(refined_path, refined)
                    record[scenario + "_refined"] = artifact(refined_path, refined)
                    fine_values = refined["arrays"]
                    head_error = float(abs(coarse_depth - fine_values["depth_m"]).max())
                    volume_error = float(abs(coarse_volume - fine_values["routed_volume_m3"]).sum() / max(1e-12, fine_values["routed_volume_m3"].sum()))
                    record[scenario + "_sensitivity"] = {"scope": "entire candidate domain", "max_depth_difference_m": head_error,
                        "receiver_volume_relative_l1": volume_error, "gate_passed": head_error <= .001 and volume_error <= .01}
                    del refined, fine_values, coarse_depth, coarse_volume
            ordinary_difference = record["ordinary_differences"]
            evaporation_increase = ordinary_difference["soil_et_m3"] + ordinary_difference["surface_et_m3"]
            internal_storage_increase = sum(ordinary_difference["final_" + key + "_m3"] for key in ("soil_mm", "fast_mm", "slow_mm"))
            record["improved"] = (ordinary_difference["final_surface_m3"] < -1e-6 and
                ordinary_difference["boundary_outflow_m3"] > 1e-6 and evaporation_increase <= 1e-6 and internal_storage_increase <= 1e-6)
            record["candidate_sensitivity_verified"] = refine_candidates and all(record[scenario + "_sensitivity"]["gate_passed"] for scenario in ("ordinary", "strong"))
            record["gates_passed"] = numerical_sensitivity_passed and record["candidate_sensitivity_verified"]
            if record["candidate_sensitivity_verified"]:
                record["rejection_reasons"] = [reason for reason in record["rejection_reasons"] if reason != "candidate_specific_transient_sensitivity_not_verified"]
            elif refine_candidates:
                record["rejection_reasons"].append("candidate_full_domain_transient_not_converged")
            if not record["improved"]:
                record["rejection_reasons"].append("no_verified_non_evaporation_connectivity_improvement")
            records.append(record)
        selected = select_candidate(records, numerical_sensitivity_passed=numerical_sensitivity_passed)
        for record in records:
            record["selected"] = record["candidate_id"] == selected
        payload = {"schema": "td-basin-candidate-records-v1", "selected_candidate_id": selected, "candidates": records,
            "saddle_search": path_report, "numerical_sensitivity_passed": numerical_sensitivity_passed,
            "mode": "diagnostic coupling only when numerical sensitivity fails; never automatic terrain adoption",
            "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False}
        publish_bytes(temporary / "records.json", json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
        os.rename(temporary, output)
        return payload
    except BaseException:
        shutil.rmtree(temporary)
        raise
