"""Independent reduced natural-lake references and pinned real D4 TD replay."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from scipy.ndimage import label

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.lake import NaturalLakeConfig as NaturalLakeConfig
from terrain_pipeline.lake import build_natural_lakes as build_natural_lakes
from terrain_pipeline.lake import load_natural_lakes as load_natural_lakes
from terrain_pipeline.lake import save_natural_lakes as save_natural_lakes
from terrain_pipeline.lake import solve_natural_lakes as solve_natural_lakes
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from tools.verify_td_river_geometry import terrain_from_product


ROOT = Path(__file__).resolve().parents[1]
TD_PATH = ROOT / "verification/td-river-milestones/td256-20261008-01/product.npz"
TD_SHA = "01e7db47838aafe6028f39520895ce8f758ce3d8989e4564822bdee3388677e5"
TD_ID = "d485a50daded18e08db222cd07b4c23435aceb48f7007a3e3782d3367f863d42"
HIERARCHY_PATH = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
HIERARCHY_SHA = "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422"
HIERARCHY_ID = "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"


def independent_stage(bed, area, volume):
    lo = float(np.min(bed))
    hi = lo + volume / area + float(np.ptp(bed)) + 1.
    for _ in range(80):
        middle = (lo + hi) / 2.
        if area * np.maximum(middle - bed, 0.).sum() > volume:
            hi = middle
        else:
            lo = middle
    return (lo + hi) / 2.


def reference(domain, forcing_time, local, initial, tailwater, end_time):
    a, m = domain["arrays"], domain["metadata"]
    own, bed = a["owner_grid"].ravel(), a["source_height_m"].ravel()
    terrain = m["terrain_metadata"]
    area = terrain["dx_m"] * terrain["dz_m"]
    n = len(initial)
    faces, boundary = a["internal_faces"], a["boundary_faces"]
    coefficient = m["weir_coefficient_m3_s_m15"]
    basin_beds = [bed[own == i] for i in range(n)]

    def rhs(t, values, interval):
        stage = np.array([independent_stage(b, area, max(v, 0.)) for b, v in zip(basin_beds, values)])
        change = local[interval].copy()
        for first, second in faces:
            i, j = own[first], own[second]
            crest = max(bed[first], bed[second])
            head = max(max(stage[i], stage[j]) - max(crest, min(stage[i], stage[j])), 0.)
            q = coefficient * head ** 1.5 * np.sign(stage[i] - stage[j])
            change[i] -= q
            change[j] += q
        for index, (first, second) in enumerate(boundary):
            i = own[first]
            crest = bed[first] if second < 0 else max(bed[first], bed[second])
            kind = a["boundary_kinds"][index]
            if kind == "free_outflow":
                q = coefficient * max(stage[i] - crest, 0.) ** 1.5
            elif kind == "tailwater":
                delta = stage[i] - tailwater[interval, index]
                head = max(max(stage[i], tailwater[interval, index]) - max(crest, min(stage[i], tailwater[interval, index])), 0.)
                q = coefficient * head ** 1.5 * np.sign(delta)
            else:
                q = 0.
            change[i] -= q
        return change
    state = initial.copy()
    for interval, (start, end) in enumerate(zip(forcing_time[:-1], forcing_time[1:])):
        if start >= end_time:
            break
        solution = solve_ivp(lambda t, y: rhs(t, y, interval), (start, min(end, end_time)), state,
                             method="Radau", rtol=2e-10, atol=1e-9, max_step=1.)
        if not solution.success:
            raise AssertionError(solution.message)
        state = solution.y[:, -1]
    return state


def cold_evidence(domain, result):
    a = result["arrays"]
    d = domain["arrays"]
    metadata = domain["metadata"]["terrain_metadata"]
    area = metadata["dx_m"] * metadata["dz_m"]
    own, bed = d["owner_grid"].ravel(), d["source_height_m"].ravel()
    support = d["support_cell_ids"]
    n = len(d["seed_cell_ids"])
    max_residual = 0.
    for k, stage in enumerate(a["stage_m"]):
        actual = np.array([area * np.maximum(stage[i] - bed[own == i], 0.).sum() for i in range(n)])
        np.testing.assert_allclose(actual, a["volume_m3"][k], rtol=1e-9, atol=1e-7)
        wet = (own >= 0) & (bed < stage[np.maximum(own, 0)])
        np.testing.assert_array_equal(wet[support], a["wet_support"][k])
        native_labels, _ = label(wet.reshape(d["owner_grid"].shape))
        seed_labels = native_labels.ravel()[d["seed_cell_ids"]]
        for i in range(n):
            basin_wet = support[(own[support] == i) & wet[support]]
            if len(basin_wet):
                np.testing.assert_array_equal(native_labels.ravel()[basin_wet], np.full(len(basin_wet), seed_labels[i]))
        for i in range(n):
            for j in range(i + 1, n):
                expected_connected = seed_labels[i] > 0 and seed_labels[i] == seed_labels[j]
                if expected_connected != (a["wet_component"][k, i] == a["wet_component"][k, j]):
                    raise AssertionError("wet component differs from independent native D4 labels")
        local_volume = np.zeros(n)
        for interval, (start, end) in enumerate(zip(a["forcing_time_seconds"][:-1], a["forcing_time_seconds"][1:])):
            local_volume += a["local_q_m3_s"][interval] * max(min(a["time_seconds"][k], end) - start, 0.)
        expected = a["initial_volume_m3"] + local_volume
        for q, (first, second) in zip(a["internal_transfer_m3"][k], d["internal_faces"]):
            expected[own[first]] -= q
            expected[own[second]] += q
        for q, (first, _) in zip(a["boundary_transfer_m3"][k], d["boundary_faces"]):
            expected[own[first]] -= q
        residual = float(np.max(np.abs(expected - a["volume_m3"][k])))
        max_residual = max(max_residual, residual)
        np.testing.assert_allclose(expected, a["volume_m3"][k], rtol=1e-9, atol=1e-7)
    return dict(max_node_residual_m3=max_residual,
                final_volume_m3=a["volume_m3"][-1].tolist(),
                final_stage_m=a["stage_m"][-1].tolist(),
                final_wet_cells=int(a["wet_support"][-1].sum()),
                internal_absolute_transfer_m3=float(np.abs(a["internal_transfer_m3"][-1]).sum()),
                status=result["metadata"]["status"], last_time_seconds=float(a["time_seconds"][-1]))


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases, artifacts = {}, {}

    def run(name, domain, times, local, initial, tailwater, max_step):
        result = solve_natural_lakes(domain, times, local, initial, tailwater,
            config=NaturalLakeConfig(max_step_seconds=max_step), forcing_provenance=name)
        path = output / (name + ".npz")
        save_natural_lakes(path, result)
        pin = dict(path=path.name, sha256=file_sha256(path), identity_sha256=result["identity_sha256"])
        with patch('terrain_pipeline.lake.solve_natural_lakes', side_effect=AssertionError("cold solve")):
            cold = load_natural_lakes(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
            cases[name] = cold_evidence(domain, cold)
        ref = reference(domain, times, local, initial, tailwater, cases[name]["last_time_seconds"])
        error = float(np.max(np.abs(ref - result["arrays"]["volume_m3"][-1])))
        relative = error / max(float(np.max(np.abs(ref))), 1e-9)
        if relative > .005:
            raise AssertionError((name, "independent Radau", error, relative))
        cases[name].update(independent_reference_error_m3=error, independent_reference_relative=relative)
        artifacts[name] = pin
        return result

    from tests.test_metric_natural_lakes import two_lakes, two_saddles
    domain = two_lakes()
    for step in (.5, .125):
        run("two-pool-" + str(step), domain, np.array([0., 3., 20.]), np.array([[7., 0.], [0., 0.]]),
            np.zeros(2), np.zeros((2, 1)), step)
    domain = two_saddles()
    run("multiple-saddles", domain, np.array([0., 20.]), np.array([[2., 0.]]), np.zeros(2), np.empty((1, 0)), .125)
    run("capacity-or-unresolved-failed-prefix", domain, np.array([0., 100.]), np.array([[100., 0.]]),
        np.zeros(2), np.empty((1, 0)), .125)
    for kind in ("free_outflow", "tailwater"):
        domain = two_lakes(boundary_kind=kind)
        run(kind, domain, np.array([0., 2.]), np.zeros((1, 2)), np.zeros(2), np.array([[6.]]), .125)

    source = load_diagnostic_product(TD_PATH, expected_sha256=TD_SHA, expected_identity=TD_ID)
    hierarchy = load_basin_hierarchy(HIERARCHY_PATH, expected_sha256=HIERARCHY_SHA, expected_identity=HIERARCHY_ID)
    terrain = terrain_from_product(source)
    np.testing.assert_array_equal(terrain.elevation_m, hierarchy["arrays"]["height_m"])
    original_owner = hierarchy["arrays"]["contribution_owner"]
    leaves = np.array([1, 2, 3, 6, 8, 9], np.int64)
    owner = np.full(original_owner.shape, -1, np.int64)
    seeds = []
    for index, leaf in enumerate(leaves):
        ids = np.flatnonzero(original_owner.ravel() == leaf)
        seeds.append(int(ids[np.argmin(terrain.elevation_m.ravel()[ids])]))
        owner[original_owner == leaf] = index
    perimeter = np.zeros_like(owner, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    perimeter_ids = np.flatnonzero((owner >= 0) & perimeter)
    boundary_faces = np.column_stack((perimeter_ids, np.full(len(perimeter_ids), -1))).astype(np.int64)
    boundary_kinds = np.array(["free_outflow" if source["arrays"]["boundary_kind"].ravel()[cell] == "open_outflow"
                               else "unknown" for cell in perimeter_ids], dtype="U16")
    domain = build_natural_lakes(terrain, np.array(seeds, np.int64), owner,
        max_stage_m=np.full(len(leaves), 1348.5), boundary_faces=boundary_faces,
        boundary_kinds=boundary_kinds, weir_coefficient_m3_s_m15=10.,
        source_provenance="pinned original TD256 and frozen D4 contribution owners 1,2,3,6,8,9",
        boundary_provenance="source perimeter open_outflow faces explicit free outflow; other excluded faces unresolved")
    path = output / "td-domain.npz"
    save_natural_lakes(path, domain)
    artifacts["td-domain"] = dict(path=path.name, sha256=file_sha256(path), identity_sha256=domain["identity_sha256"])
    local = np.column_stack([source["arrays"]["local_q_m3_s"][:, owner == i].sum(axis=1) for i in range(len(leaves))])
    bed = terrain.elevation_m.ravel()
    initial = np.array([terrain.cell_area_m2 * np.maximum(1347.0 - bed[owner.ravel() == i], 0.).sum() for i in range(len(leaves))])
    times = source["arrays"]["time_seconds"].copy()
    td_runs = []
    for name, step in (("td-coarse", 2.), ("td-fine", .5)):
        td_runs.append(run(name, domain, times, local, initial, np.zeros((len(times)-1, len(boundary_faces))), step))
    coarse, fine = [product["arrays"] for product in td_runs]
    stage_diff = float(np.max(np.abs(coarse["stage_m"][-1] - fine["stage_m"][-1])))
    if stage_diff > .001:
        raise AssertionError(("TD natural lake stage refinement", stage_diff))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for i, leaf in enumerate(leaves):
        axes[0].plot(fine["time_seconds"], fine["stage_m"][:, i], label="leaf " + str(leaf))
    axes[0].set_xlabel("Physical seconds")
    axes[0].set_ylabel("Native-prism level (m)")
    axes[0].legend()
    wet = np.zeros(terrain.elevation_m.size)
    wet[domain["arrays"]["support_cell_ids"]] = fine["wet_support"][-1]
    rows, cols = np.where(owner >= 0)
    r0, r1, c0, c1 = rows.min()-2, rows.max()+3, cols.min()-2, cols.max()+3
    r0, r1, c0, c1 = max(r0,0), min(r1,len(owner)), max(c0,0), min(c1,owner.shape[1])
    axes[1].imshow(terrain.elevation_m[r0:r1,c0:c1], cmap="terrain")
    mask = np.ma.masked_where(wet.reshape(owner.shape)[r0:r1,c0:c1] == 0, wet.reshape(owner.shape)[r0:r1,c0:c1])
    axes[1].imshow(mask, cmap="winter", alpha=.7)
    axes[1].set_title("Original TD wet cells | reduced pools, no fine instantaneous water")
    fig.tight_layout()
    fig.savefig(output / "natural-lake-preview.png", dpi=150)
    plt.close(fig)
    report = dict(schema="td-natural-lake-extension-verification-v1", status="accepted_reduced_natural_support",
        cases=cases, artifacts=artifacts, td_stage_refinement_m=stage_diff,
        td_source=dict(path=str(TD_PATH), sha256=TD_SHA, identity_sha256=TD_ID),
        hierarchy=dict(path=str(HIERARCHY_PATH), sha256=HIERARCHY_SHA, identity_sha256=HIERARCHY_ID),
        td_leaf_nodes=leaves.tolist(), td_selected_local_input_m3=float(np.sum(local*np.diff(times)[:,None])),
        limitations=["piecewise_level_pool_signed_weir_not_channel_backwater_PDE",
                     "initial_near_saddle_preset", "excluded_exterior_saddles_unresolved",
                     "TD256_support_not_TD1024_global_lakes", "no_M3_channel_port_coupling"],
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode())
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output)
    print(json.dumps({key: result[key] for key in ("status", "td_stage_refinement_m", "td_selected_local_input_m3")}))


if __name__ == "__main__":
    main()
