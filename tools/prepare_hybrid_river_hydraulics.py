"""Explicit graph preparation and separately authorized bounded 1D experiments."""

from dataclasses import asdict, replace
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_river_graph import (
    FilePin, MAX_FILE_BYTES, build_graph, canonical_json, identity, load_graph,
    native_bed_pieces, read_pinned)
from terrain_pipeline.hybrid_river_hydraulics import (
    Experiment, Model, compare_refinement, run_experiment)

SURFACE_INDEX_SHA = "d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68"
SURFACE_AUDIT_SHA = "54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5"
CODE_FILES = ("terrain_pipeline/hybrid_river_graph.py", "terrain_pipeline/hybrid_river_hydraulics.py",
              "tools/prepare_hybrid_river_hydraulics.py", "tests/test_hybrid_river_graph.py", "tests/test_hybrid_river_hydraulics.py")


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pin(path, sha=None):
    path = Path(path).resolve(strict=True)
    return FilePin(str(path), sha or file_sha(path))


def saved_pin(record):
    return FilePin(record["path"], record["sha256"])


def check_original_pins(inputs):
    for key, record in inputs.items():
        original = saved_pin(record)
        if file_sha(original.path) != original.sha256:
            raise ValueError("original input pin changed: " + key)


def prepare_graph(args):
    index_pin, audit_pin = pin(args.surface_index, args.surface_index_sha256), pin(args.surface_audit, args.surface_audit_sha256)
    if index_pin.sha256 != SURFACE_INDEX_SHA or audit_pin.sha256 != SURFACE_AUDIT_SHA:
        raise ValueError("only the frozen actual passed task14 package is authorized")
    index, audit = read_pinned(index_pin), read_pinned(audit_pin)
    if audit["index_sha256"] != index_pin.sha256 or audit.get("errors") or audit["inputs"] != index["inputs"]:
        raise ValueError("surface passed audit/index binding mismatch")
    artifacts, bindings = {}, {"surface_index": index_pin, "surface_audit": audit_pin}
    for key in ("graph", "manifest", "topology", "selection", "mesh"):
        artifact_pin = saved_pin(index[key])
        if audit[key + "_sha256"] != artifact_pin.sha256:
            raise ValueError("surface artifact audit binding mismatch")
        artifacts[key] = read_pinned(artifact_pin)
        bindings["surface_" + key] = artifact_pin
    check_original_pins(index["inputs"])
    bindings.update(("original_" + key, saved_pin(record)) for key, record in index["inputs"].items())
    for name, sha in index["code_sha256"].items():
        if file_sha(ROOT / name) != sha:
            raise ValueError("frozen parent code changed: " + name)
    fine_index_pin, fine_audit_pin = pin(args.fine_index, args.fine_index_sha256), pin(args.fine_audit, args.fine_audit_sha256)
    fine_index, fine_audit = read_pinned(fine_index_pin), read_pinned(fine_audit_pin)
    if fine_audit["status"] != "passed" or fine_audit.get("errors") or fine_audit["index_sha256"] != fine_index_pin.sha256:
        raise ValueError("fine input is not independently passed and bound")
    channel = fine_index["channel"]
    if fine_audit["channel"] != channel:
        raise ValueError("fine independent audit original channel bindings differ")
    if channel["index"]["sha256"] != index_pin.sha256 or channel["audit"]["sha256"] != audit_pin.sha256:
        raise ValueError("fine package belongs to another surface package")
    bindings.update(fine_index=fine_index_pin, fine_audit=fine_audit_pin)
    for key in ("manifest", "compact_fans", "material"):
        artifact_pin = saved_pin(fine_index[key])
        if fine_audit[key + "_sha256"] != artifact_pin.sha256:
            raise ValueError("fine artifact differs from passed audit")
        read_pinned(artifact_pin)
        bindings["fine_" + key] = artifact_pin
    ports = {}
    for row in artifacts["manifest"]["ports"]:
        if row["arc_id"] in (args.sink_arc, args.spring_arc):
            port_pin = saved_pin(row["pin"])
            witness = audit["ports"][row["arc_id"]]
            if witness["sha256"] != port_pin.sha256 or witness["path"] != port_pin.path:
                raise ValueError("chosen canonical port file is not the audited witness")
            ports[row["arc_id"]] = read_pinned(port_pin)
            bindings["portal_" + row["arc_id"]] = port_pin
    saved_nodes = {}
    for row in artifacts["manifest"]["nodes"]:
        if row["node_id"] not in artifacts["manifest"]["selected_node_ids"]:
            continue
        node_pin = saved_pin(row["pin"])
        witness = audit["nodes"][row["node_id"]]
        if witness["sha256"] != node_pin.sha256 or witness["path"] != node_pin.path:
            raise ValueError("surface half-arm/bed node is not the audited file")
        saved_nodes[row["node_id"]] = read_pinned(node_pin)
        bindings["accepted_node_" + row["node_id"]] = node_pin
    graph = build_graph(artifacts["graph"], artifacts["manifest"], artifacts["topology"], audit,
                        ports, bindings, args.sink_arc, args.spring_arc, saved_nodes)
    return {"graph.json": graph.to_record()}


def validate_geometry(graph_record, geometry_pin, geometry_audit_pin):
    graph = load_graph(graph_record)
    geometry, audit = read_pinned(geometry_pin), read_pinned(geometry_audit_pin)
    if geometry["schema"] != "td-hybrid-river-geometry-v1" or geometry["graph_identity_sha256"] != graph_record["identity_sha256"]:
        raise ValueError("geometry belongs to a different typed graph")
    unsigned = dict(geometry)
    geometry_identity = unsigned.pop("identity_sha256")
    if identity(unsigned) != geometry_identity:
        raise ValueError("geometry identity mismatch")
    if audit["status"] != "passed" or audit.get("errors") or audit["geometry_sha256"] != geometry_pin.sha256 or audit["graph_identity_sha256"] != graph_record["identity_sha256"]:
        raise ValueError("geometry independent audit binding mismatch")
    if audit["schema"] != "td-hybrid-cave-geometry-independent-audit-v1":
        raise ValueError("wrong independent geometry audit schema")
    if not audit["actual_hydraulic_sections_verified"] or not audit["actual_portal_connections_verified"]:
        raise ValueError("node adjacency is not actual hydraulic/void attachment evidence")
    for key, graph_pin in graph.inputs:
        if geometry["inputs"].get(key) != asdict(graph_pin):
            raise ValueError("geometry omitted immutable parent pin: " + key)
        if file_sha(graph_pin.path) != graph_pin.sha256:
            raise ValueError("graph original pin changed: " + key)
    check_original_pins(geometry["inputs"])
    for kind, ordinal in (("sink", 0), ("spring", -1)):
        node = next(node for node in graph.nodes if node.kind == kind)
        port = json.loads(node.source_record_json)
        binding = geometry["portal_bindings"][kind]
        if binding["port_arc_id"] != node.port_arc_id or binding["port_identity_sha256"] != port["identity_sha256"]:
            raise ValueError("actual portal differs from selected audited midpoint")
        if geometry["portal_sections"][kind]["pieces"] != native_bed_pieces(port):
            raise ValueError("portal omitted/changed complete native function")
    active_arcs = {arc.arc_id: arc for arc in graph.arcs if arc.hydraulic_role == "sample_route"}
    required_arcs = {"surface_in": "engineered:sink:half_arm_attachment", "underground": "engineered:underground", "surface_out": "engineered:spring:half_arm_attachment"}
    station_ids = []
    regions = []
    for cell in geometry["hydraulic_cells"]:
        region = cell["route_region"]
        if region not in required_arcs or cell["graph_arc_id"] != required_arcs[region] or cell["graph_arc_id"] not in active_arcs:
            raise ValueError("actual section is not on the physical graph route")
        reference = cell["section_geometry_reference"]
        station_ids.append(reference["station_id"])
        regions.append(region)
        ring = reference["derived_ring_xyz_m"]
        origin = reference["origin_xyz_m"]
        transverse = reference["transverse_unit_xz"]
        import math
        if len(transverse) != 2 or abs(math.hypot(*transverse) - 1) > 1e-10:
            raise ValueError("section frame is not a unit transverse direction")
        section = cell["section"]
        shape = section["polygon_transverse_elevation_m"] if section["kind"] == "closed_polygon" else section["polyline_transverse_elevation_m"]
        if len(ring) != len(shape):
            raise ValueError("storage shape differs from final derived ring")
        for point, projected in zip(ring, shape):
            if len(point) != 3 or not all(math.isfinite(value) for value in point):
                raise ValueError("nonfinite actual section ring")
            delta_x, delta_z = point[0] - origin[0], point[2] - origin[2]
            if (abs(delta_x * transverse[0] + delta_z * transverse[1] - projected[0]) > 1e-8
                    or abs(point[1] - projected[1]) > 1e-8
                    or abs(delta_x * transverse[1] - delta_z * transverse[0]) > 1e-8):
                raise ValueError("section polygon is not the actual final VDM ring projection")
    if len(set(station_ids)) != len(station_ids) or set(regions) != set(required_arcs) or regions != sorted(regions, key=lambda region: list(required_arcs).index(region)):
        raise ValueError("missing/duplicated/out-of-order physical route stations")
    return Model.from_geometry(geometry), geometry


def prepare_runs(args):
    graph_pin, geometry_pin, geometry_audit_pin, experiment_pin = (
        pin(args.graph, args.graph_sha256), pin(args.geometry, args.geometry_sha256),
        pin(args.geometry_audit, args.geometry_audit_sha256), pin(args.experiments, args.experiments_sha256))
    graph_record = read_pinned(graph_pin)
    model, geometry = validate_geometry(graph_record, geometry_pin, geometry_audit_pin)
    configuration = read_pinned(experiment_pin)
    if configuration["schema"] != "td-hybrid-river-engineering-experiments-v1":
        raise ValueError("explicit engineering experiment configuration required")
    unsigned_configuration = dict(configuration)
    expected_identity = unsigned_configuration.pop("identity_sha256")
    if identity(unsigned_configuration) != expected_identity or configuration["graph_identity_sha256"] != graph_record["identity_sha256"] or configuration["geometry_identity_sha256"] != geometry["identity_sha256"]:
        raise ValueError("engineering forcing identity/geometry binding mismatch")
    if configuration["inputs"] != {"graph": asdict(graph_pin), "geometry": asdict(geometry_pin), "geometry_audit": asdict(geometry_audit_pin)}:
        raise ValueError("engineering configuration differs from actual pinned geometry")
    scenarios = configuration["scenarios"]
    if len(scenarios) != 2 or {record["scenario"] for record in scenarios} != {"pulse", "reverse_tailwater"}:
        raise ValueError("exactly pulse and reverse tailwater scenarios are authorized")
    records, summaries = {}, []
    for parameters in scenarios:
        experiment = Experiment(**{**parameters, "initial_heads_m": tuple(parameters["initial_heads_m"]), "saved_times_s": tuple(parameters["saved_times_s"])})
        base = run_experiment(model, experiment)
        refined_parameters = replace(experiment, max_step_s=experiment.max_step_s / 2,
                                     relative_tolerance=experiment.relative_tolerance / 4, absolute_tolerance=experiment.absolute_tolerance / 4)
        refined = run_experiment(model, refined_parameters)
        comparison = compare_refinement(base, refined, **configuration.get("refinement_tolerances", {}))
        required_evidence = refined["source_reached_engineered_outlet"] if experiment.scenario == "pulse" else refined["reverse_reached_sink"]
        status = "diagnostic_accepted" if comparison["status"] == "passed" and required_evidence else "refused_diagnostic_evidence"
        for label, result, saved_parameters in (("base", base, experiment), ("refined", refined, refined_parameters)):
            result.update(graph_identity_sha256=graph_record["identity_sha256"], geometry_identity_sha256=geometry["identity_sha256"],
                          inputs={"graph": asdict(graph_pin), "geometry": asdict(geometry_pin), "geometry_audit": asdict(geometry_audit_pin), "experiments": asdict(experiment_pin)},
                          parameters=asdict(saved_parameters), parameters_identity_sha256=identity(asdict(saved_parameters)))
            result["identity_sha256"] = identity(result)
            records[experiment.scenario + "-" + label + ".json"] = result
        summaries.append({"scenario": experiment.scenario, "status": status, "refinement": comparison,
                          "source_reached_engineered_outlet": refined["source_reached_engineered_outlet"], "reverse_reached_sink": refined["reverse_reached_sink"]})
    index = {"schema": "td-hybrid-river-hydraulics-preparation-v1", "status": "diagnostic_accepted" if all(row["status"] == "diagnostic_accepted" for row in summaries) else "refused_diagnostic_evidence",
             "graph_identity_sha256": graph_record["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
             "inputs": {"graph": asdict(graph_pin), "geometry": asdict(geometry_pin), "geometry_audit": asdict(geometry_audit_pin), "experiments": asdict(experiment_pin)},
             "summary": summaries, "independent_audit_passed": False, "natural_outlet_certified": False,
             "full_network_verified": False, "three_dimensional_flow_solved": False,
             "code_sha256": {name: file_sha(ROOT / name) for name in CODE_FILES},
             "work": {"new_1d_rhs_evaluations": sum(record["work"]["rhs_evaluations"] for record in records.values()),
                      "new_1d_link_evaluations": sum(record["work"]["link_evaluations"] for record in records.values()),
                      "old_hll_face_work": 0, "old_hll_face_budget_remaining_unchanged": 2_949_448_968}}
    records["index.json"] = index
    return records


def prepare_experiments(args):
    graph_pin, geometry_pin, geometry_audit_pin = pin(args.graph, args.graph_sha256), pin(args.geometry, args.geometry_sha256), pin(args.geometry_audit, args.geometry_audit_sha256)
    graph_record = read_pinned(graph_pin)
    model, geometry = validate_geometry(graph_record, geometry_pin, geometry_audit_pin)
    if not 0 < args.initial_depth_m <= 0.25 or not 0 < args.pulse_tailwater_depth_m <= 0.25 or args.observation_interval_s <= 0:
        raise ValueError("explicit bounded prewet depth/tailwater depth/observation interval required")
    heads = tuple(cell.section.floor_m + args.initial_depth_m for cell in model.cells)
    if any(cell.kind == "underground" and head >= cell.section.crown_m for cell, head in zip(model.cells, heads)):
        raise ValueError("requested prewet depth exceeds an actual conduit crown")
    import numpy as np
    count = int(np.ceil(args.duration_s / args.observation_interval_s))
    if not 1 <= count <= 4095:
        raise ValueError("physical observations exceed bounded count")
    times = tuple(float(value) for value in np.linspace(0, args.duration_s, count + 1))
    pulse = Experiment("pulse", args.duration_s, args.pulse_duration_s, args.pulse_q_m3_s,
                       model.cells[-1].section.floor_m + args.pulse_tailwater_depth_m, heads, times, max_step_s=args.max_step_s)
    reverse = replace(pulse, scenario="reverse_tailwater", pulse_duration_s=0, pulse_q_m3_s=0, tailwater_head_m=args.reverse_tailwater_head_m)
    if reverse.tailwater_head_m <= max(heads):
        raise ValueError("reverse engineering head must exceed the complete route initial heads")
    pulse.validate(model)
    reverse.validate(model)
    configuration = {"schema": "td-hybrid-river-engineering-experiments-v1", "status": "engineering_configuration_only_not_solver_result",
                     "inputs": {"graph": asdict(graph_pin), "geometry": asdict(geometry_pin), "geometry_audit": asdict(geometry_audit_pin)},
                     "graph_identity_sha256": graph_record["identity_sha256"], "geometry_identity_sha256": geometry["identity_sha256"],
                     "initial_water_semantics": "explicit_untraced_engineering_prewet_not_hidden_source",
                     "scenarios": [asdict(pulse), asdict(reverse)], "natural_outlet_certified": False,
                     "refinement_tolerances": {"volume_absolute_tolerance_m3": 1e-4, "head_absolute_tolerance_m": 1e-3, "volume_relative_tolerance": 0.01}}
    configuration["identity_sha256"] = identity(configuration)
    return {"experiments.json": configuration, "index.json": {"schema": "td-hybrid-river-engineering-configuration-preparation-v1", "status": "engineering_configuration_only_not_solver_result"}}


def publish(output, records):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("new output directory required; no frozen output overwrite")
    if output.parent != ROOT / "verification" / "natural-river-network":
        raise ValueError("new top-level verification package required; frozen package subdirectories cannot be modified")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hybrid-", dir=output.parent) as temporary:
        staging = Path(temporary) / "publish"
        staging.mkdir()
        artifacts = {}
        for name, record in records.items():
            if name == "index.json":
                continue
            payload = canonical_json(record).encode("utf-8")
            if len(payload) > MAX_FILE_BYTES:
                raise ValueError("bounded artifact file exceeded")
            (staging / name).write_bytes(payload)
            artifacts[name] = {"path": str(output / name), "sha256": hashlib.sha256(payload).hexdigest(), "identity_sha256": record["identity_sha256"]}
        index = dict(records.get("index.json", {"schema": "td-hybrid-river-graph-preparation-v1", "status": "candidate_geometry_pending", "full_network_verified": False}))
        index["artifacts"] = artifacts
        index["code_sha256"] = {name: file_sha(ROOT / name) for name in CODE_FILES}
        index["identity_sha256"] = identity(index)
        payload = canonical_json(index).encode("utf-8")
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError("bounded index file exceeded")
        (staging / "index.json").write_bytes(payload)
        staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    graph_parser = subparsers.add_parser("graph", help="prepare immutable graph only; no solver")
    graph_parser.add_argument("--surface-index", required=True, type=Path)
    graph_parser.add_argument("--surface-index-sha256", default=SURFACE_INDEX_SHA)
    graph_parser.add_argument("--surface-audit", required=True, type=Path)
    graph_parser.add_argument("--surface-audit-sha256", default=SURFACE_AUDIT_SHA)
    for name in ("fine-index", "fine-audit"):
        graph_parser.add_argument("--" + name, required=True, type=Path)
        graph_parser.add_argument("--" + name + "-sha256", required=True)
    graph_parser.add_argument("--sink-arc", required=True)
    graph_parser.add_argument("--spring-arc", required=True)
    run_parser = subparsers.add_parser("run", help="execute only pinned engineering pulse/reverse plus refinement")
    for name in ("graph", "geometry", "geometry-audit", "experiments"):
        run_parser.add_argument("--" + name, required=True, type=Path)
        run_parser.add_argument("--" + name + "-sha256", required=True)
    experiment_parser = subparsers.add_parser("experiments", help="prepare engineering forcing from audited actual sections; no solver")
    for name in ("graph", "geometry", "geometry-audit"):
        experiment_parser.add_argument("--" + name, required=True, type=Path)
        experiment_parser.add_argument("--" + name + "-sha256", required=True)
    for name in ("duration-s", "pulse-duration-s", "pulse-q-m3-s", "reverse-tailwater-head-m"):
        experiment_parser.add_argument("--" + name, required=True, type=float)
    experiment_parser.add_argument("--initial-depth-m", type=float, default=0.05)
    experiment_parser.add_argument("--pulse-tailwater-depth-m", type=float, default=0.03)
    experiment_parser.add_argument("--observation-interval-s", type=float, default=5)
    experiment_parser.add_argument("--max-step-s", type=float, default=2)
    for command in (graph_parser, run_parser, experiment_parser):
        command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("new output directory required")
    records = {"graph": prepare_graph, "experiments": prepare_experiments, "run": prepare_runs}[args.command](args)
    result = publish(args.output, records)
    print(json.dumps({"status": result["status"], "identity_sha256": result["identity_sha256"], "summary": result.get("summary")}))


if __name__ == "__main__":
    main()
