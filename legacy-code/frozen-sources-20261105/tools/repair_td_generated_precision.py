"""Repair observed TD support/closure refusals and reuse verified saved beds."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_td_generated_source import (
    load_generated_td_source,
)
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
    GeneratedRiverConfig,
    component_geometry,
    load_component_geometry,
    merge_component_beds,
    save_component_geometry,
)
from tools.generate_td_terrain_rivers import snapshot_generation_sources
from dataclasses import asdict


def write_json(path, value):
    publish_bytes(path, json.dumps(value, indent=2, allow_nan=False).encode())


def copy_verified(source, target, digest):
    if file_sha256(source) != digest:
        raise ValueError("original artifact differs: " + str(source))
    shutil.copy2(source, target)
    if file_sha256(target) != digest:
        raise ValueError("copied artifact differs: " + str(target))


def verified_component_fixture(
    receipt_path, terrain, ids, receiver, width, depth, config, original_algorithms
):
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("sample_index") != 1
        or receipt.get("component_id") != 2
        or receipt.get("status") != "independently_verified_complete_component_fixture"
    ):
        raise ValueError(
            "explicit independently verified sample-1 component-2 fixture required"
        )
    pins = {}
    for name in (
        "component_file",
        "saved_audit",
        "preflight",
        "original_counterfactual_file",
    ):
        pin = receipt[name]
        path = Path(pin["path"])
        if not path.is_absolute():
            path = receipt_path.parent / path
        if file_sha256(path) != pin["sha256"]:
            raise ValueError("fixture evidence differs: " + name)
        pins[name] = path
    preflight = json.loads(pins["preflight"].read_text(encoding="utf-8"))
    source_pins = preflight["algorithm_source_sha256"]
    if any(
        source_pins.get(name) != digest for name, digest in original_algorithms.items()
    ):
        raise ValueError("fixture shaping source differs from original generation")
    module = "terrain_pipeline/surface_rivers/metric_design_bed.py"
    root = Path(__file__).resolve().parents[1]
    if source_pins[module] != file_sha256(root / module):
        raise ValueError("fixture design solver differs from current solver")
    pin = receipt["component_file"]
    bundle = load_component_geometry(
        pins["component_file"],
        expected_sha256=pin["sha256"],
        expected_identity=pin["identity_sha256"],
    )
    a, m = bundle["arrays"], bundle["metadata"]
    if (
        m["source_identity_sha256"] != terrain.identity_sha256
        or m["config"] != asdict(config)
        or any(
            not np.array_equal(a[name], expected)
            for name, expected in (
                ("source_node_cell_ids", ids),
                ("receiver", receiver),
                ("width_m", width),
                ("design_base_depth_m", depth),
                ("source_height_m", terrain.elevation_m),
            )
        )
    ):
        raise ValueError(
            "fixture does not bind the same raw source and network component"
        )
    audit = json.loads(pins["saved_audit"].read_text(encoding="utf-8"))
    certificate = audit["continuous_design_certificate"]
    if (
        audit["artifact_sha256"] != pin["sha256"]
        or not certificate.get("passed")
        or certificate["status"]
        != "continuous_conservative_bottom_depth_profile_raw_cut_and_interior_seam_verified"
        or certificate["interior_support_seam_status"] != "zero_cut_verified"
    ):
        raise ValueError("fixture continuous design audit did not pass")
    return bundle, pins["component_file"], receipt


def repair(baseline, output, component_fixture_receipt=None):
    manifest_path = baseline / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "completed" or len(manifest["samples"]) != 6:
        raise ValueError("complete fixed six-sample baseline required")
    source_report = Path(manifest["generation_report_path"])
    if file_sha256(source_report) != manifest["generation_report_sha256"]:
        raise ValueError("raw generation report differs")
    output.mkdir(parents=True, exist_ok=False)
    snapshots = snapshot_generation_sources(output)
    tool_snapshot = output / "source-snapshots/tools/repair_td_generated_precision.py"
    shutil.copy2(Path(__file__), tool_snapshot)
    snapshots.append(
        dict(
            source_path="tools/repair_td_generated_precision.py",
            path="source-snapshots/tools/repair_td_generated_precision.py",
            sha256=file_sha256(tool_snapshot),
        )
    )
    final = dict(
        schema="td-terrain-generated-rivers-v1",
        status="running",
        collection_algorithm="verified-component-reuse-and-observed-support-design-closure-repair-v2",
        generation_report_path=str(source_report),
        generation_report_sha256=manifest["generation_report_sha256"],
        original_collection_manifest=dict(
            path=str(manifest_path.resolve()), sha256=file_sha256(manifest_path)
        ),
        source_snapshots=snapshots,
        samples=[],
        execution_policy="copy verified original component bytes; regenerate observed support or physical closure refusals with continuous design constraints; recompute global unique bed only when component artifact set changes",
        selection=manifest["selection"],
        natural_outlet_verified=False,
        hydraulic_ready=False,
        publishable=False,
    )
    write_json(output / "startup-manifest.json", final)
    for sample_pin in manifest["samples"]:
        index = sample_pin["sample_index"]
        old_report_path = baseline / sample_pin["report_path"]
        if file_sha256(old_report_path) != sample_pin["report_sha256"]:
            raise ValueError("original sample report differs")
        old_report = json.loads(old_report_path.read_text(encoding="utf-8"))
        original = old_report_path.parent
        destination = output / f"sample-{index}"
        destination.mkdir()
        network_path = original / old_report["network"]["path"]
        if file_sha256(network_path) != old_report["network"]["sha256"]:
            raise ValueError("original network differs")
        with np.load(network_path, allow_pickle=False) as archive:
            network = {key: archive[key] for key in archive.files}
        registration = load_generated_td_source(
            source_report,
            index,
            expected_report_sha256=manifest["generation_report_sha256"],
        )
        terrain = registration["terrain"]
        if not np.array_equal(network["source_height_m"], terrain.elevation_m):
            raise ValueError("saved original terrain differs")
        config = GeneratedRiverConfig(**old_report["config"])
        records, artifacts, bundles = [], [], []
        statuses = network["selected_edge_status"].copy()
        for old_record in old_report["component_records"]:
            record = dict(old_record)
            record["original_generation"] = dict(
                report_sha256=sample_pin["report_sha256"],
                collection_manifest_sha256=file_sha256(manifest_path),
                algorithm_source_sha256=old_report["algorithm_source_sha256"],
            )
            component = record["component_id"]
            edges = np.asarray(record["selected_edge_indices"], np.int64)
            if record["status"] == "accepted":
                pin = dict(record["geometry"])
                copy_verified(
                    original / pin["path"], destination / pin["path"], pin["sha256"]
                )
                bundle = load_component_geometry(
                    destination / pin["path"],
                    expected_sha256=pin["sha256"],
                    expected_identity=pin["identity_sha256"],
                )
                record["artifact_provenance"] = (
                    "verified_original_component_bytes_copied"
                )
                artifacts.append(pin)
                bundles.append(bundle)
            elif record.get(
                "reason"
            ) == "centerline point outside sparse triangles" or record.get(
                "reason", ""
            ).startswith(
                "shared physical-slope closure exceeds"
            ):
                sources = network["selected_edge_source_ids"][edges]
                targets = network["selected_edge_target_ids"][edges]
                ids = np.unique(np.r_[sources, targets])
                mapping = {int(cell): i for i, cell in enumerate(ids)}
                receiver = np.full(len(ids), -1, np.int64)
                for source, target in zip(sources, targets):
                    receiver[mapping[int(source)]] = mapping[int(target)]
                record["original_refusal_reason"] = record.pop("reason")
                record["artifact_provenance"] = (
                    "regenerated_observed_support_or_closure_refusal_with_continuous_design"
                )
                try:
                    path = destination / f"geometry-c{component}.npz"
                    if (
                        index == 1
                        and component == 2
                        and component_fixture_receipt is not None
                    ):
                        bundle, fixture_path, receipt = verified_component_fixture(
                            component_fixture_receipt,
                            terrain,
                            ids,
                            receiver,
                            network["width_m"][ids],
                            network["base_depth_m"][ids],
                            config,
                            old_report["algorithm_source_sha256"],
                        )
                        copy_verified(
                            fixture_path, path, receipt["component_file"]["sha256"]
                        )
                        record["artifact_provenance"] = (
                            "independently_verified_complete_component_fixture_bytes_copied"
                        )
                        record["fixture_receipt"] = dict(
                            path=str(component_fixture_receipt.resolve()),
                            sha256=file_sha256(component_fixture_receipt),
                            receipt=receipt,
                        )
                    else:
                        bundle = component_geometry(
                            terrain,
                            ids,
                            receiver,
                            network["width_m"][ids],
                            network["base_depth_m"][ids],
                            config,
                        )
                        save_component_geometry(path, bundle)
                    pin = dict(
                        path=path.name,
                        sha256=file_sha256(path),
                        identity_sha256=bundle["identity_sha256"],
                    )
                    load_component_geometry(
                        path,
                        expected_sha256=pin["sha256"],
                        expected_identity=pin["identity_sha256"],
                    )
                    record.update(
                        status="accepted",
                        geometry=pin,
                        cut_volume_m3=bundle["metadata"]["cut_volume_m3"],
                        maximum_cut_m=bundle["metadata"]["maximum_cut_m"],
                    )
                    statuses[edges] = "accepted"
                    artifacts.append(pin)
                    bundles.append(bundle)
                except ValueError as error:
                    record.update(status="rejected", reason=str(error))
            else:
                record["artifact_provenance"] = "original_physical_refusal_retained"
            records.append(record)
            print(
                json.dumps(
                    dict(
                        sample=index,
                        component=component,
                        status=record["status"],
                        provenance=record["artifact_provenance"],
                    )
                ),
                flush=True,
            )
        path = destination / "global-bed.npz"
        original_artifact_set = sorted(
            pin["sha256"] for pin in old_report["geometry_artifacts"]
        )
        new_artifact_set = sorted(pin["sha256"] for pin in artifacts)
        changed = original_artifact_set != new_artifact_set
        if changed:
            global_bundle = merge_component_beds(
                terrain, bundles, config, network_design_depth=network["base_depth_m"]
            )
            save_component_geometry(path, global_bundle)
            global_pin = dict(
                path=path.name,
                sha256=file_sha256(path),
                identity_sha256=global_bundle["identity_sha256"],
            )
            summed = sum(bundle["metadata"]["cut_volume_m3"] for bundle in bundles)
            unique = global_bundle["metadata"]["cut_volume_m3"]
            material = dict(
                unique_cut_volume_m3=unique,
                component_sum_cut_volume_m3=summed,
                component_max_envelope_cut_volume_m3=global_bundle["metadata"][
                    "component_max_cut_reference_volume_m3"
                ],
                overlap_double_count_m3=summed
                - global_bundle["metadata"]["component_max_cut_reference_volume_m3"],
                union_monotone_additional_cut_volume_m3=unique
                - global_bundle["metadata"]["preclosure_cut_volume_m3"],
                necessary_lower_cut_volume_m3=global_bundle["metadata"][
                    "preclosure_cut_volume_m3"
                ],
                reclosure_net_change_m3=unique
                - global_bundle["metadata"]["component_max_cut_reference_volume_m3"],
                closure_additional_cut_semantics="relative to necessary legacy/design minimum lower bound; net change is relative to component solved max envelope",
                material_policy=old_report["material_ledger"]["material_policy"],
            )
            global_provenance = (
                "recomputed_unique_mesh_after_component_artifact_set_changed"
            )
        else:
            global_pin = dict(old_report["global_bed"])
            copy_verified(original / global_pin["path"], path, global_pin["sha256"])
            material = dict(old_report["material_ledger"])
            global_provenance = "verified_original_global_bytes_unchanged_copied"
        load_component_geometry(
            path,
            expected_sha256=global_pin["sha256"],
            expected_identity=global_pin["identity_sha256"],
        )
        network["selected_edge_status"] = statuses
        np.savez_compressed(destination / "network.npz", **network)
        plan_path = original / "network-plan.npz"
        copy_verified(
            plan_path, destination / "network-plan.npz", file_sha256(plan_path)
        )
        report = dict(old_report)
        report.update(
            component_records=records,
            geometry_artifacts=artifacts,
            global_bed=global_pin,
            network=dict(
                path="network.npz", sha256=file_sha256(destination / "network.npz")
            ),
            accepted_edges=int(np.sum(statuses == "accepted")),
            rejected_edges=int(np.sum(statuses != "accepted")),
            generation_provenance="original verified component reuse plus observed support/design closure repair",
            global_bed_provenance=global_provenance,
            original_generation_algorithm_source_sha256=old_report[
                "algorithm_source_sha256"
            ],
            repair_source_snapshots=snapshots,
            material_ledger=material,
        )
        report.pop("algorithm_source_sha256", None)
        report_path = destination / "report.json"
        write_json(report_path, report)
        final["samples"].append(
            dict(
                sample_index=index,
                report_path=f"sample-{index}/report.json",
                report_sha256=file_sha256(report_path),
                accepted_edges=report["accepted_edges"],
                rejected_edges=report["rejected_edges"],
            )
        )
        write_json(output / f"progress-after-sample-{index}.json", final)
    final["status"] = "completed"
    write_json(output / "manifest.json", final)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component-fixture-receipt", type=Path)
    args = parser.parse_args()
    repair(args.baseline, args.output, args.component_fixture_receipt)
