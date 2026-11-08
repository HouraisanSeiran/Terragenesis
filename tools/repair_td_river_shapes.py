"""Run isolated physical river-shape repair against the six frozen TD sources."""

import argparse
import ast
import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_td_generated_source import load_generated_td_source
from terrain_pipeline.climate_forcing import grid_rainfall
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
    GeneratedRiverConfig, component_geometry, component_centerline, generate_sample, save_component_geometry,
    _continuous_profile, _local_route_crossings,
)
from terrain_pipeline.channel_geometry import initialize_centerline, turn_summary
from tools.generate_td_terrain_rivers import DEFAULT_REPORT, ROOT, snapshot_generation_sources


def validate_resume_sources(directory, snapshots):
    approved_old = {
        "tools/repair_td_river_shapes.py": "3092bb7b799e7655c911cbe5090e03839e3fc6f3cc4dbdce5790ba4ce44614aa",
        "terrain_pipeline/surface_rivers/metric_td_generated_rivers.py": "4736057fe4538a748787c5c12e96d123ef85e18c4660428395b54449aac09268",
    }
    approved_merge_functions = {
        "terrain_pipeline/surface_rivers/metric_valley_union.py": {
            "_sparse_mesh": (
                "ed3caffe3a711c088e4039912e87e84d36a7688a536bc6658a044090e1329570",
                "e4b59174f6464e14c6291d8438206060c7b93e8ba1fcc410eb53f72928c08037"),
        },
        "terrain_pipeline/surface_rivers/metric_design_bed.py": {
            "interior_support_boundary_vertices": (
                "c4d21770ef8330d94b7bfd711152c88c694312f8c39f546a83970a9a40bbc939",
                "a216726889248efa67fa93007cad0befc8d2d99ac0b31a0e2b74db65c311e7bd"),
            "merge_design_bundles": (
                "75cc505916e6789217c2b23735a6b4a604f44affc1d04d08bcbdbbf12c280c91",
                "7d8afbc9b9b1b4c29684fb4f5f4ff9ec8b84ab97e700c4187242ac8c5a917ba9"),
        },
    }
    records = []
    def module_tree(path, excluded):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.FunctionDef) and node.name in excluded)]
        return ast.dump(tree, include_attributes=False)
    for pin in snapshots:
        name = pin["source_path"]
        old_path = directory / pin["path"]
        old_hash = file_sha256(old_path)
        function_changes = []
        if old_hash == pin["sha256"]:
            comparison = "identical_bytes"
        elif (name == "tools/repair_td_river_shapes.py"
              and old_hash == "f874ec9e1bb2ee87ecfb6dc8f62343961041140613a003282255ff4f74168426"):
            if module_tree(old_path, {"validate_resume_sources"}) != module_tree(ROOT / name, {"validate_resume_sources"}):
                raise ValueError("resume entrypoint outside compatibility validator differs")
            comparison = "approved_resume_compatibility_validator_change"
        elif name in approved_merge_functions:
            functions = approved_merge_functions[name]
            if module_tree(old_path, functions) != module_tree(ROOT / name, functions):
                raise ValueError("resume source outside approved merge functions differs: " + name)
            for function, expected_pair in functions.items():
                pair = []
                for path in (old_path, ROOT / name):
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                    node = next(node for node in tree.body
                                if isinstance(node, ast.FunctionDef) and node.name == function)
                    pair.append(hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest())
                if tuple(pair) != expected_pair:
                    raise ValueError("resume approved merge function differs: " + function)
                function_changes.append(dict(function=function, original_ast_sha256=pair[0],
                                             current_ast_sha256=pair[1]))
            comparison = "approved_equivalent_mesh_and_merge_resource_change"
        elif name in approved_old:
            if old_hash != approved_old[name]:
                raise ValueError("resume orchestration snapshot differs: " + name)
            if name.endswith("metric_td_generated_rivers.py"):
                current_tree = ast.parse((ROOT / name).read_text(encoding="utf-8-sig"))
                orchestration = ast.Module(body=[node for node in current_tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name in ("generate_sample", "_resume_component")], type_ignores=[])
                orchestration_hash = hashlib.sha256(
                    ast.dump(orchestration, include_attributes=False).encode()).hexdigest()
                if orchestration_hash != "d1fe33c6aaec7d9dca36417e4211b0ba9395f71f41e3799fc40dbd870e1165fc":
                    raise ValueError("resume orchestration differs from reviewed implementation")
                excluded = {"generate_sample", "_resume_component"}
                if module_tree(old_path, excluded) != module_tree(ROOT / name, excluded):
                    raise ValueError("resume physical algorithm differs")
            comparison = "approved_resume_orchestration_change"
        else:
            raise ValueError("resume source snapshot differs: " + name)
        record = dict(source_path=name, original_sha256=old_hash,
                      current_sha256=pin["sha256"], comparison=comparison)
        if function_changes:
            record["function_changes"] = function_changes
        records.append(record)
    return records


def copy_completed_sample(source, target, registration, config, progress_pin):
    report_path = source / "report.json"
    if file_sha256(report_path) != progress_pin["report_sha256"]:
        raise ValueError("resume completed report differs from progress pin")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report["config"] != asdict(config)
            or report["source_registration"] != registration["metadata"]
            or report["status"] != "completed_all_selected_edges_classified"):
        raise ValueError("resume completed sample source, config or status differs")
    pins = [report["network"], *report["geometry_artifacts"]]
    if report["global_bed"] is not None:
        pins.append(report["global_bed"])
    for pin in pins:
        if file_sha256(source / pin["path"]) != pin["sha256"]:
            raise ValueError("resume completed artifact differs: " + pin["path"])
    shutil.copytree(source, target)
    for pin in pins:
        if file_sha256(target / pin["path"]) != pin["sha256"]:
            raise ValueError("resume copied artifact differs: " + pin["path"])
    if file_sha256(target / "report.json") != progress_pin["report_sha256"]:
        raise ValueError("resume copied report differs")
    return report


def peak_process_memory_bytes():
    if os.name != "nt":
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    import ctypes
    from ctypes import wintypes

    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.PeakWorkingSetSize)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--baseline", type=Path, default=ROOT / "verification/td-terrain-generated-rivers/generated-20261011-04")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", type=int, choices=range(6))
    parser.add_argument("--component", type=int)
    parser.add_argument("--all-six", action="store_true")
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--path-only", action="store_true")
    parser.add_argument("--reference-actual", action="store_true")
    parser.add_argument("--corridor-m", type=float, default=30.0)
    parser.add_argument("--iterations", type=int, default=24)
    args = parser.parse_args(argv)
    if args.all_six == (args.sample is not None or args.component is not None):
        parser.error("choose --all-six or both --sample and --component")
    if not args.all_six and (args.sample is None or args.component is None):
        parser.error("diagnostic requires both --sample and --component")
    if args.all_six and args.path_only:
        parser.error("path-only requires explicit diagnostic component")
    if args.all_six and args.reference_actual:
        parser.error("reference-actual is diagnostic only; all-six uses original-TD initialization")
    if args.resume_from and not args.all_six:
        parser.error("resume-from requires all-six")
    config = GeneratedRiverConfig(centerline_corridor_m=args.corridor_m,
                                  centerline_iterations=args.iterations)
    args.output.mkdir(parents=True, exist_ok=False)
    snapshots = snapshot_generation_sources(args.output)
    resume = None
    if args.resume_from:
        resume = dict(path=str(args.resume_from.resolve()),
                      source_comparison=validate_resume_sources(args.resume_from, snapshots),
                      completed_samples=[], component_samples=[])
        publish_bytes(args.output / "resume-provenance.json",
                      json.dumps(resume, indent=2, allow_nan=False).encode())
    baseline_manifest = json.loads((args.baseline / "manifest.json").read_text(encoding="utf-8"))
    if file_sha256(args.report) != baseline_manifest["generation_report_sha256"]:
        raise ValueError("generation report differs from pinned baseline")
    samples = []
    for index in range(6) if args.all_six else [args.sample]:
        started = time.perf_counter()
        registration = load_generated_td_source(args.report, index)
        pin = next(sample for sample in baseline_manifest["samples"] if sample["sample_index"] == index)
        baseline_report = args.baseline / pin["report_path"]
        if file_sha256(baseline_report) != pin["report_sha256"]:
            raise ValueError("baseline sample report differs from manifest pin")
        old = json.loads(baseline_report.read_text(encoding="utf-8"))
        terrain = registration["terrain"]
        sample_reused = False
        if (old["source_registration"]["terrain_identity_sha256"] != terrain.identity_sha256
                or old["source_registration"]["boundary_identity_sha256"] != registration["boundary"].identity_sha256):
            raise ValueError("baseline terrain or boundary differs from frozen registration")
        baseline_network = args.baseline / f"sample-{index}" / old["network"]["path"]
        if file_sha256(baseline_network) != old["network"]["sha256"]:
            raise ValueError("baseline network differs from pinned sample report")
        forcing, forcing_metadata = grid_rainfall(
            terrain.generation_seed, origin_xz_m=(terrain.x0_m, terrain.z0_m),
            shape_zx=terrain.elevation_m.shape, spacing_m=float(terrain.dx_m),
            time_edges_s=[0.0, 900.0])
        if forcing_metadata != old["forcing"]:
            raise ValueError("baseline forcing differs from frozen-source forcing")
        if args.all_six:
            source = args.resume_from / f"sample-{index}" if args.resume_from else None
            target = args.output / f"sample-{index}"
            if source and (source / "report.json").exists():
                progress_path = args.resume_from / f"progress-sample-{index}.json"
                progress_pin = json.loads(progress_path.read_text(encoding="utf-8"))
                report = copy_completed_sample(source, target, registration, config, progress_pin)
                sample_reused = True
                resume["completed_samples"].append(dict(sample_index=index,
                    report_path=str((source / "report.json").resolve()),
                    report_sha256=file_sha256(source / "report.json"),
                    progress_path=str(progress_path.resolve()),
                    progress_sha256=file_sha256(progress_path)))
            else:
                report, bundles = generate_sample(target, registration, config, resume_from=source)
                del bundles
                if source and source.exists():
                    resume["component_samples"].append(dict(sample_index=index,
                        components=[dict(component_id=row["component_id"], **row["reused_from"])
                                    for row in report["component_records"] if "reused_from" in row]))
            record = dict(sample_index=index, accepted_edges=report["accepted_edges"],
                          rejected_edges=report["rejected_edges"],
                          report_path=f"sample-{index}/report.json",
                          report_sha256=file_sha256(args.output / f"sample-{index}/report.json"),
                          baseline_accepted_edges=old["accepted_edges"],
                          accepted_edge_change=report["accepted_edges"] - old["accepted_edges"])
            if sample_reused:
                record["reused_from"] = resume["completed_samples"][-1]
                record["original_runtime"] = progress_pin.get("runtime")
        else:
            with np.load(baseline_network, allow_pickle=False) as archive:
                if (not np.array_equal(archive["source_height_m"], terrain.elevation_m)
                        or not np.array_equal(archive["rainfall_mm_h"], forcing.rain_mm_h[0])):
                    raise ValueError("baseline network source or rainfall differs")
                edge_indices = np.flatnonzero(archive["selected_component_id"] == args.component)
                if not len(edge_indices):
                    raise ValueError("baseline component has no edges")
                sources = archive["selected_edge_source_ids"][edge_indices]
                targets = archive["selected_edge_target_ids"][edge_indices]
                ids = np.unique(np.r_[sources, targets])
                widths = archive["width_m"][ids]
                depths = archive["base_depth_m"][ids]
            mapping = {int(cell): i for i, cell in enumerate(ids)}
            receiver = np.full(len(ids), -1, np.int64)
            for source, target in zip(sources, targets):
                receiver[mapping[int(source)]] = mapping[int(target)]
            record = dict(sample_index=index, component_id=args.component,
                          selected_edge_indices=edge_indices.tolist(), edge_count=len(sources),
                          baseline_report_sha256=file_sha256(baseline_report))
            old_component = next(c for c in old["component_records"] if c["component_id"] == args.component)
            reference_points = None
            if old_component["status"] == "accepted":
                old_geometry = args.baseline / f"sample-{index}" / old_component["geometry"]["path"]
                if file_sha256(old_geometry) != old_component["geometry"]["sha256"]:
                    raise ValueError("baseline component geometry differs from report pin")
                with np.load(old_geometry, allow_pickle=False) as archive:
                    if (not np.array_equal(ids, archive["source_node_cell_ids"])
                            or not np.array_equal(receiver, archive["receiver"])):
                        raise ValueError("baseline actual path topology differs")
                    reference_points = archive["node_xz_m"].copy()
                record["baseline_geometry_sha256"] = old_component["geometry"]["sha256"]
            try:
                if args.path_only:
                    cols = terrain.elevation_m.shape[1]
                    original = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                                                terrain.z0_m + ids // cols * terrain.dz_m))
                    points, _, policy = component_centerline(
                        terrain, ids, receiver, widths, depths, config,
                        reference_points=reference_points if args.reference_actual else None)
                    initialized = initialize_centerline(
                        original, receiver, terrain,
                        validate=lambda candidate: _local_route_crossings(candidate, receiver),
                        certify=lambda candidate: _continuous_profile(candidate, receiver, depths, terrain,
                                                                      config.max_cut_m, config.fine_spacing_m))
                    policy["deterministic_initializer_turns"] = turn_summary(initialized, receiver)
                    policy["deterministic_initializer_max_difference_from_reference_m"] = float(
                        np.linalg.norm(initialized - (reference_points if reference_points is not None else original), axis=1).max())
                    if reference_points is not None:
                        policy["saved_baseline_actual_turns"] = turn_summary(reference_points, receiver)
                    path = args.output / f"sample-{index}-component-{args.component}-path.npz"
                    np.savez_compressed(path, source_node_cell_ids=ids, receiver=receiver,
                                        original_node_xz_m=original, node_xz_m=points,
                                        baseline_node_xz_m=reference_points if reference_points is not None else original)
                    record.update(status="path_only_certified_no_bed_generated", path=path.name,
                                  sha256=file_sha256(path), metadata=policy)
                else:
                    def progress(phase):
                        print(json.dumps(dict(sample=index, component=args.component, phase=phase,
                                              elapsed_seconds=time.perf_counter() - started)), flush=True)
                    bundle = component_geometry(terrain, ids, receiver, widths, depths, config,
                                                reference_points=reference_points if args.reference_actual else None,
                                                progress=progress)
                    path = args.output / f"sample-{index}-component-{args.component}.npz"
                    save_component_geometry(path, bundle)
                    record.update(status="accepted", path=path.name, sha256=file_sha256(path),
                                  metadata=bundle["metadata"])
            except ValueError as error:
                record.update(status="rejected", reason=str(error))
        samples.append(record)
        record["runtime"] = dict(process_id=os.getpid(), elapsed_seconds=time.perf_counter() - started,
                                 peak_process_working_set_bytes=peak_process_memory_bytes(),
                                 peak_semantics="process lifetime peak, includes source loading and saved product validation")
        record["runtime"]["operation"] = "validate_and_copy_completed_sample" if sample_reused else "generate_or_resume_sample"
        publish_bytes(args.output / f"progress-sample-{index}.json", json.dumps(record, indent=2, allow_nan=False).encode())
        if resume is not None:
            publish_bytes(args.output / f"resume-provenance-sample-{index}.json",
                          json.dumps(resume, indent=2, allow_nan=False).encode())
    manifest = dict(schema="td-terrain-generated-rivers-v1" if args.all_six else "td-river-shape-repair-v1", samples=samples,
                    status="completed" if args.all_six else "component_diagnostic_only",
                    baseline=str(args.baseline.resolve()), source_snapshots=snapshots,
                    baseline_manifest_sha256=file_sha256(args.baseline / "manifest.json"),
                    generation_report_path=str(args.report.resolve()),
                    generation_report_sha256=file_sha256(args.report),
                    selection="all_six_frozen_manifest_order_no_output_filtering" if args.all_six else "explicit_component_diagnostic",
                    entrypoint_sha256=file_sha256(Path(__file__)),
                    natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    if resume is not None:
        manifest["resume"] = resume
    publish_bytes(args.output / "manifest.json", json.dumps(manifest, indent=2, allow_nan=False).encode())


if __name__ == "__main__":
    main()
