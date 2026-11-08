"""`tools/publish_domain_bundle.py`: the explicitly invoked default consumer's contracts.

The role identifies the user-designated default entry point; it does not certify the
underlying terrain, hydraulics, natural outlet or publishability. Publication remains
explicit, cold-readable and non-overwriting.
"""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import publish_domain_bundle as publisher  # noqa: E402
from tools.publish_domain_bundle import BUNDLE_SCHEMA, run  # noqa: E402
from terrain_pipeline.common_infra import identity

SEED = 20261020
# Three current core members, resolved without any same-domain margin land.
POINTS = ((170000.0, 10000.0),)


def _publish(out, points=POINTS, intervals=2):
    argv = ["--legacy-coarse", "--seed", str(SEED), "--output-dir", str(out),
            "--rain-mm-h", "4", "--dt-s", "3600", "--intervals", str(intervals)]
    for x, z in points:
        argv.extend(["--point", str(x), str(z)])
    return run(argv)


class PublishBundleTests(unittest.TestCase):
    def temp_dir(self, name):
        root = Path(tempfile.mkdtemp(prefix="bundle-%s-" % name))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_a_bundle_publishes_and_every_check_passes(self):
        out = self.temp_dir("publish")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(index["schema"], BUNDLE_SCHEMA)
        self.assertTrue(index["passed"])
        self.assertEqual(index["check_count"], index["passed_count"])
        self.assertEqual(index["tile_count"], 1)
        self.assertGreaterEqual(index["domain_products"]["domain_count"], 1)

    def test_the_index_names_every_published_file(self):
        out = self.temp_dir("names")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        tile = index["tiles"][0]
        for kind in ("flow", "sediment", "coupled", "bed_feedback"):
            record = tile["ledgers"][kind]
            path = out / tile["directory"] / record["file"]
            self.assertTrue(path.exists(), kind)
            self.assertEqual(len(record["sha256"]), 64, kind)
            self.assertEqual(len(record["identity_sha256"]), 64, kind)
            self.assertTrue(record["schema"], kind)
            self.assertEqual(int(record["interval_count"]), 2, kind)

    def test_published_products_keep_their_distinct_readiness_contracts(self):
        out = self.temp_dir("claims")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        for tile in index["tiles"]:
            for kind, record in tile["ledgers"].items():
                self.assertTrue(record["claims"], kind)
                self.assertTrue(publisher._claims_are_safe(kind, {"metadata": record}), kind)
                if kind == "bed_feedback":
                    self.assertTrue(record["claims"]["terrain_feedback_applied"])
                    self.assertTrue(record["revalidation"][
                        "needs_geometry_and_hydraulic_revalidation"])
                    self.assertIs(record["revalidation"]["bed_rejection_applied"], False)
                else:
                    self.assertTrue(all(value is False
                                        for value in record["claims"].values()), kind)

    def test_the_bundle_declares_itself_the_unvalidated_default_consumer(self):
        out = self.temp_dir("role")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(index["role"], "production_default_consumer_unvalidated")
        self.assertTrue(index["passed"])
        joined = " ".join(index["limitations"])
        self.assertIn("default consumer entry point", joined)
        self.assertIn("not an automatic infinite-world scheduler", joined)
        self.assertIn("does not certify terrain or hydrology", joined)
        self.assertIn("per TILE", joined)
        self.assertIn("publishable", joined)
        self.assertIn("uniform-within-domain", joined)
        self.assertIn("RAW base face", joined)
        self.assertIn("does not rerun hydraulics", joined)
        coverage = index["tiles"][0]["closure_gate_coverage"]
        self.assertEqual(coverage["scope"], "point_selected_domains_only")
        self.assertGreaterEqual(coverage["selected_domains_checked"], 1)
        self.assertEqual(coverage["unselected_domains_in_ledgers_unchecked"],
                         index["tiles"][0]["domain_count"] - coverage["selected_domains_checked"])
        self.assertIs(coverage["whole_tile_certified"], False)
        self.assertIn("only point-selected domains were checked", joined)
        self.assertIn("unselected domains", joined)
        self.assertIn("phase completion is not certified", joined)
        for tile in index["tiles"]:
            for kind, record in tile["ledgers"].items():
                claims = record["claims"]
                self.assertIs(claims["hydraulic_ready"], False, kind)
                self.assertIs(claims["natural_outlet_verified"], False, kind)
                self.assertIs(claims["publishable"], False, kind)

    def test_an_existing_bundle_is_never_overwritten(self):
        out = self.temp_dir("overwrite")
        self.assertEqual(_publish(out), 0)
        before = (out / "bundle.json").read_text(encoding="utf-8")
        self.assertEqual(_publish(out), 2)
        self.assertEqual((out / "bundle.json").read_text(encoding="utf-8"), before)

    def test_two_tiles_are_published_separately(self):
        out = self.temp_dir("multitile")
        far = 12_800_000.0  # five core spans away: a different world-anchored tile
        self.assertEqual(_publish(out, ((0.0, 30000.0), (far, far))), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(index["tile_count"], 2)
        directories = {tile["directory"] for tile in index["tiles"]}
        self.assertEqual(len(directories), 2)
        for tile in index["tiles"]:
            self.assertEqual(set(tile["ledgers"]),
                             {"flow", "sediment", "coupled", "bed_feedback"})

    def test_the_tile_directory_is_keyed_by_the_tile_index(self):
        out = self.temp_dir("keyed")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        tile = index["tiles"][0]
        self.assertIn("tiles/tile_", tile["directory"])
        self.assertNotIn("\\", tile["directory"])

    def test_the_index_repeats_the_run_parameters(self):
        out = self.temp_dir("params")
        self.assertEqual(_publish(out, intervals=3), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(index["seed"], SEED)
        self.assertEqual(index["intervals"], 3)
        self.assertEqual(index["rain_mm_h"], 4.0)
        self.assertEqual(len(index["config_id"]), 64)
        self.assertEqual(index["requested_points"], len(POINTS))

    def test_flow_and_coupled_share_the_exact_runoff_parameters(self):
        out = self.temp_dir("unified-runoff")
        with patch.object(publisher, "solve_domain_flow",
                          wraps=publisher.solve_domain_flow) as flow, \
                patch.object(publisher, "solve_domain_coupled",
                             wraps=publisher.solve_domain_coupled) as coupled:
            self.assertEqual(_publish(out), 0)
        runoff = flow.call_args.kwargs["parameters"]
        self.assertIs(runoff, coupled.call_args.kwargs["parameters"].runoff)
        self.assertEqual(runoff.infiltration_capacity_mm_h, 2.0)
        self.assertEqual(asdict(runoff), asdict(publisher.CoupledParameters().runoff))
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(index["runoff_parameters"], asdict(runoff))
        tile = index["tiles"][0]
        flow_record = tile["ledgers"]["flow"]
        cold = publisher.load_domain_flow(out / tile["directory"] / flow_record["file"],
                                         expected_sha256=flow_record["sha256"],
                                         expected_identity=flow_record["identity_sha256"])
        self.assertEqual(cold["metadata"]["parameters"], asdict(runoff))

    def test_bed_feedback_cold_load_identity_and_parent_binding(self):
        out = self.temp_dir("bed-cold")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        loaders = {"flow": publisher.load_domain_flow,
                   "sediment": publisher.load_domain_sediment,
                   "coupled": publisher.load_domain_coupled,
                   "bed_feedback": publisher.load_domain_bed_feedback}
        for tile in index["tiles"]:
            for kind, loader in loaders.items():
                record = tile["ledgers"][kind]
                path = out / tile["directory"] / record["file"]
                cold = loader(path, expected_sha256=record["sha256"],
                              expected_identity=record["identity_sha256"])
                self.assertEqual(cold["identity_sha256"], record["identity_sha256"])
                self.assertTrue(publisher._claims_are_safe(kind, cold))
                if kind != "bed_feedback":
                    continue
                self.assertEqual(record["file"], "bed_feedback.npz")
                self.assertEqual(record["schema"], "river-domain-bed-feedback-v1")
                self.assertEqual(record["parent_identity_sha256"],
                                 tile["ledgers"]["coupled"]["identity_sha256"])
                for key in ("parent_identity_sha256", "placement_rule", "revalidation"):
                    self.assertEqual(cold["metadata"][key], record[key])
                self.assertEqual(record["placement_rule"],
                                 "uniform_within_domain_over_published_cells")
                self.assertEqual(record["status"], "derived_bed_candidate_requires_revalidation")
                with self.assertRaises(ValueError):
                    loader(path, expected_sha256="0" * 64)
                with self.assertRaises(ValueError):
                    loader(path, expected_sha256=record["sha256"],
                           expected_identity="0" * 64)

    def test_missing_or_tampered_bed_file_refuses_publication(self):
        original_loader = publisher.load_domain_flow
        for action in ("missing", "tampered"):
            with self.subTest(action=action):
                out = self.temp_dir(action)

                def damage_bed(path, **kwargs):
                    bed_path = Path(path).with_name("bed_feedback.npz")
                    if action == "missing":
                        bed_path.unlink()
                    else:
                        with bed_path.open("ab") as stream:
                            stream.write(b"tampered after index sha capture")
                    return original_loader(path, **kwargs)

                with patch.object(publisher, "load_domain_flow", side_effect=damage_bed):
                    self.assertEqual(_publish(out), 1)
                index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
                self.assertFalse(index["passed"])
                self.assertTrue(any(not check["passed"] for check in index["checks"]))

    def test_reidentified_bed_with_wrong_parent_is_refused(self):
        out = self.temp_dir("wrong-parent")
        original = publisher.solve_domain_bed_feedback

        def wrong_parent(parent):
            record = copy.deepcopy(original(parent))
            record["metadata"]["parent_identity_sha256"] = "0" * 64
            record["identity_sha256"] = identity(record["arrays"], record["metadata"])
            return record

        with patch.object(publisher, "solve_domain_bed_feedback", side_effect=wrong_parent):
            self.assertEqual(_publish(out), 1)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertFalse(index["passed"])
        bindings = [check for check in index["checks"]
                    if check["check"] == "bed_feedback_parent_binding"]
        self.assertTrue(bindings)
        self.assertFalse(bindings[0]["passed"])

    def test_bed_readiness_contract_rejects_unsafe_flags(self):
        metadata = {
            "claims": {"terrain_feedback_applied": True, "hydraulic_ready": False,
                       "natural_outlet_verified": False, "publishable": False},
            "revalidation": {"needs_geometry_and_hydraulic_revalidation": True,
                             "bed_rejection_applied": False},
        }
        for section, key, value in (
                ("claims", "hydraulic_ready", True),
                ("claims", "natural_outlet_verified", True),
                ("claims", "publishable", True),
                ("claims", "terrain_feedback_applied", False),
                ("revalidation", "needs_geometry_and_hydraulic_revalidation", False),
                ("revalidation", "bed_rejection_applied", True)):
            with self.subTest(key=key):
                unsafe = copy.deepcopy(metadata)
                unsafe[section][key] = value
                self.assertFalse(publisher._claims_are_safe("bed_feedback", {"metadata": unsafe}))
        self.assertFalse(publisher._claims_are_safe("flow", {"metadata": metadata}))
        self.assertTrue(publisher._claims_are_safe("bed_feedback", {"metadata": metadata}))

    def test_closed_gate_accepts_core_plus_margin_closed_domain(self):
        out = self.temp_dir("closed-margin")
        self.assertEqual(_publish(out, ((40000, 0),)), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        self.assertTrue(index["closed_domain_gate"]["passed"])

    def test_closed_gate_rejects_before_any_product_or_ledger_write(self):
        out = self.temp_dir("closed-gate")
        sentinel = out / "existing.txt"
        sentinel.write_text("keep", encoding="utf-8")
        before = sorted(path.name for path in out.iterdir())
        with patch.object(publisher, "check_domain_closed", return_value={"passed": False}):
            with patch.object(publisher, "resolve_domain_products") as products, \
                    patch.object(publisher, "solve_domain_flow") as flow, \
                    patch.object(publisher, "save_domain_flow") as save:
                self.assertEqual(_publish(out, ((170000, 10000),)), 2)
        products.assert_not_called()
        flow.assert_not_called()
        save.assert_not_called()
        self.assertEqual(sorted(path.name for path in out.iterdir()), before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


    def test_closed_gate_refusal_does_not_create_output_directory(self):
        out = self.temp_dir("closed-absent") / "absent"
        with patch.object(publisher, "check_domain_closed", return_value={"passed": False}):
            self.assertEqual(_publish(out, ((170000, 10000),)), 2)
        self.assertFalse(out.exists())

    def test_closed_gate_audit_is_in_successful_bundle(self):
        out = self.temp_dir("closed-audit")
        self.assertEqual(_publish(out), 0)
        index = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
        gate = index["closed_domain_gate"]
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["accepted_points"], 1)
        self.assertEqual(gate["accepted_domains"], 1)
        self.assertEqual(gate["refused_domains"], 0)
        self.assertEqual(gate["domains"][0]["core_members"], 3)

    def test_invalid_input_is_refused(self):
        out = self.temp_dir("bad")
        self.assertEqual(run(["--legacy-coarse", "--seed", str(SEED), "--point", "1",
                              "--output-dir", str(out)]), 2)
        self.assertEqual(run(["--legacy-coarse", "--seed", str(SEED), "--point", "a", "b",
                              "--output-dir", str(out)]), 2)
        self.assertEqual(run(["--legacy-coarse", "--seed", str(SEED), "--point", "0", "0",
                              "--rain-mm-h", "-1", "--output-dir", str(out)]), 2)
        self.assertEqual(run(["--legacy-coarse", "--seed", str(SEED), "--point", "0", "0",
                              "--intervals", "0", "--output-dir", str(out)]), 2)

    # ---- the closure lattice takes no scale knob --------------------------

    def test_the_closure_lattice_takes_no_scale_knob(self):
        """The closure lattice is a 7680 m CONDITIONING grid, not the terrain grid.

        Forcing its node spacing to 30 m was measured to refuse 100% of cells: the
        drainage margin is DEFAULT_MARGIN_NODES = 48 NODES, i.e. 1.44 km at 30 m
        instead of the 480 km it means at 10 km. A 30 m census therefore belongs on
        the native-page mechanism in `metric_cross_region`, and this entry point
        must not grow a scale knob that pretends otherwise.
        """
        out = self.temp_dir("no-scale-knob")
        common = ["--seed", str(SEED), "--point", "170000", "10000",
                  "--output-dir", str(out)]
        # argparse itself rejects the removed flags: an unknown option is a usage
        # error, which surfaces as SystemExit(2) rather than a silent default.
        with self.assertRaises(SystemExit) as caught:
            run(common + ["--macro-span-m", "1920", "--samples-per-span", "64"])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse((out / "bundle.json").exists())


if __name__ == "__main__":
    unittest.main()
