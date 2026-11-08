"""The pillar-field true-3D review reader: pinned artifact, bounded routes, no rebuild.

Two layers are checked, mirroring ``test_special_surface_preview``.  First the adapter on its
own: the four pins must equal the real digests on disk (a re-pinned constant that no longer
matches the artifact is a silent re-point and must never read), the stored L1 report must stay
a ``candidate``, and every declared array must arrive with exactly the byte count it advertised.
Then the real HTTP surface, because the routes are the contract the browser actually sees.

Nothing here certifies anything: the artifact's own flags are the ones under test, and the
reader is expected to reproduce them as false rather than upgrade them.
"""

import importlib.util
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web-preview"


def load(name):
    spec = importlib.util.spec_from_file_location(name, WEB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PILLARS = load("pillars3d")
BRIDGE = load("bridge")


class PillarReaderTests(unittest.TestCase):
    def test_every_pin_matches_the_artifact_on_disk(self):
        from terrain_pipeline.common_infra import file_sha256
        self.assertNotEqual(PILLARS.REPORT_SHA256, "PENDING")
        self.assertNotEqual(PILLARS.CARVED_SHA256, "PENDING")
        self.assertNotEqual(PILLARS.PLAIN_SHA256, "PENDING")
        self.assertEqual(file_sha256(PILLARS.REPORT), PILLARS.REPORT_SHA256)
        self.assertEqual(file_sha256(PILLARS.CARVED), PILLARS.CARVED_SHA256)
        self.assertEqual(file_sha256(PILLARS.PLAIN), PILLARS.PLAIN_SHA256)
        record = json.loads(PILLARS.REPORT.read_text(encoding="utf-8"))
        self.assertEqual(record["identity_sha256"], PILLARS.REPORT_IDENTITY)

    def test_the_stored_report_is_still_a_candidate(self):
        record = PILLARS.source_report()
        self.assertEqual(record["schema"], PILLARS.SOURCE_SCHEMA)
        self.assertEqual(record["status"], "candidate")
        self.assertTrue(record["flags"])
        self.assertFalse(any(record["flags"].values()))
        self.assertEqual(record["supersedes"]["kind"], "sandstone_pillar_field")
        self.assertTrue(record["supersedes"]["not_a_certification"])

    def test_a_moved_report_pin_is_refused_not_displayed(self):
        PILLARS.CACHED = None
        with patch.object(PILLARS, "REPORT_SHA256", "0" * 64):
            with self.assertRaises(ValueError):
                PILLARS.source_report()
        with patch.object(PILLARS, "REPORT_IDENTITY", "0" * 64):
            with self.assertRaises(ValueError):
                PILLARS.source_report()
        PILLARS.CACHED = None

    def test_a_moved_archive_pin_is_refused_not_displayed(self):
        PILLARS.CACHED = None
        with patch.object(PILLARS, "CARVED_SHA256", "0" * 64):
            with self.assertRaises(ValueError):
                PILLARS.frame()
        PILLARS.CACHED = None

    def test_catalog_carries_no_capability(self):
        catalog = PILLARS.catalog()
        self.assertEqual(catalog["schema"], "special-pillars3d-catalog-v1")
        self.assertEqual(catalog["status"], "candidate")
        self.assertEqual(len(catalog["cases"]), 1)
        for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable",
                     "self_intersection_verified"):
            self.assertFalse(catalog[flag], flag)

    def test_every_declared_array_matches_its_binary_body(self):
        descriptor, buffers = PILLARS.frame()
        self.assertEqual(descriptor["schema"], PILLARS.SCHEMA)
        for name, record in descriptor["arrays"].items():
            body = PILLARS.binary(name)
            self.assertEqual(len(body), record["bytes"], name)
            self.assertEqual(len(body), buffers[name].nbytes, name)
            self.assertEqual(record["url"], f"/api/pillars3d/array/{name}")

    def test_mesh_reuses_the_stored_topology(self):
        # The reader must hand the stored index array through untouched: the carved solid is
        # the artifact's own MESH64 export, so its counts are the ones the report declares.
        descriptor, buffers = PILLARS.frame()
        self.assertEqual(buffers["solid_vertices"].shape, (descriptor["vertices"], 3))
        self.assertEqual(buffers["solid_triangles"].shape, (descriptor["triangles"], 3))
        self.assertEqual(buffers["plain_vertices"].shape, (descriptor["plain_vertices"], 3))
        self.assertEqual(buffers["plain_triangles"].shape, (descriptor["plain_triangles"], 3))
        self.assertLess(int(buffers["solid_triangles"].max()), descriptor["vertices"])
        self.assertLess(int(buffers["plain_triangles"].max()), descriptor["plain_vertices"])
        # 14 of 16 pillars stand at full depth, so the carved solid carries far more vertices
        # than the plain prisms and the gap is itself the evidence the carve ran.
        self.assertGreater(descriptor["vertices"], descriptor["plain_vertices"])
        self.assertEqual(descriptor["full_depth_pillars"],
                         sum(1 for scale in descriptor["carve_scales"] if scale >= 1.))

    def test_plan_footprints_describe_the_joint_cells(self):
        descriptor, _ = PILLARS.frame()
        self.assertEqual(len(descriptor["pillar_footprints"]), descriptor["pillar_count"])
        for index, item in enumerate(descriptor["pillar_footprints"]):
            self.assertEqual(item["index"], index)
            self.assertEqual(item["role"], "pillar-%02d" % index)
            self.assertGreater(len(item["ring_xz_m"]), 8)
            self.assertGreater(item["ring_area_m2"], 0.)
            self.assertGreater(item["height_m"], 0.)
            self.assertEqual(len(item["centre_xz_m"]), 2)
        rings = [item["ring_area_m2"] for item in descriptor["pillar_footprints"]]
        # Voronoi cells on the frame boundary are clipped by the jittered seed grid, so the
        # smallest footprint is a corner sliver and the largest is an interior cell: the spread
        # is real geometry, not a defect. What must hold is that the cells tile most of the
        # analytic base without spilling out of it.
        self.assertLess(max(rings) / min(rings), 20.)
        ring = descriptor["plateau"]["ring_xz_m"]
        plateau_area = abs(sum(ring[index][0] * ring[(index + 1) % len(ring)][1]
                               - ring[(index + 1) % len(ring)][0] * ring[index][1]
                               for index in range(len(ring)))) / 2.
        self.assertLess(sum(rings), plateau_area)
        self.assertGreater(sum(rings), .5 * plateau_area)
        self.assertGreater(descriptor["plateau"]["top_y_m"], descriptor["plateau"]["bottom_y_m"])
        self.assertEqual(len(descriptor["plateau"]["ring_xz_m"]), 4)
        self.assertGreater(len(descriptor["level_schedule"]["levels_m"]), 1)
        self.assertEqual(descriptor["level_schedule"]["pillar_index"], 0)
        self.assertAlmostEqual(descriptor["level_schedule"]["levels_m"][0], 0.)

    def test_volume_account_is_consistent_and_declared(self):
        descriptor, _ = PILLARS.frame()
        account = descriptor["volume_account"]
        self.assertGreater(account["assembled_volume_m3"], 0.)
        self.assertEqual(account["assembled_volume_m3"], descriptor["assembled_volume_m3"])
        # The pillars stand apart by a joint gap and the plateau lies entirely below y = 0, so
        # the declared inputs are mutually disjoint and the union removes no material at all:
        # the honest expectation is exactly zero, not "some overlap".
        self.assertEqual(account["overlap_removed_m3"], 0.)
        self.assertEqual(account["inputs_total_m3"], account["assembled_volume_m3"])
        self.assertLess(abs(account["relative_residual"]), 1e-9)
        # What VDM did add is measurable: the carved variant is lighter than the plain prisms.
        self.assertGreater(account["carved_removed_m3"], 0.)
        self.assertLess(account["assembled_volume_m3"],
                        account["uncarved_variant_assembled_volume_m3"])
        self.assertEqual(descriptor["components"], 1)

    def test_unknown_array_is_refused(self):
        with self.assertRaises(ValueError):
            PILLARS.binary("no_such_array")


class PillarRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def fetch(self, path):
        try:
            with urlopen(self.base + path, timeout=60) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    def test_catalog_route(self):
        status, headers, body = self.fetch("/api/pillars3d/catalog")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["schema"], "special-pillars3d-catalog-v1")

    def test_frame_then_binary_route(self):
        status, _, body = self.fetch("/api/pillars3d/frame")
        self.assertEqual(status, 200)
        descriptor = json.loads(body)
        self.assertEqual(descriptor["caseId"], "pillars3d")
        for name, record in descriptor["arrays"].items():
            status, headers, blob = self.fetch(record["url"])
            self.assertEqual(status, 200, name)
            self.assertEqual(headers["Content-Type"], "application/octet-stream")
            self.assertEqual(len(blob), record["bytes"], name)

    def test_query_strings_and_unknown_routes_are_refused(self):
        status, _, body = self.fetch("/api/pillars3d/frame?path=elsewhere")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))
        status, _, body = self.fetch("/api/pillars3d/array/no_such_array")
        self.assertEqual(status, 500)
        self.assertIn("outside allowlist", json.loads(body)["error"])
        status, _, _ = self.fetch("/api/pillars3d/frame/extra")
        self.assertEqual(status, 404)
        status, _, _ = self.fetch("/api/pillars3d/nope")
        self.assertEqual(status, 404)

    def test_script_is_allowlisted_and_neighbours_stay_closed(self):
        status, headers, body = self.fetch("/pillars3d.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertIn(b"window.pillars3d", body)
        status, _, _ = self.fetch("/pillars3d-nope.js")
        self.assertEqual(status, 403)

    def test_page_registers_the_new_workspace(self):
        status, _, body = self.fetch("/index.html")
        self.assertEqual(status, 200)
        self.assertIn(b"pillars3dControls", body)
        self.assertIn(b"pillars3d.js", body)
        status, _, body = self.fetch("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"pillars3d", body)


if __name__ == "__main__":
    unittest.main()
