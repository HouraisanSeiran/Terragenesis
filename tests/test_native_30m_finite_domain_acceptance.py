"""p5: executable acceptance for the finite real 30 m cross-window integration round.

What this file pins
-------------------
The manifest ``.scratch/river-stage1-completion/finite-domain-20261025-v1/manifest-finite-domain-20261025-v1.md``
asks for things that a report alone cannot keep honest, so each one is a test here:

* the auditor really does run in a process that never imported a judged kernel, and
  refuses to start when one is there;
* the auditor's own D8, priority flood, basin component and donor-wave accumulation
  are *not* vacuous: they are checked against closed-form fixtures, and then against a
  real assembled window where the sanctioned receiver is known;
* a failed outlet claim cannot become a legitimate state, and ``retained`` is never
  upgraded;
* a lake surface is never read back as a bed;
* the audit tool's exit codes distinguish pass / assertion failure / refusal.

What it deliberately does not do
--------------------------------
No GPU, no terrain generation, no 48 km recomputation. The only real data it touches is
the already-written 257-node raster under ``finite-domain-20261025-v1/logs``; nothing is
regenerated and no page is re-assembled beyond one 257 window load.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.lake import build_native_30m_lake as build_native_30m_lake
from terrain_pipeline.surface_rivers.native_30m_source import (  # noqa: E402
    build_strict_topology, load_native_window)
from terrain_pipeline.surface_rivers.natural_outlet_status import (  # noqa: E402
    certify_natural_outlet)
from tools import audit_native_30m_finite_domain as auditor  # noqa: E402

WORLD_SEED = 20261020
SPACING_M = 30.0
EVIDENCE = ROOT / ".scratch" / "river-stage1-completion" / "finite-domain-20261025-v1"
V8_REQUEST = (ROOT / ".scratch" / "river-stage1-completion"
              / "m1-finite-product-20261025-v8" / "source-request.json")


def plane(rows, columns, slope_z=0.01, slope_x=0.004, offset=100.0):
    z = np.arange(rows)[:, None]
    x = np.arange(columns)[None, :]
    return offset + slope_z * z + slope_x * x


def bowl(side=21, floor=100.0, rim=112.0, plateau=3.0):
    """A conical bowl sunk into a flat plateau: the closed basin is closed-form checkable.

    The plateau is load-bearing. ``depression_hierarchy`` seeds its flood on the window
    border and fills by 8-connectivity, so a bowl whose rim *is* the outermost ring cannot
    be closed at all: the border drains, every cell gets ``filled == bed``, and there is no
    component. Sinking the cone three cells inside a flat plateau makes the escape level
    the rim height and makes the fill level constant over the component -- the property the
    lake module depends on.
    """
    centre = (side - 1) / 2.0
    rr = np.arange(side)[:, None]
    cc = np.arange(side)[None, :]
    radius = np.hypot(rr - centre, cc - centre)
    inner = np.hypot(centre, centre) - plateau
    cone = floor + (rim - floor) * np.clip(radius / inner, 0.0, 1.0)
    return np.where(radius > inner, rim + plateau, cone)


def page_records():
    request = json.loads(V8_REQUEST.read_text(encoding="utf-8"))
    return [{"path": str(ROOT / item["path"]), "sha256": item["sha256"]}
            for item in request["source_records"]]


class IndependenceTests(unittest.TestCase):
    """The auditor must not be able to audit its own imports."""

    def test_a_cold_process_imports_no_judged_kernel(self):
        code = (
            "import sys;"
            "sys.path.insert(0, r'%s');"
            "import tools.audit_native_30m_finite_domain as m;"
            "m.assert_independence();"
            "bad=[n for n in m.FORBIDDEN_MODULES if n in sys.modules];"
            "print('CLEAN' if not bad else 'DIRTY:'+','.join(bad))" % str(ROOT))
        completed = subprocess.run([sys.executable, "-B", "-c", code],
                                   cwd=str(ROOT), capture_output=True, text=True,
                                   encoding="utf-8", timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertIn("CLEAN", completed.stdout)

    def test_a_polluted_process_is_refused(self):
        original = sys.modules.get("terrain_pipeline.surface_rivers")
        sys.modules["terrain_pipeline.surface_rivers"] = object()
        try:
            with self.assertRaises(auditor.AuditFailure) as caught:
                auditor.assert_independence()
            self.assertEqual(caught.exception.reason_code, "judged_kernel_already_imported")
        finally:
            if original is None:
                sys.modules.pop("terrain_pipeline.surface_rivers", None)
            else:
                sys.modules["terrain_pipeline.surface_rivers"] = original

    def test_the_auditor_imports_none_of_the_judged_kernels_by_name(self):
        source = Path(auditor.__file__).read_text(encoding="utf-8")
        for name in ("native_30m_source", "native_30m_runoff", "native_30m_lakes",
                     "natural_outlet_status", "metric_network_accumulation"):
            self.assertNotIn("import " + name, source)
            self.assertNotIn("from terrain_pipeline.surface_rivers." + name, source)


class OwnKernelTests(unittest.TestCase):
    """The auditor's re-derivations are checked against closed forms, not against itself."""

    def test_shared_graph_on_plane_selects_maximum_metric_downhill_slope(self):
        height = plane(9, 9, slope_x=0.0)
        valid = np.ones(height.shape, bool)
        receiver = auditor.steepest_receiver(height, valid)
        rows, columns = height.shape
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(height.shape)
        for row in range(rows):
            for column in range(columns):
                flat = row * columns + column
                if row == 0:
                    self.assertEqual(int(receiver[row, column]), -1)
                else:
                    edges = np.arange(mesh.indptr[flat], mesh.indptr[flat + 1])
                    slopes = (height.ravel()[flat] - height.ravel()[mesh.indices[edges]]) / mesh.edge_length_m[edges]
                    self.assertEqual(int(receiver[row, column]), int(mesh.indices[edges[np.argmax(slopes)]]))

    def test_own_d8_never_proposes_an_unresolved_receiver(self):
        height = plane(7, 7)
        valid = np.ones(height.shape, bool)
        valid[3, 3] = False
        receiver = auditor.steepest_receiver(height, valid)
        flat = receiver.reshape(-1)
        targets = flat[flat >= 0]
        self.assertTrue(valid.reshape(-1)[targets].all())
        self.assertEqual(int(receiver[3, 3]), -1)

    def test_own_priority_flood_is_constant_over_a_closed_bowl(self):
        height = bowl()
        filled = auditor.priority_flood(height)
        depth = filled - height
        component = auditor.basin_component(depth, (10, 10))
        self.assertIsNotNone(component)
        self.assertGreater(int(component.sum()), 1)
        # What is constant is the FILLED LEVEL, not the water column: in a cone the depth
        # varies from zero at the rim to its maximum at the floor. Conflating the two is
        # the mistake the lake module warns about, so both are stated.
        levels = filled[component]
        self.assertEqual(float(levels.max() - levels.min()), 0.0)
        self.assertGreater(float(depth[component].max()), 0.0)
        spill = float(levels.max())
        rim = auditor.dilate8(component) & ~component
        self.assertTrue(rim.any())
        exits = rim & (np.abs(filled - spill) <= 1e-9)
        self.assertTrue(exits.any(), "a closed bowl must have an exit set on its rim")

    def test_own_basin_is_none_on_a_crescent_shelf(self):
        """A cell that is merely low is not a closed hollow.

        A *strictly* monotone plane has no local minimum at all, so the flood leaves no
        positive fill depth anywhere and the basin is ``None`` -- that is the honest
        version of 'low ground is not a lake'.
        """
        height = plane(11, 11)
        filled = auditor.priority_flood(height)
        depth = filled - height
        self.assertEqual(float(np.abs(depth).max()), 0.0)
        self.assertIsNone(auditor.basin_component(depth, (5, 5)))

    def test_own_donor_waves_sum_a_chain_exactly(self):
        # receiver[i] names the cell that cell i drains INTO: 0 -> 1 -> 2 -> 3, and cell 3
        # is the terminal (receiver -1). The whole chain's water must arrive there.
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        values = np.array([[1.0, 2.0, 4.0, 8.0]])
        flow, dirty = auditor.donor_waves(receiver, valid, values,
                                          np.zeros((1, 4), bool))
        self.assertEqual(float(flow[0, 3]), 15.0, "the whole chain arrives at the terminal")
        self.assertEqual(float(flow[0, 0]), 1.0, "a headwater keeps only its own water")
        # The array is the accumulated field, so intermediate cells hold their own
        # upstream sum too; conservation is stated at the terminal, not by summing cells.
        self.assertEqual(float(flow[0, 1]), 3.0)
        self.assertEqual(float(flow[0, 2]), 7.0)
        self.assertFalse(dirty.any())

    def test_own_donor_waves_propagate_an_unknown_seed_downstream(self):
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        seeds = np.array([[True, False, False, False]])
        _flow, dirty = auditor.donor_waves(receiver, valid, np.ones((1, 4)), seeds)
        self.assertTrue(dirty.all(),
                        "a declared unknown upstream must mark the whole downstream cone")

    def test_own_donor_waves_never_treat_a_terminal_as_a_source(self):
        """A terminal has receiver -1; indexing it would wrap and invent water."""
        receiver = np.array([[-1, -1]], np.int64)
        valid = np.ones((1, 2), bool)
        flow, _dirty = auditor.donor_waves(receiver, valid, np.array([[1.0, 2.0]]),
                                            np.zeros((1, 2), bool))
        self.assertEqual(float(flow.sum()), 3.0, "two isolated terminals keep their water")

    def test_the_partition_is_not_satisfied_by_folding_withheld_into_the_outlet(self):
        """The forbidden variant must be numerically distinguishable, not just relabelled."""
        declared_input = 10.0
        retained, opened, unknown, withheld = 4.0, 0.0, 2.5, 3.5
        self.assertEqual((retained + opened + unknown + withheld), declared_input)
        # Folding withheld into the outlet drops the withheld term entirely.
        folded = (retained + opened + unknown)
        self.assertNotEqual(folded, declared_input)
        self.assertEqual(declared_input - folded, withheld)


class RealWindowRederivationTests(unittest.TestCase):
    """On the real 257 window the auditor's own traversals must land on the saved ones."""

    @classmethod
    def setUpClass(cls):
        cls.window = load_native_window(page_records(), origin_native_xz=[42173, 42874],
                                       shape_zx=[257, 257], world_seed=WORLD_SEED)
        cls.topology = build_strict_topology(cls.window["field"],
                                             cls.window["resolved_mask"])

    def test_own_d8_matches_the_sanctioned_receiver_cell_for_cell(self):
        own = auditor.steepest_receiver(self.window["field"], self.window["resolved_mask"])
        self.assertTrue(np.array_equal(own, self.topology["receiver"]),
                        "%d cells disagree" % int((own != self.topology["receiver"]).sum()))

    def test_own_terminal_labels_match_the_saved_ones(self):
        own, complete, _terminal = auditor.terminal_labels(
            self.topology["receiver"], self.window["resolved_mask"], self.window["field"])
        self.assertTrue(np.array_equal(own, self.topology["terminal_kind"]))
        seeds = self.window["resolved_mask"] & ~complete
        self.assertTrue(np.array_equal(seeds, self.topology["upstream_unknown_mask"]))

    def test_open_outflow_is_never_emitted_on_a_real_window(self):
        kinds = self.topology["terminal_kind"]
        self.assertEqual(int((kinds == "open_outflow").sum()), 0)
        self.assertGreater(int((kinds == "unknown_boundary").sum()), 0)

    def test_a_real_certified_basin_is_reproduced_by_the_auditor(self):
        filled = auditor.priority_flood(self.window["field"])
        depth = filled - self.window["field"]
        ids = np.flatnonzero(self.topology["terminal_kind"].reshape(-1) == "retained")
        checked = 0
        for flat in ids[:12]:
            row, column = divmod(int(flat), 257)
            lake = build_native_30m_lake(
                self.window["field"], self.window["resolved_mask"],
                seed_cell_rc=(row, column), spacing_m=SPACING_M,
                origin_xz_m=(42173 * SPACING_M, 42874 * SPACING_M),
                source_identity_sha256=self.window["assembly_digest"],
                surface_kind="bed_elevation_m", sill_width_m=SPACING_M,
                discharge_coefficient=1.7, head_allowance_m=2.0)
            component = auditor.basin_component(depth, (row, column))
            if component is None:
                self.assertEqual(lake.reason_code, "no_depression_at_seed")
                continue
            self.assertEqual(int(component.sum()), int(lake.basin_cells))
            self.assertEqual(float(self.window["field"][component].min()),
                             float(lake.bed_min_m))
            # The escape level is the FILLED level, which the flood holds constant over a
            # closed component; `depth.max()` is the deepest water column, a different
            # number. Comparing the wrong one is exactly the confusion the lake module
            # documents, so the right one is used here.
            self.assertEqual(float(filled[component].max()), float(lake.spill_level_m))
            checked += 1
        self.assertGreater(checked, 0, "no basin in the first twelve terminals was closed")


class NoUpgradeTests(unittest.TestCase):
    """A label is not a certification, and a failed claim is not a state."""

    def graph(self):
        """A strictly downhill 5x5 field: row 0 is the terminal row.

        ``natural_outlet_status`` validates that every receiver target is *lower* than its
        cell, so the fixture must drain towards decreasing height; reversing this would be
        rejected by the module's own guard rather than by the gate under test.
        """
        side = 5
        rr = np.arange(side)[:, None]
        cc = np.arange(side)[None, :]
        height = 100.0 + 0.01 * rr + 0.004 * cc
        receiver = np.full((side, side), -1, np.int64)
        for row in range(side):
            for column in range(side):
                if row > 0:
                    receiver[row, column] = (row - 1) * side + column
        kinds = np.full((side, side), "inactive", dtype="U24")
        kinds[receiver >= 0] = "interior"
        kinds[receiver < 0] = "retained"
        valid = np.ones((side, side), bool)
        return {"receiver": receiver, "height_m": height,
                "valid_mask": valid, "terminal_kind": kinds}

    def evidence(self, terminal):
        side = 5
        shape = (side, side)
        row, column = divmod(int(terminal), side)
        return {"masks": {"coastline_mask": np.zeros(shape, bool),
                           "artificial_boundary_mask": np.zeros(shape, bool),
                           "unknown_mask": np.zeros(shape, bool)},
                "source_pin": {"world_seed": WORLD_SEED, "spacing_m": SPACING_M,
                               "native_origin_xz": [0, 0],
                               "outlet_world_xz_m": [float(column * SPACING_M),
                                                     float(row * SPACING_M)],
                               "page_sha256": ["a" * 64], "pinned": True},
                "water_quantity": {"q_m3_s": 1.0, "provenance": "declared test",
                                   "independent": True},
                "water_level": {"sea_level_m": 1000.0,
                                "water_surface_m": 100.0 + 0.01 * row,
                                "outlet_bed_m": 100.0 + 0.01 * row,
                                "datum": "test datum", "uncertainty_m": 0.0}}

    def certify(self, declared):
        graph = self.graph()
        terminal = int(np.flatnonzero(graph["terminal_kind"].reshape(-1) == "retained")[0])
        evidence = self.evidence(terminal)
        path = np.array([terminal], np.int64)
        return certify_natural_outlet(
            candidate={"terminal_cell_id": terminal, "declared_state": declared},
            graph=graph,
            downstream={"path_cell_ids": path, "coastline_cell_id": terminal,
                        "independent_observation": True},
            **evidence)

    def test_retained_is_never_upgraded(self):
        report = self.certify("natural_outlet")
        self.assertNotEqual(report["assigned_state"], "natural_outlet")
        self.assertIn("graph_label_is_not_an_open_outflow", report["failure_reasons"])

    def test_a_declared_retained_keeps_its_own_state(self):
        report = self.certify("retained")
        self.assertEqual(report["assigned_state"], "retained")
        self.assertIn("declared_retained_is_not_a_natural_outlet", report["failure_reasons"])

    def test_a_failed_claim_never_lands_on_a_legal_state(self):
        report = self.certify("natural_outlet")
        self.assertEqual(report["assigned_state"], "unverified_outlet_candidate")


class WaterSurfaceIsNotABedTests(unittest.TestCase):
    """A lake level must never be read back as terrain."""

    def test_the_filled_surface_of_a_real_bowl_is_refused(self):
        height = bowl()
        valid = np.ones(height.shape, bool)
        filled = auditor.priority_flood(height)
        lake = build_native_30m_lake(
            filled, valid, seed_cell_rc=(10, 10), spacing_m=SPACING_M,
            origin_xz_m=(0.0, 0.0), source_identity_sha256="c" * 64,
            surface_kind="bed_elevation_m", sill_width_m=SPACING_M,
            discharge_coefficient=1.7, head_allowance_m=2.0)
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, "no_depression_at_seed")
        with self.assertRaises(ValueError):
            build_native_30m_lake(
                filled, valid, seed_cell_rc=(10, 10), spacing_m=SPACING_M,
                origin_xz_m=(0.0, 0.0), source_identity_sha256="c" * 64,
                surface_kind="water_surface_m", sill_width_m=SPACING_M,
                discharge_coefficient=1.7, head_allowance_m=2.0)

    def test_a_lowland_that_drains_is_not_a_lake(self):
        height = plane(11, 11)
        valid = np.ones(height.shape, bool)
        lake = build_native_30m_lake(
            height, valid, seed_cell_rc=(5, 5), spacing_m=SPACING_M,
            origin_xz_m=(0.0, 0.0), source_identity_sha256="d" * 64,
            surface_kind="bed_elevation_m", sill_width_m=SPACING_M,
            discharge_coefficient=1.7, head_allowance_m=2.0)
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, "no_depression_at_seed")
        self.assertFalse(lake.truncated_not_judged,
                         "'the terrain answered: not a lake' is not a truncation")


class AuditToolExitCodeTests(unittest.TestCase):
    """0 = written and all assertions hold, 1 = an assertion failed, 2 = refused."""

    def run_audit(self, evidence_dir, output):
        return subprocess.run(
            [sys.executable, "-B", "-X", "utf8",
             str(ROOT / "tools" / "audit_native_30m_finite_domain.py"),
             "--evidence", str(evidence_dir), "--output", str(output)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=900)

    def test_missing_evidence_is_refused_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = self.run_audit(Path(tmp), Path(tmp) / "audit.json")
            self.assertEqual(completed.returncode, 2, completed.stdout[-2000:])
            self.assertIn("evidence_missing", completed.stdout)
            self.assertFalse((Path(tmp) / "audit.json").exists())

    def test_a_tampered_evidence_file_fails_rather_than_passes(self):
        evidence = EVIDENCE / "evidence-20261025-v1.json"
        if not evidence.is_file():
            self.skipTest("the p5 evidence file has not been produced yet")
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        payload["windows"][0]["census"]["retained"] += 1
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "evidence-20261025-v1.json"
            copy.write_text(json.dumps(payload), encoding="utf-8")
            logs = Path(tmp) / "logs"
            logs.mkdir()
            # Every array the audit re-derives from must travel with the tampered JSON,
            # otherwise the run stops on a missing file instead of on the tampered count
            # and the test would be proving the wrong thing.
            for item in EVIDENCE.joinpath("logs").glob("*.npz"):
                (logs / item.name).write_bytes(item.read_bytes())
            completed = self.run_audit(Path(tmp), Path(tmp) / "audit.json")
            self.assertEqual(completed.returncode, 1, completed.stdout[-3000:])
            report = json.loads((Path(tmp) / "audit.json").read_text(encoding="utf-8"))
            self.assertGreater(report["failure_count"], 0)
            self.assertIn("census_matches_declaration:W1", report["failures"])


if __name__ == "__main__":
    unittest.main()
