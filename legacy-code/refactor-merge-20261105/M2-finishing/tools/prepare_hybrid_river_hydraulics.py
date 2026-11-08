"""Current immutable graph/forcing preparation; hydraulic execution is explicit v8."""

from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]

from terrain_pipeline.hybrid_geometry import FilePin, MAX_FILE_BYTES, build_graph, canonical_json, identity, load_graph, native_bed_pieces, read_pinned
from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment
from tools.hybrid_hydraulics_preparation_common import (
    file_sha, pin, saved_pin, check_original_pins, validate_geometry)

SURFACE_INDEX_SHA = "d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68"
SURFACE_AUDIT_SHA = "54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5"
CODE_FILES = ("terrain_pipeline/hybrid_river_graph.py", "terrain_pipeline/hybrid_river_hydraulics_common.py",
              "tools/prepare_hybrid_river_hydraulics.py", "tests/test_hybrid_river_graph.py")


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
    for command in (graph_parser, experiment_parser):
        command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("new output directory required")
    records = {"graph": prepare_graph, "experiments": prepare_experiments}[args.command](args)
    result = publish(args.output, records)
    print(json.dumps({"status": result["status"], "identity_sha256": result["identity_sha256"], "summary": result.get("summary")}))


if __name__ == "__main__":
    main()
