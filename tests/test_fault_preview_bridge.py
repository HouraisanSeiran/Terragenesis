"""Real pinned fault preview contracts, without hydrology or saved output writes."""

import copy
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web-preview"))
sys.path.insert(0, str(ROOT))
import fault_preview

SPEC = importlib.util.spec_from_file_location("fault_bridge_under_test", ROOT / "web-preview/bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FaultPreviewBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = fault_preview.fault_case()
        cls.body = dict(cls.case["defaults"])
        cls.index, cls.config, cls.records, cls.report = fault_preview._evidence()
        cls.source = fault_preview._source(cls.index)

    def assert_mesh(self, payload):
        mesh = payload["mesh"]
        geometry = payload["geometry"]
        vertices = np.asarray(mesh["vertices"])
        reference = np.asarray(mesh["reference"])
        displacement = np.asarray(mesh["displacement"])
        triangles = np.asarray(mesh["triangles"])
        sides = np.asarray(mesh["vertexSide"])
        np.testing.assert_allclose(vertices - reference, displacement, atol=3e-11)
        moving = np.linalg.norm(displacement, axis=1) > 1e-12
        influenced = np.any(moving[triangles], axis=1)
        self.assertTrue(np.all(np.ptp(sides[triangles[influenced]], axis=1) == 0))
        self.assertEqual(geometry["crossSeamTriangles"], 0)
        self.assertEqual(geometry["displayVertices"], len(vertices))
        self.assertEqual(geometry["displayTriangles"], len(triangles))
        self.assertEqual(geometry["displayMovedVertices"], geometry["movedVertices"])
        self.assertLess(len(vertices), geometry["fullVertices"])
        self.assertLessEqual(len(vertices), 25_000)
        self.assertTrue(np.any(np.asarray(mesh["sourceVertexIndex"]) == -1))
        self.assertGreater(len(mesh["seamEdges"]), 0)
        self.assertEqual(payload["selection"], fault_preview.SELECTION)
        self.assertTrue(payload["editable"])
        for flag in ("hydraulic_ready", "publishable", "solver_advanced", "water_generated", "self_intersection_verified"):
            self.assertIs(payload["metadata"][flag], False)

    def test_saved_cold_read_never_calls_apply(self):
        with patch.object(fault_preview, "apply_fault", side_effect=AssertionError("cold generation forbidden")):
            payload = fault_preview.fault_case()
        self.assertEqual(payload["schema"], "fault-case-v1")
        self.assertEqual(payload["identity"], self.index["fault"]["identity_sha256"])
        self.assert_mesh(payload)

    def test_display_reference_is_preslip_formed_source_without_chart_substitution(self):
        mesh = self.case["mesh"]
        indices = np.asarray(mesh["sourceVertexIndex"])
        exact = indices >= 0
        deformation = self.source["arrays"]["vertices_xyz_m"][indices[exact]] - self.source["arrays"]["reference_xyz_m"].reshape(-1, 3)[indices[exact]]
        self.assertGreater(float(np.linalg.norm(deformation, axis=1).max()), 1.)
        np.testing.assert_allclose(np.asarray(mesh["reference"])[exact],
                                   self.source["arrays"]["vertices_xyz_m"][indices[exact]], atol=3e-11)
        np.testing.assert_array_equal(np.asarray(mesh["reference"]),
                                      np.asarray(mesh["vertices"]) - np.asarray(mesh["displacement"]))
        self.assertEqual(self.case["plane_origin_bounds_xz_m"], fault_preview.catalog()["plane_origin_bounds_xz_m"])

    def test_real_signed_and_zero_slip_source_unchanged(self):
        watched = (fault_preview.INDEX, fault_preview.CONFIG, fault_preview.SOURCE,
                   fault_preview.INDEX.parent / "fault.npz", fault_preview.INDEX.parent / "audit.json")
        before = {path: fault_preview._sha256(path) for path in watched}
        previews = []
        for slip in (1., -1., 0., 4.):
            with self.subTest(slip=slip):
                payload = fault_preview.preview_fault({**self.body, "slip_m": slip})
                self.assertEqual(payload["schema"], "fault-preview-v1")
                self.assert_mesh(payload)
                self.assertEqual(payload["geometry"]["movedVertices"] == 0, slip == 0)
                self.assertAlmostEqual(payload["geometry"]["maxDisplacement_m"], abs(slip))
                previews.append(payload)
        np.testing.assert_array_equal(previews[0]["mesh"]["triangles"], previews[1]["mesh"]["triangles"])
        np.testing.assert_allclose(previews[0]["mesh"]["displacement"], -np.asarray(previews[1]["mesh"]["displacement"]))
        self.assertEqual(previews[3]["identity"], self.case["identity"])
        self.assertEqual(before, {path: fault_preview._sha256(path) for path in watched})

    def test_negative_moving_side(self):
        payload = fault_preview.preview_fault({**self.body, "moving_side": "negative", "slip_m": 2.})
        self.assert_mesh(payload)
        sides = np.asarray(payload["mesh"]["vertexSide"])
        displacement = np.asarray(payload["mesh"]["displacement"])
        self.assertTrue(np.all(displacement[sides > 0] == 0))
        self.assertGreater(payload["geometry"]["movedVertices"], 0)

    def test_invalid_fields_paths_numbers_and_bounds_before_apply(self):
        invalid = [None, [], {}, {**self.body, "path": "fault.npz"},
                   {**self.body, "source": "fluted_wall"}, {**self.body, "selection": fault_preview.SELECTION},
                   {**self.body, "budget": 100000}, {**self.body, "protected": False},
                   {**self.body, "slip": 2}, {**self.body, "moving_side": "both"},
                   {**self.body, "moving_side": []}, {**self.body, "slip_m": 8.01},
                   {**self.body, "slip_m": -8.01}, {**self.body, "slip_m": True},
                   {**self.body, "transition_width_m": .99}, {**self.body, "transition_width_m": 30.01},
                   {**self.body, "strike_degrees": 361}, {**self.body, "plane_origin_xz_m": [0, 0]},
                   {**self.body, "plane_origin_xz_m": [True, self.body["plane_origin_xz_m"][1]]}]
        for key in ("slip_m", "strike_degrees", "transition_width_m"):
            for value in (float("nan"), float("inf"), False, "4"):
                invalid.append({**self.body, key: value})
        with patch.object(fault_preview, "apply_fault", side_effect=AssertionError("invalid input reached apply")):
            for body in invalid:
                with self.subTest(body=body), self.assertRaises(ValueError):
                    fault_preview.preview_fault(body)

    def test_hash_schema_identity_and_audit_fail_closed(self):
        with patch.object(fault_preview, "INDEX_SHA256", "0" * 64), self.assertRaisesRegex(ValueError, "hash"):
            fault_preview.fault_case()
        original_json = fault_preview._json
        for changed in ("schema", "identity", "audit"):
            def corrupt(path, expected, schema=None):
                result = copy.deepcopy(original_json(path, expected, schema))
                if changed == "schema" and path == fault_preview.INDEX:
                    raise ValueError("fixed fault schema mismatch")
                if changed == "identity" and path == fault_preview.CONFIG:
                    result["source"]["expected_identity"] = "0" * 64
                if changed == "audit" and path.name == "audit.json":
                    result["passed"] = False
                return result
            with self.subTest(changed=changed), patch.object(fault_preview, "_json", side_effect=corrupt), self.assertRaises(ValueError):
                fault_preview.fault_case()

    def test_each_evidence_pin_rejects_changed_bytes_without_apply(self):
        original_sha = fault_preview._sha256
        for target in (fault_preview.CONFIG, fault_preview.SOURCE,
                       fault_preview.INDEX.parent / "fault.npz", fault_preview.INDEX.parent / "audit.json",
                       fault_preview.INDEX.parent / "report.json"):
            def corrupt_sha(path):
                return "0" * 64 if path == target else original_sha(path)
            with self.subTest(target=target.name), patch.object(fault_preview, "_sha256", side_effect=corrupt_sha), patch.object(fault_preview, "apply_fault", side_effect=AssertionError("pin mismatch reached generation")), self.assertRaisesRegex(ValueError, "hash"):
                fault_preview.fault_case()

    def test_protected_selection_and_cutmiss_rejected(self):
        source = {**self.source, "arrays": dict(self.source["arrays"])}
        protected = source["arrays"]["protected_mask"].copy()
        protected[fault_preview.SELECTION["row_start"] + 3, fault_preview.SELECTION["column_start"] + 3] = True
        source["arrays"]["protected_mask"] = protected
        with patch.object(fault_preview, "_source", return_value=source), self.assertRaisesRegex(ValueError, "protected"):
            fault_preview.preview_fault(self.body)
        reference = self.source["arrays"]["reference_xyz_m"]
        row_start, _, col_start, _ = fault_preview._window(reference.shape[:2])
        origin = reference[row_start, col_start, (0, 2)].tolist()
        with self.assertRaisesRegex(ValueError, "cutmiss"):
            fault_preview.preview_fault({**self.body, "plane_origin_xz_m": origin, "strike_degrees": 0.})

    def test_nomotion_and_budgets_fail_closed(self):
        saved = fault_preview.load_fault(fault_preview.INDEX.parent / "fault.npz",
                                        expected_sha256=self.index["fault"]["sha256"],
                                        expected_identity=self.index["fault"]["identity_sha256"])
        no_motion = {**saved, "arrays": dict(saved["arrays"])}
        no_motion["arrays"]["applied_displacement_xyz_m"] = np.zeros_like(saved["arrays"]["applied_displacement_xyz_m"])
        with patch.object(fault_preview, "apply_fault", return_value=no_motion), self.assertRaisesRegex(ValueError, "nomotion"):
            fault_preview.preview_fault(self.body)
        for constant in ("MAX_DISPLAY_VERTICES", "MAX_JSON_BYTES", "MAX_WORKING_BYTES"):
            with self.subTest(constant=constant), patch.object(fault_preview, constant, 1), self.assertRaisesRegex(ValueError, "budget"):
                fault_preview.fault_case()

    def test_crop_preserves_exact_saved_triangle_and_seam_indices(self):
        saved = fault_preview.load_fault(fault_preview.INDEX.parent / "fault.npz",
                                        expected_sha256=self.index["fault"]["sha256"],
                                        expected_identity=self.index["fault"]["identity_sha256"])
        arrays = saved["arrays"]
        mesh = self.case["mesh"]
        lookup = {(tuple(vertex), side): index for index, (vertex, side) in
                  enumerate(zip(arrays["vertices_xyz_m"], arrays["vertex_side"]))}
        full_indices = np.asarray([lookup[(tuple(vertex), side)] for vertex, side in zip(mesh["vertices"], mesh["vertexSide"])])
        full_triangles = {tuple(triangle) for triangle in arrays["triangles"]}
        self.assertTrue(all(tuple(triangle) in full_triangles for triangle in full_indices[np.asarray(mesh["triangles"])]))
        full_seams = {tuple(edge) for edge in arrays["seam_edges"]}
        self.assertTrue(all(tuple(edge) in full_seams for edge in full_indices[np.asarray(mesh["seamEdges"])]))
        np.testing.assert_array_equal(arrays["vertex_source_index"][full_indices], mesh["sourceVertexIndex"])

    def test_http_routes_and_lazy_catalog_no_large_mesh(self):
        server = bridge.ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        try:
            with patch.object(fault_preview, "fault_case", return_value=self.case):
                connection.request("GET", "/api/fault/case")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["schema"], "fault-case-v1")
            connection.request("GET", "/api/fault/case?path=evil")
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.request("POST", "/api/fault/preview", json.dumps({**self.body, "source": "evil"}), {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            with patch.object(fault_preview, "preview_fault", return_value={**self.case, "schema": "fault-preview-v1"}) as preview:
                connection.request("POST", "/api/fault/preview", json.dumps(self.body), {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["schema"], "fault-preview-v1")
                preview.assert_called_once_with(self.body)
            connection.request("POST", "/api/fault/draft", "{}")
            response = connection.getresponse()
            self.assertTrue(json.loads(response.read())["deprecated"])
            with patch.object(fault_preview, "load_fault", side_effect=AssertionError("catalog loaded mesh")), patch.object(fault_preview, "_source", side_effect=AssertionError("catalog loaded source")):
                catalog = bridge.fixed_catalog()
                self.assertEqual(catalog["fault"]["status"], "diagnostic-real-cut")
                self.assertNotIn("mesh", catalog["fault"])
                self.assertNotIn("not implemented", " ".join(catalog["limitations"]))
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
