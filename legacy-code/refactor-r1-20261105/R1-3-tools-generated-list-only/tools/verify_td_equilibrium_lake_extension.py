"""Cold-pinned TD256 six-leaf common-stage lake support verification."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.ndimage import label

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_equilibrium_lake_support import (
    EquilibriumLakeConfig, EquilibriumLakeForcing, load_equilibrium_lakes,
    save_equilibrium_lakes, solve_equilibrium_lakes,
)
from terrain_pipeline.surface_rivers.metric_natural_lakes import load_natural_lakes
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.verify_td_natural_lake_extension import TD_PATH, TD_SHA, TD_ID


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "verification/td-natural-lake-extension/td256-20261008-04/td-domain.npz"
DOMAIN_SHA = "0fc4e741b7cf593d298cc5a60046771d313b8a69ed99b691a746e954e01cfd2c"
DOMAIN_ID = "fbdbdcaec93c56b50d79383e7c32684a81df9ab97500596ba9fd1a37d5662961"
LEAVES = [1, 2, 3, 6, 8, 9]


def _independent_cold(domain, trace, initial, local):
    source, a = domain["arrays"], trace["arrays"]
    bed = source["source_height_m"].ravel()
    owner = source["owner_grid"].ravel()
    support = source["support_cell_ids"]
    faces = source["internal_faces"]
    boundary = source["boundary_faces"]
    n = len(source["seed_cell_ids"])
    cell_area = (domain["metadata"]["terrain_metadata"]["dx_m"] *
                 domain["metadata"]["terrain_metadata"]["dz_m"])
    max_balance = 0.
    max_projection_balance = 0.
    max_weir_error = 0.
    merged_frames = 0
    for step, stage in enumerate(a["trace_owner_stage_m"]):
        volume = np.array([cell_area * np.maximum(stage[i] - bed[owner == i], 0.).sum()
                           for i in range(n)])
        np.testing.assert_allclose(volume, a["trace_owner_volume_m3"][step], rtol=1e-10, atol=1e-6)
        wet = (owner >= 0) & (bed < stage[np.maximum(owner, 0)])
        np.testing.assert_array_equal(wet[support], a["trace_wet_support"][step])
        native, _ = label(wet.reshape(source["owner_grid"].shape),
                          structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        native_seed = native.ravel()[source["seed_cell_ids"]]
        for i in range(n):
            for j in range(i + 1, n):
                wet_link = native_seed[i] > 0 and native_seed[i] == native_seed[j]
                saved_link = a["trace_wet_component"][step, i] == a["trace_wet_component"][step, j]
                if wet_link != saved_link:
                    raise AssertionError("native D4 wet connectivity mismatch")
                if a["trace_component_id"][step, i] == a["trace_component_id"][step, j]:
                    merged_frames += 1
                    if abs(stage[i] - stage[j]) > 1e-7:
                        raise AssertionError("merged owners lack common stage")
        if step == 0:
            previous = initial.copy()
            paired = a["initial_redistribution_face_m3"]
            delta = a["initial_redistribution_m3"]
        else:
            dt = a["step_dt_seconds"][step - 1]
            prior_stage = a["trace_owner_stage_m"][step - 1]
            prior_component = a["trace_component_id"][step - 1]
            coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
            for edge, ((left, right), crest) in enumerate(zip(faces, source["internal_crest_m"])):
                first, second = int(owner[left]), int(owner[right])
                if prior_component[first] == prior_component[second]:
                    reference_q = 0.
                else:
                    high, low = max(prior_stage[first], prior_stage[second]), min(prior_stage[first], prior_stage[second])
                    reference_q = (coefficient * max(high - max(crest, low), 0.) ** 1.5 *
                                   np.sign(prior_stage[first] - prior_stage[second]))
                error = abs(reference_q - a["step_internal_q_m3_s"][step - 1, edge])
                max_weir_error = max(max_weir_error, error)
                if error > 1e-8:
                    raise AssertionError("independent original D4 internal weir law mismatch")
            for edge, ((left, _), crest, kind) in enumerate(zip(boundary,
                    source["boundary_crest_m"], source["boundary_kinds"])):
                reference_q = (coefficient * max(prior_stage[owner[left]] - crest, 0.) ** 1.5
                               if kind == "free_outflow" else 0.)
                error = abs(reference_q - a["step_boundary_q_m3_s"][step - 1, edge])
                max_weir_error = max(max_weir_error, error)
                if error > 1e-8:
                    raise AssertionError("independent original D4 boundary weir law mismatch")
            index = min(int(np.searchsorted(a["forcing_time_seconds"],
                a["time_seconds"][step - 1], side="right") - 1), len(local) - 1)
            previous = a["trace_owner_volume_m3"][step - 1] + dt * local[index]
            for flux, (left, right) in zip(a["step_internal_q_m3_s"][step - 1], faces):
                previous[owner[left]] -= dt * flux
                previous[owner[right]] += dt * flux
            for flux, (left, _) in zip(a["step_boundary_q_m3_s"][step - 1], boundary):
                previous[owner[left]] -= dt * flux
            paired = a["step_redistribution_face_m3"][step - 1]
            delta = a["step_redistribution_m3"][step - 1]
        face_delta = np.zeros(n)
        for amount, (left, right) in zip(paired, faces):
            face_delta[owner[left]] -= amount
            face_delta[owner[right]] += amount
        np.testing.assert_allclose(face_delta, delta, atol=1e-7)
        np.testing.assert_allclose(previous + face_delta, a["trace_owner_volume_m3"][step], atol=1e-6)
        max_projection_balance = max(max_projection_balance, abs(float(face_delta.sum())))
        max_balance = max(max_balance, float(np.max(abs(previous + face_delta - volume))))
    expected_total = float(initial.sum() + np.sum(a["step_dt_seconds"][:, None] *
                      np.array([local[min(int(np.searchsorted(a["forcing_time_seconds"], t,
                        side="right") - 1), len(local) - 1)] for t in a["time_seconds"][:-1]])))
    expected_total -= float(np.sum(a["step_dt_seconds"][:, None] * a["step_boundary_q_m3_s"]))
    actual_total = float(a["trace_owner_volume_m3"][-1].sum())
    if abs(expected_total - actual_total) > 1e-5:
        raise AssertionError("real TD global native water balance failed")
    return {"status": trace["metadata"]["status"],
            "steps": len(a["step_dt_seconds"]), "merged_owner_pair_frames": merged_frames,
            "final_owner_volume_m3": a["trace_owner_volume_m3"][-1].tolist(),
            "final_owner_stage_m": a["trace_owner_stage_m"][-1].tolist(),
            "final_wet_cells": int(a["trace_wet_support"][-1].sum()),
            "max_owner_balance_m3": max_balance,
            "max_independent_weir_error_m3_s": max_weir_error,
            "max_projection_pair_balance_m3": max_projection_balance,
            "global_balance_m3": actual_total - expected_total}


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    domain = load_natural_lakes(DOMAIN_PATH, expected_sha256=DOMAIN_SHA,
                                expected_identity=DOMAIN_ID)
    source = load_diagnostic_product(TD_PATH, expected_sha256=TD_SHA,
                                     expected_identity=TD_ID)
    d, s = domain["arrays"], source["arrays"]
    if domain["metadata"]["source_identity_sha256"] != source["metadata"]["terrain_identity_sha256"]:
        raise AssertionError("TD256 source provenance changed")
    owner = d["owner_grid"]
    local = np.column_stack([s["local_q_m3_s"][:, owner == i].sum(axis=1)
                             for i in range(len(LEAVES))])
    bed = d["source_height_m"].ravel()
    area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    initial = np.array([area * np.maximum(1347. - bed[owner.ravel() == i], 0.).sum()
                        for i in range(len(LEAVES))])
    times = s["time_seconds"].copy()
    if times[-1] != 900. or len(d["seed_cell_ids"]) != 6:
        raise AssertionError("unexpected frozen TD six-leaf interval")
    forcing = EquilibriumLakeForcing(times, local,
        np.zeros((len(times) - 1, len(d["boundary_faces"]))),
        np.zeros_like(local), domain["metadata"]["source_identity_sha256"],
        "pinned TD256 selected owner local runoff counted once",
        "0" * 64, "explicit zero channel-port forcing in standalone equilibrium case")
    cases, artifacts, runs = {}, {}, {}
    for name, dt in (("td-coarse", .5), ("td-fine", .125)):
        result = solve_equilibrium_lakes(domain, forcing, initial,
                                          EquilibriumLakeConfig(max_dt_seconds=dt))
        if result["metadata"]["status"] != "complete":
            raise AssertionError((name, result["metadata"]["failure_reason"]))
        path = output / (name + ".npz")
        save_equilibrium_lakes(path, result)
        sha = file_sha256(path)
        with patch("terrain_pipeline.surface_rivers.metric_equilibrium_lake_support.solve_equilibrium_lakes",
                   side_effect=AssertionError("cold audit must not solve")):
            cold = load_equilibrium_lakes(path, expected_sha256=sha)
            cases[name] = _independent_cold(domain, cold, initial, local)
        artifacts[name] = {"path": path.name, "sha256": sha,
                           "identity_sha256": result["identity_sha256"]}
        runs[name] = result
    stage_diff = float(np.max(abs(runs["td-coarse"]["arrays"]["trace_owner_stage_m"][-1] -
                                  runs["td-fine"]["arrays"]["trace_owner_stage_m"][-1])))
    if stage_diff > .001:
        raise AssertionError(("TD equilibrium stage refinement", stage_diff))
    if cases["td-fine"]["merged_owner_pair_frames"] <= 0:
        raise AssertionError("real TD case never exercised common stage")
    report = {"schema": "td-equilibrium-lake-extension-verification-v1",
              "status": "accepted_bounded_equilibrium_lake_support",
              "cases": cases, "artifacts": artifacts,
              "td_stage_refinement_m": stage_diff,
              "domain": {"path": str(DOMAIN_PATH), "sha256": DOMAIN_SHA,
                         "identity_sha256": DOMAIN_ID},
              "td_source": {"path": str(TD_PATH), "sha256": TD_SHA,
                            "identity_sha256": TD_ID},
              "td_leaf_nodes": LEAVES,
              "td_local_input_m3": float(np.sum(local * np.diff(times)[:, None])),
              "limitations": ["instant_equilibrium_original_D4_components_not_Saint_Venant",
                              "finite_native_support_and_explicit_boundary_faces",
                              "zero_channel_port_forcing_this_standalone_case",
                              "TD256_six_leaf_scope_not_global_natural_lake_certification"],
              "hydraulic_ready": False, "natural_outlet_verified": False,
              "publishable": False}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode())
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output)
    print(json.dumps({key: result[key] for key in
          ("status", "td_stage_refinement_m", "td_local_input_m3")}))


if __name__ == "__main__":
    main()
