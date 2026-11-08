"""Fixed UTC connector evidence; CPU only, independent source sample, no default world."""

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_lake_river_connector import common_source_case, expanded_corridor, mutable
from tests.test_surface_lake_network import high_tailwater_case
from terrain_pipeline.lake import evaluate_surface_lake_network as evaluate_surface_lake_network
from terrain_pipeline.lake import surface_lake_network_hash as surface_lake_network_hash
from terrain_pipeline.lake import evaluate_lake_river_connector as evaluate_lake_river_connector
from terrain_pipeline.lake import lake_river_connector_hash as lake_river_connector_hash
from terrain_pipeline.lake import load_lake_river_connector as load_lake_river_connector
from terrain_pipeline.lake import query_lake_river_connector as query_lake_river_connector
from terrain_pipeline.lake import save_lake_river_connector as save_lake_river_connector
from terrain_pipeline.lake import validate_lake_river_connector as validate_lake_river_connector


def independent_mesh_checks(result):
    rows = []
    for row in result["steps"]:
        geometry = row["geometry"]
        if geometry is None:
            continue
        vertices = geometry["water_vertices_xzw_m"]
        triangles = geometry["triangles"]
        area = 0.
        edges = {}
        for triangle in triangles:
            points = vertices[triangle, :2]
            first, second = points[1] - points[0], points[2] - points[0]
            area += abs(first[0] * second[1] - first[1] * second[0]) / 2
            for begin, end in zip(triangle, np.roll(triangle, -1)):
                edge = tuple(sorted((int(begin), int(end))))
                edges[edge] = edges.get(edge, 0) + 1
        assert max(edges.values()) == 2
        assert abs(area - geometry["audit"]["wet_area_m2"]) < 1e-12
        source = result["source_joint"]["trace"][row["index"]]
        actual = source["recovery"]["surface"]["arrays"]
        assert geometry["station_bed_m"][-1] == actual["final_surface_m"][10, 30]
        assert geometry["station_water_m"][-1] == actual["water_surface_m"][10, 30]
        assert row["actual_outflow_m3_s"] == source["lake_outflow_m3_s"]
        rows.append(dict(step=row["index"], outflow_m3_s=row["actual_outflow_m3_s"],
            vertices=len(vertices), triangles=len(triangles), independently_summed_area_m2=float(area),
            nonmanifold_edges=sum(count > 2 for count in edges.values()),
            cut_volume_m3=geometry["audit"]["cut_volume_m3"],
            changed_area_m2=geometry["audit"]["changed_area_m2"],
            min_depth_m=geometry["audit"]["min_depth_m"],
            max_cut_m=geometry["audit"]["max_cut_m"],
            actual_river_bed_m=geometry["station_bed_m"][-1]))
    return rows


def main():
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = ROOT / "verification" / "lake-river-connector" / ("run-" + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_lake_river_connector")
    test_started = time.perf_counter()
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    test_seconds = time.perf_counter() - test_started
    (directory / "focused-tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    if not tests.wasSuccessful():
        raise RuntimeError("focused tests failed; preserve this incomplete evidence directory")
    records = []

    def retain(name, result, expected):
        assert result["geometry_feasible"] is expected, (name, result["diagnostic"])
        destination = directory / (name + ".npz")
        save_lake_river_connector(result, destination)
        with patch('terrain_pipeline.lake.connector_geometry', side_effect=AssertionError), patch(
                'terrain_pipeline.lake.evaluate_lake_river_connector', side_effect=AssertionError), patch(
                'terrain_pipeline.lake.evaluate_surface_lake_network', side_effect=AssertionError), patch(
                'terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError):
            loaded = load_lake_river_connector(destination)
            query_lake_river_connector(loaded, 0)
        assert loaded["identity_sha256"] == result["identity_sha256"]
        records.append(dict(name=name, bundle=destination.name, geometry_feasible=expected,
            diagnostic=mutable(result["diagnostic"]), identity_sha256=result["identity_sha256"],
            geometry=independent_mesh_checks(result),
            file_sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))

    joint, corridor, recipe = common_source_case()
    first = evaluate_lake_river_connector(joint, corridor, recipe)
    retain("common-source-positive-changing-q", first, True)
    retain("common-source-positive-lower-q", evaluate_lake_river_connector(*common_source_case((1., 1.))), True)
    retain("zero-q-closed", evaluate_lake_river_connector(*common_source_case((0., 0.), initial_stage=8., original_local=0.)), True)
    negatives = []
    height = corridor.surface_m.copy()
    height[4:8, 68:72] = 12.
    negatives.append(("shore-ridge", replace(corridor, surface_m=height), recipe))
    for name, field, value in (("unknown", "valid_mask", False), ("protected", "protected_mask", True),
                               ("domain", "domain_mask", False)):
        mask = getattr(corridor, field).copy()
        mask[6, 75] = value
        negatives.append((name, replace(corridor, **{field: mask}), recipe))
    for name, changes in (("width-resolution", dict(width_m=(.02,) * 3)),
                          ("longitudinal-resolution", dict(max_station_spacing_m=.1)),
                          ("cut-depth", dict(max_cut_m=.01)), ("cut-volume", dict(max_cut_volume_m3=0.)),
                          ("changed-area", dict(max_changed_area_m2=0.)), ("station-resource", dict(max_stations=3)),
                          ("triangle-resource", dict(max_triangles=2)), ("support-resource", dict(max_support_tests=1))):
        negatives.append((name, corridor, replace(recipe, **changes)))
    negatives.append(("dry-full-width-splice", expanded_corridor(joint), replace(recipe, width_m=(.4,) * 3)))
    for name, terrain, bounded_recipe in negatives:
        retain(name, evaluate_lake_river_connector(joint, terrain, bounded_recipe), False)

    rejections = []
    for field in ("geometry", "summary", "q", "source-h0", "tolerance"):
        altered = mutable(first)
        if field == "geometry":
            altered["steps"][0]["geometry"]["bed_vertices_m"][5] -= .01
        elif field == "summary":
            altered["summary"]["connected_steps"] = 99
        elif field == "q":
            altered["steps"][0]["actual_outflow_m3_s"] += .1
        else:
            source = altered["source_joint"]
            if field == "source-h0":
                source["inputs"]["plan"]["arrays"]["source_height_m"][0, 0] += .1
            else:
                source["ledger"][0]["combined_tolerance_m3"] = 100.
            source["identity_sha256"] = surface_lake_network_hash(source)
        altered["identity_sha256"] = lake_river_connector_hash(altered)
        try:
            validate_lake_river_connector(altered)
        except ValueError as error:
            rejections.append(dict(name="rehashed-" + field, reason=str(error)))
        else:
            raise AssertionError("rehashed semantic tamper accepted: " + field)
    failed_source = evaluate_surface_lake_network(**high_tailwater_case())
    try:
        evaluate_lake_river_connector(failed_source, corridor, recipe)
    except ValueError as error:
        rejections.append(dict(name="high-tailwater-source", source_diagnostic=failed_source["diagnostic"], reason=str(error)))
    else:
        raise AssertionError("high tailwater source accepted")
    for name, invalid_recipe in (("illegal-spill", replace(recipe, path_xz_m=((-2.2, 1.), (-1.1, 1.), (0., 1.)))),
                                  ("retained-resource", replace(recipe, max_retained_bytes=1024))):
        try:
            evaluate_lake_river_connector(joint, corridor, invalid_recipe)
        except ValueError as error:
            rejections.append(dict(name=name, reason=str(error)))
        else:
            raise AssertionError("invalid input accepted")
    report = dict(utc=stamp, directory=str(directory), focused_tests=tests.testsRun,
        focused_seconds=test_seconds, bundles=len(records), positive_flow_bundles=2, closed_bundles=1,
        diagnostic_bundles=sum(not record["geometry_feasible"] for record in records),
        rehashed_and_input_rejections=rejections, cases=records,
        files_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            ROOT / 'terrain_pipeline/lake.py', ROOT / "tests/test_lake_river_connector.py",
            ROOT / "tools/verify_lake_river_connector.py", ROOT / "docs/lake-river-connector-v1.md")},
        limitations=["Engineering synthetic common-source sample, not natural-domain certification",
            "No free-fall/drop solver or dynamic/backwater validation", "Source joint remains diagnostic_not_publishable",
            "Default load audits saved source and geometry without preparation; explicit replay is opt-in",
            "External official documentation was not verified and is not cited"], elapsed_seconds=time.perf_counter() - started)
    (directory / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(dict(directory=str(directory), focused_tests=tests.testsRun, bundles=len(records),
                          diagnostic_bundles=report["diagnostic_bundles"], elapsed_seconds=report["elapsed_seconds"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
