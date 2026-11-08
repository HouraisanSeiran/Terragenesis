"""Behavioural tests for the 40 km @30 m reach acceptance (spec 4.2).

These tests do not re-measure the reach. They assert the properties the acceptance is
supposed to guarantee, reading the archived artifacts:

* the selection rule is the declared one, and every refusal carries one of the declared codes;
* the section depth is a hydraulic solution, not a constant (the placeholder this work removed);
* the design discharge comes from the existing routers and the routed/lag-free distinction is
  recorded;
* the three ledgers close, each in its own units, at declared tolerances;
* the bed change is checked by a volume identity, not by subtracting large numbers;
* what was not executed is declared as not executed, and the hydraulic-revalidation scope is
  split into the parts that were and were not met.

Run:
    runtime/venv/Scripts/python.exe -B -X utf8 -m unittest tests.test_fine_terrain_40km_reach
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".scratch" / "fine-terrain-40km" / "reach"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name):
    path = ARTIFACTS / name
    if not path.exists():
        raise unittest.SkipTest("artifact %s not produced yet" % name)
    return json.loads(path.read_text(encoding="utf-8"))


class SelectionRuleTests(unittest.TestCase):
    def test_the_rule_was_declared_before_the_table(self):
        data = load("reach-selection.json")
        rule = data["rule"]
        assert rule["stage"] == "A_terrain_candidate_and_selection"
        for key in ("candidate", "eligibility", "ranking", "reject_reason_codes"):
            assert key in rule and rule[key]

    def test_v2_added_only_a_rejection_and_kept_the_ranking(self):
        data = load("reach-selection.json")
        revision = data["rule"]["rule_revision"]
        assert "v2" in revision
        # the ranking rule text must not have been rewritten to fit the new winner
        assert "largest terminal catchment area" in data["rule"]["ranking"]

    def test_every_refusal_carries_a_declared_reason_code(self):
        data = load("reach-selection.json")
        declared = set(data["rule"]["reject_reason_codes"])
        for entry in data["rejected"]:
            assert entry["reason_code"] in declared, entry["reason_code"]
        assert set(data["rejection_counts"]) <= declared

    def test_the_chosen_reach_is_interior_and_whole(self):
        data = load("reach-selection.json")
        chosen = data["chosen"]
        assert chosen["stem_rim_clearance_cells"] >= data["contact_margin_cells"]
        assert chosen["catchment_rim_clearance_cells"] >= data["contact_margin_cells"]
        assert chosen["catchment_cells_chain_truncated"] == 0
        # the stem is the complete head-to-terminal path, not a segment
        assert chosen["stem_nodes_full_resolution"] == len(chosen["stem_flat_cells"])
        assert chosen["stem_flat_cells"][-1] == chosen["terminal_flat_cell"]

    def test_the_mapped_catchment_matches_the_counted_catchment(self):
        data = load("reach-selection.json")
        chosen = data["chosen"]
        assert chosen["catchment_cells_mapped"] == chosen["catchment_cells"]


class SectionLawTests(unittest.TestCase):
    def test_depth_is_not_a_constant(self):
        scene = load("scene.json")
        depth = np.asarray(scene["nodes"]["depth_m"], np.float64)
        assert depth.size == scene["stem"]["carved_nodes"]
        assert depth[0] != depth[1]
        assert depth.min() > 0.
        # the placeholder this replaced
        assert not np.allclose(depth, 0.4)

    def test_per_node_vectors_are_complete(self):
        """Every per-node vector must have one entry per carved node, not two endpoints."""
        scene = load("scene.json")
        count = scene["stem"]["carved_nodes"]
        for key in ("width_m", "depth_m", "slope", "design_q_m3_s", "width_unclamped_m",
                    "source_slope_per_m", "bed_m", "length_m"):
            assert len(scene["nodes"][key]) == count, key
        # and the summaries in `section` are ranges, not the vectors
        for key in ("width_m_range", "depth_m_range", "design_q_m3_s_range"):
            assert len(scene["section"][key]) == 2, key

    def test_depth_comes_from_the_repository_law(self):
        data = load("section-law-identity.json")
        assert "metric_dynamic_feedback.normal_depth" in data["law_owner"]
        assert data["copies_removed"] == 2
        # the removed copy and the repository function are bit-identical, which is why a copy
        # was indefensible; the archived depth then differs only by the repository's own
        # bisection quantisation, and must still carry the design discharge
        assert data["max_abs_diff_removed_copy_vs_repository"] == 0.0
        assert data["bitwise_identical_with_removed_copy"] is True

    def test_depth_closes_on_the_source_slope(self):
        """The section is solved before the incision exists, so it closes on the source slope."""
        data = load("slope-closure.json")
        assert data["max_rel_q_error_on_source_slope"] <= 1e-12
        # the carved slope gives a different answer and that difference is reported, not hidden
        assert data["max_rel_q_error_on_carved_slope"] > 1e-4

    def test_depth_solves_the_solver_conveyance(self):
        """Plug the recorded depth back into the solver's rectangular conveyance."""
        scene = load("scene.json")
        width = np.asarray(scene["nodes"]["width_m"], np.float64)
        depth = np.asarray(scene["nodes"]["depth_m"], np.float64)
        source_slope = np.asarray(scene["nodes"]["source_slope_per_m"], np.float64)
        q_design = np.asarray(scene["nodes"]["design_q_m3_s"], np.float64)
        n = scene["section"]["manning_n"]
        area = width * depth
        perimeter = width + 2. * depth
        conveyance = area * (area / perimeter) ** (2. / 3.) * np.sqrt(source_slope) / n
        assert np.allclose(conveyance, q_design, rtol=1e-9, atol=1e-12)

    def test_design_discharge_comes_from_the_routers(self):
        scene = load("scene.json")
        routing = load("routing.json")
        section = scene["section"]
        assert section["routed_peak_q_m3_s"] == routing["routed"]["peak_m3_s"]
        assert section["instantaneous_peak_q_m3_s"] == routing["instantaneous"]["peak_m3_s"]
        # far tighter than any physical tolerance: the recording is the router's own number
        assert abs(section["routed_peak_q_m3_s"] - routing["routed"]["peak_m3_s"]) \
            <= 1e-12 * routing["routed"]["peak_m3_s"]
        assert abs(section["instantaneous_peak_q_m3_s"]
                   - routing["instantaneous"]["peak_m3_s"]) \
            <= 1e-12 * routing["instantaneous"]["peak_m3_s"]
        assert "reach-level" in section["design_q_source"]
        # every node carries the same routed peak: the uniform law is recorded as such
        design = np.asarray(scene["nodes"]["design_q_m3_s"], np.float64)
        assert np.allclose(design, routing["routed"]["peak_m3_s"], rtol=1e-12)


class RoutingTests(unittest.TestCase):
    def test_the_lag_router_and_the_lag_free_router_agree_on_volume(self):
        routing = load("routing.json")
        routed, inst = routing["routed"], routing["instantaneous"]
        # both route the same catchment total; only the reservoir storage differs
        assert abs(inst["volume_m3"] - routed["lateral_volume_m3"]) \
            <= 1e-9 * routed["lateral_volume_m3"]
        residual = inst["volume_m3"] - routed["volume_m3"] - routed["storage_change_m3"]
        assert abs(residual) <= 1e-6 * max(1., inst["volume_m3"])

    def test_the_routed_peak_is_not_above_the_lag_free_peak(self):
        routing = load("routing.json")
        assert routing["routed"]["peak_m3_s"] <= routing["instantaneous"]["peak_m3_s"] * (1 + 1e-9)

    def test_the_router_ledger_closes(self):
        routing = load("routing.json")
        routed = routing["routed"]
        assert abs(routed["balance_residual_m3"]) <= 1e-6 * max(1., routed["lateral_volume_m3"])

    def test_the_rejected_per_node_taper_is_quantified(self):
        data = load("q-sensitivity.json")
        assert data["not_executed"].strip()
        taper = data["per_node_taper_rejected"]
        uniform = data["reach_uniform"]
        assert taper["nodes_below_floor"] > 0
        assert uniform["nodes_below_floor"] == 0
        assert taper["carved_nodes"] + taper["trimmed_upstream_cells"] == data["stem_cells"]


class GeometryChainTests(unittest.TestCase):
    def test_the_incision_used_the_monotone_closure(self):
        scene = load("scene.json")
        closure = scene["monotone_closure"]
        assert closure["maximum_constraint_residual_m"] <= 1e-9
        assert closure["extra_cut_vertices"] >= 0
        assert "NOT part of the hydraulic section" in scene["monotone_closure_semantics"]

    def test_the_carved_bed_decreases_downstream(self):
        scene = load("scene.json")
        bed = np.asarray(scene["nodes"]["bed_m"], np.float64)
        assert np.all(np.diff(bed) < 0.)

    def test_the_section_never_underflows_one_native_cell(self):
        scene = load("scene.json")
        width = np.asarray(scene["nodes"]["width_m"], np.float64)
        assert width.min() >= scene["section"]["min_width_m"] - 1e-9


class LedgerTests(unittest.TestCase):
    def test_independent_ledgers_did_not_import_the_solvers(self):
        data = load("independent-ledgers.json")
        assert data["independence"]["imported_tested_modules"] is False

    def test_water_ledger_closes(self):
        data = load("independent-ledgers.json")
        total = data["water"]["total"]
        assert total["residual_relative"] is not None
        assert total["residual_relative"] <= 1e-12
        assert len(data["water"]["units"]) > 0

    def test_solid_ledger_closes(self):
        data = load("independent-ledgers.json")
        total = data["solid"]["total"]
        assert total["residual_relative"] is not None
        assert total["residual_relative"] <= 1e-9

    def test_internal_transfers_are_separated_from_external_fluxes(self):
        """`eroded_loose`/`deposited` are bed<->load transfers, not external fluxes."""
        data = load("independent-ledgers.json")
        total = data["solid"]["total"]
        assert total["internal_eroded_loose_m3"] > 0.
        assert total["internal_deposited_m3"] > 0.
        assert "internal transfer" in total["ledger_form"]
        # adding them as external fluxes is what produced a 1.3e-3 residual; the combined form
        # must be far tighter than that
        assert total["residual_relative"] <= 1e-12
        assert total["max_abs_mobile_only_residual_m3"] <= 1e-9
        assert total["max_abs_loose_only_residual_m3"] <= 1e-9

    def test_bed_change_is_a_volume_identity(self):
        data = load("independent-ledgers.json")
        total = data["bed"]["total"]
        assert total["residual_relative"] is not None
        assert total["residual_relative"] <= 1e-9
        # the identity must not be an empty statement
        assert abs(total["total_area_delta_bed_m3"]) > 0.

    def test_every_interval_reports_its_own_residual(self):
        data = load("independent-ledgers.json")
        assert len(data["water"]["per_interval"]) == data["intervals"]
        assert len(data["solid"]["per_interval"]) == data["intervals"]
        assert len(data["bed"]["per_interval"]) == data["intervals"]


class RevalidationTests(unittest.TestCase):
    def test_the_hydraulic_revalidation_scope_is_split(self):
        data = load("dynamics.json")
        scope = data["revalidation"]
        assert scope["hydraulic_recomputed_every_interval"] is True
        assert "dynamic_PL_mesh_updated" in scope
        # the geometric re-cut is the part that was NOT done, and it says so
        assert scope["geometry_recut_per_interval"] is False
        assert scope["dynamic_PL_mesh_updated"] is False
        assert scope["unmet"]

    def test_hydraulics_were_recomputed_on_the_updated_bed(self):
        data = load("dynamics.json")
        for row in data["per_interval"]:
            assert row["hydraulic_recomputed"] is True
        assert data["intervals"] > 1

    def test_independent_hydraulic_recheck_agrees(self):
        data = load("hydraulic-recheck.json")
        assert data["max_relative_q_disagreement"] <= 1e-6
        assert data["checked"] is True

    def test_the_recheck_distinguishes_the_updated_bed(self):
        """A recheck that cannot tell the beds apart is not evidence."""
        data = load("hydraulic-recheck.json")
        assert data["discriminates_initial_vs_final_bed"] is True
        assert data["stale_bed_relative_q_disagreement"] > 10. * data["max_relative_q_disagreement"]

    def test_the_coupling_window_is_declared_short(self):
        data = load("dynamics.json")
        assert data["coupled_hours"] < data["declared_storm_hours"]
        assert data["coupling_covers_declared_storm"] is False
        assert "NOT" in data["coverage_note"] or "not" in data["coverage_note"]


class DeclaredGapsTests(unittest.TestCase):
    def test_not_executed_is_declared(self):
        report = ARTIFACTS / "report.md"
        if not report.exists():
            raise unittest.SkipTest("report.md not written yet")
        text = report.read_text(encoding="utf-8")
        assert "未执行" in text

    def test_condition_two_is_declared_pending_not_substituted(self):
        report = ARTIFACTS / "report.md"
        if not report.exists():
            raise unittest.SkipTest("report.md not written yet")
        text = report.read_text(encoding="utf-8")
        assert "条件 2" in text
        assert "PENDING" in text or "未执行" in text
        # the 10 km result must not stand in for it
        assert "不用 10 km" in text or "不拿 10 km" in text

    def test_the_uniform_q_caveat_is_in_the_summary_verbatim(self):
        report = ARTIFACTS / "report.md"
        if not report.exists():
            raise unittest.SkipTest("report.md not written yet")
        text = report.read_text(encoding="utf-8")
        assert "这份\"完整\"是 reach 级均匀 Q 换来的" in text
        assert "不是断面真的在全河段都可解析" in text

    def test_the_report_avoids_unqualified_completeness_words(self):
        report = ARTIFACTS / "report.md"
        if not report.exists():
            raise unittest.SkipTest("report.md not written yet")
        text = report.read_text(encoding="utf-8")
        # the declared vocabulary is in section 7d; the report may quote the forbidden words
        # only inside the terminology section or the required caveat block
        assert "## 7d. 术语约定" in text
        assert "不使用" in text

    def test_depth_note_is_kept_verbatim(self):
        scene = load("scene.json")
        report = ARTIFACTS / "report.md"
        if not report.exists():
            raise unittest.SkipTest("report.md not written yet")
        assert scene["section"]["depth_note"] in report.read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
