"""Cold-audit saved M3/M4 geometry, source mappings, fluxes and real wet footprint."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_topology import basin_volume_at_level as basin_volume_at_level
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_coupled_product import load_coupled_product, sample_coupled_output, decode_coupled_product
from tools.verify_td_river_lake_coupling import connected_wet


DISABLED = ("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled",
            'terrain_pipeline.surface_hydraulics.solve_channel',
            'terrain_pipeline.basin_topology.build_basin_hierarchy',
            'terrain_pipeline.drainage.route_diagnostic',
            "terrain_pipeline.surface_rivers.metric_product.build_diagnostic_product",
            'terrain_pipeline.runoff.runoff_from_forcing',
            'terrain_pipeline.runoff.runoff_from_forcing_large')


def audit(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    acceptance = directory / "acceptance.json"
    report = json.loads(acceptance.read_text(encoding="utf-8"))
    if report["status"] != "accepted_bounded_coupling" or any(report[key] is not False for key in (
        "hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("bounded un-certified acceptance required")
    artifacts = {}
    spill_events = {}
    with ExitStack() as stack:
        for entrypoint in DISABLED:
            stack.enter_context(patch(entrypoint, side_effect=AssertionError("cold invoked " + entrypoint)))
        for name, pin in report["artifacts"].items():
            artifacts[name] = load_coupled_product(directory / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        selection = report["td_selection"]
        source_pin = selection["source_product"]
        source = load_diagnostic_product(selection["source_product_path"], expected_sha256=source_pin["sha256"], expected_identity=source_pin["identity_sha256"])
        hierarchy = load_basin_hierarchy(selection["hierarchy_path"], expected_sha256=selection["hierarchy_sha256"],
                                         expected_identity=selection["hierarchy_identity_sha256"])
        if file_sha256(selection["source_path"]) != selection["source_sha256"]:
            raise ValueError("raw TD source changed")
        sa, ha = source["arrays"], hierarchy["arrays"]
        np.testing.assert_array_equal(sa["elevation_m"], ha["height_m"])
        seed, node = selection["d8_terminal_cell"], selection["d4_leaf_node"]
        if sa["graph_outlet_kind"][seed] != "lake_preserved" or source["metadata"]["routing_identity_sha256"] != selection["d8_graph_identity_sha256"]:
            raise ValueError("D8 terminal/source mapping differs")
        support = np.flatnonzero(ha["cell_owner"].ravel() == node)
        np.testing.assert_array_equal(support, selection["lake_support_cell_ids"])
        if (ha["node_parent"] == node).any() or int(support[np.argmin(ha["height_m"].ravel()[support])]) != seed:
            raise ValueError("D4 selected node is not mapped leaf minimum")
        crest = float(ha["node_upper_m"][node])
        if not np.isfinite(crest) or crest != selection["crest_stage_m"]:
            raise ValueError("D4 first saddle differs")
        path = np.asarray(selection["channel_source_cell_ids"], np.int64)
        if np.intersect1d(path, support).size or np.unique(path).size != len(path):
            raise ValueError("TD source ownership overlaps")
        np.testing.assert_array_equal(sa["graph_receiver"][path[:-1]], path[1:])
        if int(sa["graph_receiver"][path[-1]]) != selection["channel_intake_receiver_cell"] or sa["graph_receiver"][path[-1]] not in support:
            raise ValueError("TD intake does not reach chosen lake support")
        for name in ("td_coarse", "td_fine"):
            product = artifacts[name]
            net, lakes, outlets, mapping, forcing, boundaries = decode_coupled_product(product)
            lake = lakes[0]
            np.testing.assert_array_equal(net.receiver, np.r_[np.arange(1, len(path)), -1])
            np.testing.assert_array_equal(net.length_m, sa["graph_edge_length_m"][path])
            np.testing.assert_array_equal(net.bed_slope, sa["graph_edge_slope"][path])
            np.testing.assert_array_equal(net.bed_elevation_m, sa["elevation_m"].ravel()[path])
            np.testing.assert_array_equal(lake.cell_ids, support)
            np.testing.assert_array_equal(lake.bed_elevation_m, sa["elevation_m"].ravel()[support])
            np.testing.assert_array_equal(lake.cell_area_m2, np.full(len(support), 900.))
            np.testing.assert_array_equal(forcing.channel_local_q_m3_s, sa["local_q_m3_s"].reshape(3, -1)[:, path])
            np.testing.assert_array_equal(forcing.lake_local_q_m3_s[:, 0], sa["local_q_m3_s"].reshape(3, -1)[:, support].sum(axis=1))
            np.testing.assert_array_equal(forcing.time_seconds, sa["time_seconds"])
            expected_mapping = np.full(len(path), -1, np.int64)
            expected_mapping[-1] = 0
            np.testing.assert_array_equal(mapping, expected_mapping)
            if (net.source_identity_sha256 != source["identity_sha256"] or lake.source_identity_sha256 != source["identity_sha256"]
                    or forcing.source_identity_sha256 != source["identity_sha256"] or len(outlets) != 1
                    or outlets[0].crest_stage_m != crest or outlets[0].receiver != -1
                    or outlets[0].coefficient_m3_s_m15 != 2. or lake.max_stage_m != crest + .05
                    or product["arrays"]["trace_lake_volume_m3"][0, 0] != selection["initial_lake_volume_m3"]):
                raise ValueError("TD explicit scenario binding differs")
            for stage in np.r_[np.unique(lake.bed_elevation_m), crest]:
                np.testing.assert_allclose(lake.volume_at_stage(float(stage)), basin_volume_at_level(hierarchy, node, float(stage)), rtol=1e-10, atol=1e-7)
                if not connected_wet(support[lake.bed_elevation_m < stage], seed, sa["elevation_m"].shape[1]):
                    raise ValueError("source lake sublevel wet cells disconnected")
            dense = sample_coupled_output(product, np.arange(0., 901., 30.))
            sparse = sample_coupled_output(product, np.array([0., 900.]))
            for key in ("channel_volume_m3", "lake_volume_m3", "cumulative_channel_boundary_volume_m3", "cumulative_lake_external_volume_m3"):
                np.testing.assert_array_equal(dense["arrays"][key][0], sparse["arrays"][key][0])
                np.testing.assert_array_equal(dense["arrays"][key][-1], sparse["arrays"][key][-1])
            trace = product["arrays"]
            volumes = trace["trace_lake_volume_m3"][:, 0]
            crest_volume = lake.volume_at_stage(crest)
            candidates = np.flatnonzero(volumes >= crest_volume)
            positive = np.flatnonzero(trace["trace_lake_outlet_q_m3_s"][:, 0] > 0.)
            if not len(candidates) or not len(positive):
                raise ValueError("saved TD event did not demonstrate a spill")
            first = int(candidates[0])
            crossing = float(trace["trace_time_seconds"][0]) if first == 0 else float(np.interp(
                crest_volume, volumes[first - 1:first + 1], trace["trace_time_seconds"][first - 1:first + 1]))
            spill_events[name] = {"crest_crossing_interpolated_s": crossing,
                                 "first_positive_outlet_step_s": float(trace["trace_time_seconds"][positive[0]]),
                                 "initial_lake_volume_m3": float(volumes[0]), "final_lake_volume_m3": float(volumes[-1])}
        # Full source and solved product independently constrain the saved wet geometry.
        fine = artifacts["td_fine"]
        stage = float(fine["arrays"]["trace_lake_stage_m"][-1, 0])
        geom_pin = selection["wet_footprint"]
        def validate_geometry(bundle):
            arrays, meta = bundle["arrays"], bundle["metadata"]
            if (set(arrays) != {"source_cell_ids", "source_bed_m", "cell_area_m2", "wet_mask", "depth_m", "channel_source_cell_ids", "contribution_mask"}
                    or bundle["identity_sha256"] != geom_pin["identity_sha256"] or bundle["identity_sha256"] != identity(arrays, meta)
                    or meta["schema"] != "td-m4-wet-footprint-v1" or meta["final_stage_m"] != stage
                    or meta["first_saddle_m"] != crest or meta["d4_leaf_node"] != node or meta["d8_terminal_cell"] != seed
                    or meta["source_product_identity_sha256"] != source["identity_sha256"]
                    or meta["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]
                    or any(meta[key] is not False for key in ("natural_outlet_verified", "publishable"))):
                raise ValueError("TD wet geometry schema/identity mismatch")
            np.testing.assert_array_equal(arrays["source_cell_ids"], support)
            np.testing.assert_array_equal(arrays["source_bed_m"], sa["elevation_m"].ravel()[support])
            np.testing.assert_array_equal(arrays["cell_area_m2"], np.full(len(support), 900.))
            np.testing.assert_array_equal(arrays["channel_source_cell_ids"], path)
            np.testing.assert_array_equal(arrays["contribution_mask"], sa["graph_lake_id"] == seed)
            np.testing.assert_array_equal(arrays["wet_mask"], arrays["source_bed_m"] < stage)
            np.testing.assert_allclose(arrays["depth_m"], np.maximum(stage - arrays["source_bed_m"], 0.), rtol=0., atol=1e-10)
            np.testing.assert_allclose(float(np.sum(arrays["depth_m"] * arrays["cell_area_m2"])), fine["arrays"]["trace_lake_volume_m3"][-1, 0], rtol=1e-10, atol=1e-7)
        geometry = load_bundle(directory / geom_pin["path"], expected_sha256=geom_pin["sha256"], validator=validate_geometry, max_bytes=8 * 1024 * 1024)
    output.mkdir(parents=True, exist_ok=False)
    # Render actual source cells and saved water depths, without centreline smoothing.
    shape = sa["elevation_m"].shape
    cells = np.r_[support, path]
    rows, columns = cells // shape[1], cells % shape[1]
    r0, r1 = max(0, int(rows.min()) - 3), min(shape[0], int(rows.max()) + 4)
    c0, c1 = max(0, int(columns.min()) - 3), min(shape[1], int(columns.max()) + 4)
    extent = (c0 - .5, c1 - .5, r1 - .5, r0 - .5)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    axes[0].imshow(sa["elevation_m"][r0:r1, c0:c1], extent=extent, cmap="terrain")
    water = np.full((r1-r0, c1-c0), np.nan)
    wet_ids = support[geometry["arrays"]["wet_mask"]]
    water[wet_ids // shape[1]-r0, wet_ids % shape[1]-c0] = geometry["arrays"]["depth_m"][geometry["arrays"]["wet_mask"]]
    image = axes[0].imshow(np.ma.masked_invalid(water), extent=extent, cmap="Blues", vmin=0., vmax=max(1e-6, float(np.nanmax(water))), alpha=.9)
    axes[0].scatter(path % shape[1], path // shape[1], c="#d13468", s=28, label="Channel source control")
    fig.colorbar(image, ax=axes[0], shrink=.72, label="Saved final water depth (m)")
    axes[0].set_title("Real TD bed and finite wet support")
    axes[0].set_xlabel("Native 30 m grid column")
    axes[0].set_ylabel("Native 30 m grid row")
    axes[0].legend(fontsize=8)
    for name in ("td_coarse", "td_fine"):
        trace = artifacts[name]["arrays"]
        times = trace["trace_time_seconds"]
        axes[1].plot(times, trace["trace_lake_stage_m"][:, 0] - crest, label=name)
        axes[2].plot((times[:-1] + times[1:]) / 2., trace["trace_lake_outlet_q_m3_s"][:, 0], label=name)
    axes[1].axhline(0., color="#c63c5a", linestyle="--", linewidth=.8)
    axes[1].set_title("Lake stage relative to first saddle")
    axes[1].set_ylabel("Stage minus crest (m)")
    axes[2].set_title("Interval-average spill to excluded basin")
    axes[2].set_ylabel("Q (m3/s)")
    for axis in axes[1:]:
        axis.set_xlabel("Physical time (s)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    fig.suptitle("Saved TD M4 evidence: explicit near-spill initial storage; fixed support above saddle; natural lake merger unresolved")
    fig.tight_layout(rect=(0., 0., 1., .9))
    fig.savefig(output / "td-lake-cold-preview.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    result = {"schema": "td-m3-m4-cold-audit-v1", "status": "passed", "acceptance_sha256": file_sha256(acceptance),
              "disabled_entrypoints": list(DISABLED), "trace_count": len(artifacts),
              "source_d4_d8_mapping_verified": True, "disjoint_local_input_verified": True,
              "sub_saddle_connected_wet_footprint_verified": True,
              "saved_final_depth_volume_verified": True, "dense_sparse_state_and_integral_verified": True,
              "lake_support_cell_count": len(support), "d8_contribution_cell_count": int(geometry["arrays"]["contribution_mask"].sum()),
              "above_first_saddle_is_engineering_fixed_support": True,
              "spill_events": spill_events,
              "code_sha256": {str(path.relative_to(ROOT)): file_sha256(path) for path in (
                  ROOT / 'terrain_pipeline/lake.py',
                  ROOT / "terrain_pipeline/surface_rivers/metric_boundary_coupling.py",
                  ROOT / "terrain_pipeline/surface_rivers/metric_coupled_product.py",
                  Path(__file__).resolve())}}
    publish_bytes(output / "cold-audit.json", json.dumps(result, indent=2).encode("utf-8"))
    return result


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
