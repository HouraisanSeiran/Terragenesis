"""Freeze current hydrology evidence without upgrading local scope to release."""
import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.hydrology_seasonal import load_seasonal_water_balance
from terrain_pipeline.hydrology_seasonal_hybrid import load_hybrid_lake_bundle


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def release_gates(full_edges, full_windows, confluence, naturalness, *, continuity=None, seam_supplement=None, mouth_edges=()):
    """Count only named cold producer scopes; a local junction is not a graph port."""
    continuity = continuity or {}
    fine = continuity.get("fine_evidence", [])
    graph = continuity.get("coarse_bed_graph") or {}
    schema = continuity.get("schema") == "hydrology-owned-basin-continuity-cold-v1"
    coarse = bool(schema and continuity.get("coarse_dag_accepted") and continuity.get("owned_cell_count") == continuity.get("traced_owned_cell_count"))
    profiles = bool(schema and graph.get("accepted") and graph.get("cold_saved_profile_audit", {}).get("accepted"))
    geometry = bool(fine and all(item.get("local_geometry_accepted") and item.get("cold_geometry_audits")
        and all(audit.get("accepted") and audit.get("frozen_profile_ceiling_verified") and audit.get("continuous_longitudinal_gradient_verified") for audit in item["cold_geometry_audits"]) for item in fine))
    seams = bool(fine and all(item.get("seam_audit", {}).get("accepted") and item.get("seam_audit", {}).get("continuous_affine_trace_verified") for item in fine))
    if seam_supplement:
        seams = bool(seam_supplement.get("schema") == "hydrology-owned-basin-complete-seam-supplement-v1"
                     and seam_supplement.get("accepted")
                     and {tuple(item["source_edge"]) for item in seam_supplement.get("fine_seam_reviews", [])} == {tuple(item["source_edge"]) for item in fine}
                     and all(item["seam_audit"].get("continuous_affine_trace_verified") for item in seam_supplement.get("fine_seam_reviews", [])))
    ports = bool(schema and continuity.get("fine_to_coarse_interfaces_accepted") and not continuity.get("fine_port_conflicts"))
    accepted_fine = {tuple(item["source_edge"]) for item in fine if item.get("local_geometry_accepted")}
    return {"complete_owned_coarse_dag": coarse, "complete_coarse_river_profiles": profiles,
        "declared_fine_geometry": geometry, "complete_fine_affine_seams": seams, "declared_fine_coarse_graph_ports": ports,
        "complete_selected_network_continuity": coarse and profiles and geometry and seams and ports,
        "key_fine_mouth_geometry": bool(geometry and seams and accepted_fine.intersection(set(mouth_edges))),
        "real_td_confluence": bool(confluence and confluence.get("local_window_compatible")
            and confluence.get("fine_to_coarse_fraction_interfaces_verified")
            and confluence.get("source_artifact_kind") == "terrain_diffusion_output"),
        "multiseed_real_td_naturalness": bool(naturalness and naturalness.get("naturalness_certified")
            and naturalness.get("fine_td_geometry_certified") and naturalness.get("same_parent_algorithm_verified"))}


def collect_local_sources(root, seeds):
    """Follow static local imports, including package initializers and lazy imports."""
    root = Path(root).resolve()
    pending = [root / path for path in seeds]
    found, external = set(), set()
    while pending:
        path = pending.pop().resolve()
        if path in found or not path.is_file():
            continue
        path.relative_to(root)
        found.add(path)
        relative = path.relative_to(root).with_suffix("")
        package = list(relative.parts[:-1])
        for count in range(1, len(package) + 1):
            initializer = root.joinpath(*package[:count], "__init__.py")
            if initializer.is_file():
                pending.append(initializer)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = prefix + (node.module.split(".") if node.module else [])
                names = [".".join(base)] + [".".join(base + [alias.name]) for alias in node.names if alias.name != "*"]
            for name in names:
                if not name:
                    continue
                candidate = root.joinpath(*name.split("."))
                module, initializer = candidate.with_suffix(".py"), candidate / "__init__.py"
                if module.is_file():
                    pending.append(module)
                elif initializer.is_file():
                    pending.append(initializer)
                elif isinstance(node, ast.Import) or node.level == 0:
                    external.add(name.split(".")[0])
    return found, sorted(name for name in external if not (root / name).is_dir() and not (root / (name + ".py")).is_file())


def copy_payload(root, destination, paths, source_paths, primary_data=()):
    """Copy code/reports and primary small state; large terrain archives stay pinned."""
    root, destination = Path(root).resolve(), Path(destination)
    primary_data = {Path(path).resolve() for path in primary_data}
    artifacts = []
    for path in sorted({Path(path).resolve() for path in paths}):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = "external/" + sha256(path)[:16] + "/" + path.name
        record = {"path": str(path), "repository_path": relative, "sha256": sha256(path), "bytes": path.stat().st_size}
        if path in source_paths or path in primary_data or path.suffix.lower() in (".json", ".md", ".txt", ".toml", ".html", ".png"):
            target = destination / "payload" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            if sha256(target) != record["sha256"]:
                raise ValueError("snapshot payload copy verification failed")
            record["payload_path"] = target.relative_to(destination).as_posix()
            record["storage"] = "fixed_payload_copy"
        else:
            record["storage"] = "external_archive_pinned_by_sha256"
        artifacts.append(record)
    return artifacts


def prepare_snapshot(plan_path, seasonal_path, hybrid_folder, output, *, full_edge_path=None,
                    full_window_paths=(), naturalness_path=None, confluence_path=None, continuity_path=None,
                    seam_supplement_path=None, root=ROOT):
    root = Path(root).resolve()
    plan = load_plan(plan_path)
    load_seasonal_water_balance(plan, seasonal_path)
    hybrid = load_hybrid_lake_bundle(plan, hybrid_folder)
    reports = {}
    paths = {Path(plan_path).resolve(), Path(seasonal_path).resolve()}
    paths.update(p.resolve() for p in Path(hybrid_folder).iterdir() if p.is_file())
    for name, path in (("full_edges", full_edge_path), ("naturalness", naturalness_path), ("confluence", confluence_path),
                       ("continuity", continuity_path), ("seam_supplement", seam_supplement_path)):
        if path:
            paths.add(Path(path).resolve())
            reports[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    windows = []
    for path in full_window_paths:
        paths.add(Path(path).resolve())
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        if report.get("plan_identity") != plan["identity_sha256"]:
            raise ValueError("full-window report belongs to another parent plan")
        windows.append(report)
    full_edges = reports.get("full_edges")
    if full_edges:
        identity = full_edges.get("plan_identity", full_edges.get("plan_identity_sha256"))
        if identity != plan["identity_sha256"]:
            raise ValueError("full-edge report belongs to another parent plan")
    confluence = reports.get("confluence")
    if confluence and confluence.get("plan_identity", confluence.get("plan_identity_sha256")) != plan["identity_sha256"]:
        raise ValueError("confluence report belongs to another parent plan")
    continuity = reports.get("continuity")
    if continuity and continuity.get("plan_identity") != plan["identity_sha256"]:
        raise ValueError("continuity report belongs to another parent plan")
    supplement = reports.get("seam_supplement")
    if supplement and (not continuity_path or supplement.get("plan_identity") != plan["identity_sha256"]
                       or supplement.get("parent_cold_review_sha256") != sha256(continuity_path)):
        raise ValueError("seam supplement belongs to another cold continuity review")
    naturalness = reports.get("naturalness")
    naturalness_matches_parent = False
    if naturalness:
        samples = naturalness.get("records", naturalness.get("reports", naturalness.get("results", [])))
        naturalness_matches_parent = bool(samples and all(sample.get("plan", {}).get("algorithm", sample.get("algorithm")) == plan["algorithm_version"] for sample in samples))
        if naturalness.get("schema") == "hydrology-fixed-multiseed-production-review-v1":
            if not naturalness.get("freeze_ready") or naturalness.get("fixed_denominator") != 12 or len(samples) != 12:
                raise ValueError("final fixed twelve-slot naturalness production review required")

            def validate_sample_pins(value):
                if isinstance(value, dict):
                    if isinstance(value.get("path"), str) and value.get("sha256"):
                        path = Path(value["path"])
                        path = path if path.is_absolute() else root / path
                        if sha256(path) != value["sha256"]:
                            raise ValueError("naturalness production artifact SHA pin mismatch")
                    for item in value.values():
                        validate_sample_pins(item)
                elif isinstance(value, list):
                    for item in value:
                        validate_sample_pins(item)

            validate_sample_pins(samples)
    source_seeds = ("tools/prepare_hydrology_algorithm_release.py", "tools/prepare_hydrology_domains.py",
                     ".scratch/hydrological-planning-domain/summarize_multiseed_production.py",
                     "tools/prepare_hydrology_full_edges.py", "tools/render_hydrology_domains.py",
                     "tools/audit_hydrology_planning_naturalness.py", "diffusion/geography_physical.py",
                     "diffusion/physical_config.py", "diffusion/geographic_noise.py",
                     "terrain_pipeline/mountain_source_adapter.py",
                     "terrain_pipeline/surface_rivers/metric_contracts.py",
                     "terrain_pipeline/surface_rivers/metric_design_bed.py",
                     "terrain_pipeline/surface_rivers/metric_channel_geometry.py",
                     "terrain_pipeline/surface_rivers/metric_valley_union.py",
                     "terrain_pipeline/surface_rivers/metric_monotone_union.py",
                     "terrain_pipeline/surface_rivers/metric_valley_incision.py",
                     "terrain_pipeline/surface_rivers/metric_noise_forcing.py")
    source_paths, external_imports = collect_local_sources(root, source_seeds)
    paths.update(source_paths)
    documentation = [root / "research/river-organization-and-tokunaga-references-20261013.md",
                     root / "TODO.md", root / "CONTEXT.md", root / "README.md",
                     root / "docs/hydrological-planning-domain-design.md",
                     root / "docs/hydrological-planning-domain-progress.md",
                     root / "docs/river-progress-and-reference-use-20261013.md"]
    documentation.extend((root / ".scratch/hydrological-planning-domain").glob("*.md"))
    documentation.extend((root / ".scratch/hydrological-planning-domain/issues").glob("*.md"))
    paths.update(path.resolve() for path in documentation if path.is_file())
    visual_evidence = set()
    for path in [*full_window_paths, *[item for item in (full_edge_path, continuity_path, confluence_path) if item]]:
        parent = Path(path).resolve().parent
        for directory in (parent / "figures", parent.parent / "figures"):
            if directory.is_dir():
                visual_evidence.update(item.resolve() for item in directory.iterdir()
                                       if item.is_file() and item.suffix.lower() in (".png", ".html"))
    paths.update(visual_evidence)
    requirements = root / "bootstrap-assets/requirements-lock.txt"
    if requirements.is_file():
        paths.add(requirements)
    missing_references = []
    # Existing report path references are diagnostic lineage, not portable payload declarations.
    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (key.endswith("path") and isinstance(item, str)) or (key.endswith("paths") and isinstance(item, list)):
                    items = [item] if isinstance(item, str) else item
                    for candidate in items:
                        if not isinstance(candidate, str):
                            continue
                        path = Path(candidate)
                        path = path if path.is_absolute() else root / path
                        if path.is_file():
                            paths.add(path.resolve())
                        else:
                            missing_references.append({"field": key, "path": candidate,
                                "status": "diagnostic_lineage_reference_missing"})
                else:
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    references(reports)
    references(windows)
    scanned_json = set()
    while True:
        pending_json = [path for path in paths if path.suffix.lower() == ".json" and path not in scanned_json]
        if not pending_json:
            break
        for path in pending_json:
            scanned_json.add(path)
            references(json.loads(path.read_text(encoding="utf-8")))
    for evidence in continuity.get("fine_evidence", []) if continuity else []:
        for pin in evidence.get("piece_archive_pins", []):
            if sha256(pin["path"]) != pin["sha256"]:
                raise ValueError("frozen continuity fine archive pin mismatch")
        if sha256(evidence["report_path"]) != evidence["report_sha256"]:
            raise ValueError("frozen continuity fine report pin mismatch")
    graph = (continuity.get("coarse_bed_graph") or {}) if continuity else {}
    for record in graph.get("edge_profiles", []):
        if sha256(record["path"]) != record["archive_sha256"]:
            raise ValueError("frozen continuity coarse archive pin mismatch")
    if confluence and confluence.get("schema") == "hydrology-confluence-fraction-interfaces-v1":
        for path_key, pin_key in (("parent_continuity_report_path", "parent_continuity_report_sha256"),
                                 ("generation_report_path", "generation_report_sha256"),
                                 ("independent_cold_report_path", "independent_cold_report_sha256"),
                                 ("piece_path", "piece_archive_sha256"), ("detail_path", "detail_archive_sha256"),
                                 ("sidecar_path", "sidecar_sha256"), ("component_request_path", "component_request_sha256")):
            if sha256(confluence[path_key]) != confluence[pin_key]:
                raise ValueError("frozen confluence source or cold evidence pin mismatch")
        for record in confluence["edge_profiles"]:
            if sha256(record["path"]) != record["archive_sha256"]:
                raise ValueError("frozen confluence fractional coarse archive pin mismatch")
    receiver = plan["receiver"].ravel()
    ocean = plan["ocean_mask"].ravel()
    mouths = {(index, int(downstream)) for index, downstream in enumerate(receiver) if downstream >= 0 and ocean[downstream]}
    gates = release_gates(full_edges, windows, reports.get("confluence"), reports.get("naturalness"),
                          continuity=continuity, seam_supplement=supplement, mouth_edges=mouths)
    gates["local_hybrid_periodic_lake"] = hybrid["manifest"]["status"] == "verified_local_periodic_lake"
    gates["naturalness_same_parent_algorithm"] = naturalness_matches_parent
    complete = all(gates.values())
    distributions = importlib.metadata.packages_distributions()
    runtime_packages = {}
    for module in external_imports:
        if module in sys.stdlib_module_names:
            continue
        runtime_packages[module] = {name: importlib.metadata.version(name) for name in distributions.get(module, [])}
    manifest = {"schema": "hydrology-current-algorithm-evidence-freeze-v2-fixed-payload",
        "status": "scoped_algorithm_evidence_ready" if complete else "evidence_snapshot_incomplete", "release_ready": complete,
        "algorithm_versions": {"planning": plan["algorithm_version"],
            "hybrid_lake": hybrid["audit"]["algorithm"], "release": "hydrology-current-algorithm-evidence-freeze-v2-fixed-payload"},
        "parent_plan_identity_sha256": plan["identity_sha256"], "seed": plan["seed"],
        "validation_runtime": {"python_executable": sys.executable, "python_version": sys.version, "external_packages": runtime_packages},
        "coordinates": {"axes": "world X,Z metres; raster row increases Z", "origin_xz_m": plan["origin_xz_m"],
            "coarse_spacing_m": plan["spacing_m"], "vertical_datum": plan["source"].get("vertical_datum")},
        "units": {"length": "m", "area": "m2", "volume": "m3", "rain_and_soil_depth": "mm"},
        "budgets": {"planning": plan["budget"], "local_windows": [w.get("budget") for w in windows],
            "hybrid_lake": hybrid["detail"]["metadata"].get("budget")},
        "completed": {"frozen_plan_cold_read": True, "seasonal_cold_read": True,
            "hybrid_lake_status": hybrid["manifest"]["status"],
            "local_window_reports": [{"status": w.get("status"), "coverage": w.get("coverage"),
                "local_window_compatible": w.get("local_window_compatible")} for w in windows]},
        "gates": gates, "pending": [name for name, passed in gates.items() if not passed],
        "naturalness_algorithm_matches_parent": naturalness_matches_parent,
        "missing_diagnostic_references": missing_references,
        "publication_limit": "release gates apply only to the named finite planning and representation scope; missing mouth, confluence fraction interfaces or naturalness remain blocking",
        "report_statuses": {key: value.get("status") for key, value in reports.items()},
        "representation_scope": continuity.get("scope") if continuity else None,
        "confluence_interface_limit": "a clipped three-arm mesh needs measured fraction ports into the coarse graph; matching parent identity or junction node alone does not close those ports",
        "scope": "same-parent current planning and seasonal chain; local evidence retained at declared scope",
        "global_hydrology_certified": False, "minecraft_ready": False}
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=output.name + "-staging-", dir=output.parent) as temporary:
        staging = Path(temporary)
        manifest["artifacts"] = copy_payload(root, staging, paths, source_paths, (plan_path, seasonal_path))
        manifest["visual_evidence_paths"] = [str(path) for path in sorted(visual_evidence)]
        instructions = ("# Fixed Hydrology Evidence Payload\n\n"
            "Source code, local import dependencies, reports, dependency lock and primary coarse/seasonal state are fixed copies under payload/. "
            "Manifest entries marked external_archive_pinned_by_sha256 require their original data archives and matching hashes. "
            "Large TD and fine geometry archives are not duplicated.\n\n"
            "release_ready reflects every listed gate for this finite scope. A coarse centerline profile does not certify an unrefined transverse section. "
            "Local confluence geometry does not certify its clipped fraction ports. Naturalness needs its own explicit evidence.\n\n"
            "This batch has not passed naturalness review and is a development candidate, not a mature release. "
            "Straight river alignment, correction bands and lost source texture remain documented limitations. "
            "The copied research notes state the extent of paper adoption: PLRG provides organization ideas; Tokunaga is an evaluation tool, not a generation template. "
            "DOI references without a full-text implementation review do not establish reproduction.\n\n"
            "Verify manifest.sha256 and every copied artifact SHA before using this snapshot. Run Python entry points from payload/ with the recorded runtime dependencies.\n")
        (staging / "README.md").write_text(instructions, encoding="utf-8")
        manifest["payload_readme_sha256"] = sha256(staging / "README.md")
        unsigned = json.dumps(manifest, sort_keys=True, allow_nan=False).encode()
        manifest["identity_sha256"] = hashlib.sha256(unsigned).hexdigest()
        target = staging / "manifest.json"
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (staging / "manifest.sha256").write_text(sha256(target), encoding="ascii")
        shutil.move(str(staging), str(output))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--seasonal", required=True)
    parser.add_argument("--hybrid-lake", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--full-edge-report")
    parser.add_argument("--full-window-report", action="append", default=[])
    parser.add_argument("--naturalness-report")
    parser.add_argument("--confluence-report")
    parser.add_argument("--continuity-report")
    parser.add_argument("--continuity-seam-supplement")
    args = parser.parse_args()
    manifest = prepare_snapshot(args.plan, args.seasonal, args.hybrid_lake, args.output,
        full_edge_path=args.full_edge_report, full_window_paths=args.full_window_report,
        naturalness_path=args.naturalness_report, confluence_path=args.confluence_report,
        continuity_path=args.continuity_report, seam_supplement_path=args.continuity_seam_supplement)
    print(manifest["status"])


if __name__ == "__main__":
    main()
