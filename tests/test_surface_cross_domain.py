import json
import tempfile
import unittest
from pathlib import Path

from terrain_pipeline.surface_cross_domain import adapt_saved_mosaics, audit_cross_domain, save_cross_domain_report


def domain(water=3.0, *, reverse=False, unknown=False, protected=False):
    nodes = [
        {"local_id": 0, "x_m": 0.0, "z_m": 0.0, "h0_m": 10.0, "unknown": unknown, "protected": protected, "water_surface_m": water},
        {"local_id": 1, "x_m": 1.0, "z_m": 0.0, "h0_m": 9.0, "unknown": False, "protected": False, "water_surface_m": water},
        {"local_id": 2, "x_m": 1.0, "z_m": 1.0, "h0_m": 8.0, "unknown": False, "protected": False, "water_surface_m": water},
    ]
    edges = [{"local_id": 0, "start": 0, "end": 1, "flux_m3_s": -.25 if reverse else .25, "boundary": True},
             {"local_id": 1, "start": 1, "end": 2, "flux_m3_s": .1 if reverse else -.1, "boundary": True}]
    return {"domain_id": "B" if reverse else "A", "grid": {"origin_x_m": 0., "origin_z_m": 0., "spacing_x_m": 1., "spacing_z_m": 1., "lod": 0}, "nodes": nodes, "edges": edges}


class SurfaceCrossDomainTests(unittest.TestCase):
    def test_saved_domain_mosaic_fixture_is_adapted_readonly_without_edge_fabrication(self):
        from terrain_pipeline.surface_domain_mosaic import load_domain_mosaic
        path = Path(__file__).resolve().parents[1] / "verification/surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz"
        if not path.exists():
            self.skipTest("saved domain mosaic fixture not available")
        mosaic = load_domain_mosaic(path)
        report = adapt_saved_mosaics([{"domain_id": "saved-domain", "mosaic": mosaic}])
        self.assertEqual(report["adapter"]["prepare_called"], False)
        self.assertEqual(report["adapter"]["routing_called"], False)
        self.assertFalse(report["flags"]["edge_evidence_complete"])
        self.assertFalse(report["flags"]["water_generated"])
        self.assertEqual(len(report["adapter"]["diagnostics"]), 2)

    def test_saved_fine_mosaic_fixture_is_adapted_without_water_reconstruction(self):
        from terrain_pipeline.surface_fine_mosaic import load_fine_mosaic
        path = Path(__file__).resolve().parents[1] / "verification/surface-fine-mosaic/run-20260930T123659.258177Z/wet-cross-precision.npz"
        if not path.exists():
            self.skipTest("saved fine mosaic fixture not available")
        mosaic = load_fine_mosaic(path)
        report = adapt_saved_mosaics([{"domain_id": "saved-fine", "mosaic": mosaic}])
        self.assertEqual(report["adapter"]["water_generation_called"], False)
        self.assertFalse(report["flags"]["edge_evidence_complete"])
        self.assertFalse(report["water"]["surface_available"])

    def test_stable_global_ids_shared_nodes_and_unique_edges(self):
        first = domain()
        second = domain(reverse=True)
        second["domain_id"] = "B"
        for edge in second["edges"]:
            edge["start"], edge["end"] = edge["end"], edge["start"]
        report = audit_cross_domain([second, first])
        self.assertEqual(len(report["shared_boundary_node_ids"]), 3)
        self.assertEqual(report["grid"]["lods"], [0])
        self.assertEqual(report["ledger"]["shared_edge_count"], 2)
        self.assertEqual(audit_cross_domain([first, second])["global_nodes"], report["global_nodes"])

    def test_shared_edge_is_counted_once_and_flux_cancels(self):
        first = domain()
        second = domain(reverse=True)
        second["domain_id"] = "B"
        for edge in second["edges"]:
            edge["start"], edge["end"] = edge["end"], edge["start"]
        for edge in second["edges"]:
            edge["boundary"] = False
        first["edges"][0]["boundary"] = False
        report = audit_cross_domain([first, second])
        self.assertEqual(report["ledger"]["shared_edge_count"], 2)
        self.assertAlmostEqual(report["ledger"]["internal_shared_flux_residual_m3_s"], 0.)

    def test_spacing_misalignment_and_surface_mismatch_rejected(self):
        first, second = domain(), domain(reverse=True)
        second["domain_id"] = "B"
        second["nodes"][1]["water_surface_m"] = 4.
        with self.assertRaisesRegex(ValueError, "water surface"):
            audit_cross_domain([first, second])
        second["nodes"][1]["water_surface_m"] = 3.
        second["nodes"][1]["x_m"] = 1.5
        with self.assertRaisesRegex(ValueError, "grid"):
            audit_cross_domain([first, second])

    def test_unknown_protected_barrier_rejects_flux(self):
        first = domain(unknown=True)
        with self.assertRaisesRegex(ValueError, "barrier"):
            audit_cross_domain([first])
        first = domain(protected=True)
        with self.assertRaisesRegex(ValueError, "barrier"):
            audit_cross_domain([first])

    def test_edge_direction_and_partial_publication(self):
        first, second = domain(), domain(reverse=True)
        second["domain_id"] = "B"
        for edge in second["edges"]:
            edge["start"], edge["end"] = edge["end"], edge["start"]
        second["edges"][0]["flux_m3_s"] = .25
        with self.assertRaisesRegex(ValueError, "anti-symmetric"):
            audit_cross_domain([first, second])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with self.assertRaises(ValueError):
                save_cross_domain_report({"schema": "bad"}, path)
            self.assertFalse(path.exists())
            report = audit_cross_domain([domain()])
            save_cross_domain_report(report, path)
            self.assertEqual(json.loads(path.read_text())["schema"], "surface-cross-domain-v1")
            self.assertFalse(report["flags"]["water_generated"])
            with self.assertRaises(FileExistsError):
                save_cross_domain_report(report, path)

    def test_coarse_edge_is_split_against_fine_domain(self):
        coarse = domain()
        coarse["domain_id"] = "coarse"
        coarse["grid"]["spacing_x_m"] = 2.0
        coarse["nodes"] = [
            {"local_id": 0, "x_m": 0.0, "z_m": 0.0, "h0_m": 10.0, "unknown": False, "protected": False, "water_surface_m": 3.0},
            {"local_id": 1, "x_m": 2.0, "z_m": 0.0, "h0_m": 9.0, "unknown": False, "protected": False, "water_surface_m": 3.0},
        ]
        coarse["edges"] = [{"local_id": 0, "start": 0, "end": 1, "flux_m3_s": 1.0, "boundary": False}]
        fine = {
            "domain_id": "fine",
            "grid": {"origin_x_m": 0.0, "origin_z_m": 0.0, "spacing_x_m": 1.0, "spacing_z_m": 1.0, "lod": 1},
            "nodes": [
                {"local_id": 0, "x_m": 0.0, "z_m": 0.0, "h0_m": 10.0, "unknown": False, "protected": False, "water_surface_m": 3.0},
                {"local_id": 1, "x_m": 1.0, "z_m": 0.0, "h0_m": 9.5, "unknown": False, "protected": False, "water_surface_m": 3.0},
                {"local_id": 2, "x_m": 2.0, "z_m": 0.0, "h0_m": 9.0, "unknown": False, "protected": False, "water_surface_m": 3.0},
            ],
            "edges": [
                {"local_id": 0, "start": 1, "end": 0, "flux_m3_s": -0.5, "boundary": False},
                {"local_id": 1, "start": 2, "end": 1, "flux_m3_s": -0.5, "boundary": False},
            ],
        }
        report = audit_cross_domain([coarse, fine])
        self.assertEqual(report["ledger"]["shared_edge_count"], 2)
        self.assertAlmostEqual(report["ledger"]["internal_shared_flux_residual_m3_s"], 0.0)


if __name__ == "__main__":
    unittest.main()
