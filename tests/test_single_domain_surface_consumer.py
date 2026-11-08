import json
from pathlib import Path
import tempfile
import threading
import unittest
import numpy as np
from urllib.error import HTTPError
from urllib.request import urlopen,Request

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.single_domain_surface_consumer import BUDGETS,SCHEMA,array_roles,copy_payload,load_consumer_manifest,readonly_server


class SurfaceConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        payload = self.root/"frame.npz"
        payload.write_bytes(b"synthetic pinned payload")
        self.manifest = dict(schema=SCHEMA,budgets=BUDGETS,backend="fine-saved-fan",evidence_status="diagnostic-fine-only",
                             hydraulic_ready=False,natural_outlet_verified=False,publishable=False,solver_advanced=False,
                             output_bytes=payload.stat().st_size,artifacts=[dict(path="frame.npz",bytes=payload.stat().st_size,
                                 sha256=file_sha256(payload),media_type="application/octet-stream")],
                             scenarios=dict(fixture=dict(geometry="frame.npz",frames=[dict(frame=0,time_s=0,artifact="frame.npz")])))

    def tearDown(self):
        self.temporary.cleanup()

    def load(self):
        path = self.root/"manifest.json"
        path.write_text(json.dumps(self.manifest),encoding="utf-8")
        return load_consumer_manifest(path,expected_sha256=file_sha256(path))

    def test_relocatable_payload_and_tamper_rejection(self):
        context = self.load()
        self.assertEqual(context["allowlist"]["frame.npz"],self.root/"frame.npz")
        (self.root/"frame.npz").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.load()

    def test_allowlist_traversal_flags_and_bytes_rejected(self):
        for kind in ("traversal","flag","bytes"):
            with self.subTest(kind=kind):
                original = json.loads(json.dumps(self.manifest))
                if kind=="traversal":
                    self.manifest["artifacts"][0]["path"] = "../frame.npz"
                elif kind=="flag":
                    self.manifest["publishable"] = True
                else:
                    self.manifest["output_bytes"] += 1
                with self.assertRaises(ValueError):
                    self.load()
                self.manifest = original

    def test_http_exact_allowlist_and_write_method_rejected(self):
        context = self.load()
        server = readonly_server(context,port=0)
        worker = threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        base = "http://127.0.0.1:"+str(server.server_address[1])
        try:
            with urlopen(base+"/payload/frame.npz") as response:
                self.assertEqual(response.read(),b"synthetic pinned payload")
            for route in ("/frame.npz","/payload/../manifest.json","/payload/C:/Windows/win.ini"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base+route)
                self.assertEqual(error.exception.code,404)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+"/manifest.json",data=b"forbidden",method="POST"))
            self.assertEqual(error.exception.code,501)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_copy_rejects_escaping_destination_before_reading_source(self):
        output = self.root/"export"
        output.mkdir()
        for name in ("../escaped.npz", "/escaped.npz", "C:/escaped.npz", "x\\escaped.npz", "./escaped.npz", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                copy_payload(output,name,{}, {},role="fixture",provenance={})
        self.assertEqual(list(output.iterdir()), [])

    def test_fine_saved_physical_units_are_distinct(self):
        roles = array_roles({name:np.zeros(1) for name in (
            "time_s", "momentum_x_m2_s", "stage_relative_m", "cell_area_m2", "internal_q_m3_s")})
        self.assertEqual({name:record["units"] for name,record in roles.items()}, {
            "time_s":"s", "momentum_x_m2_s":"m2/s", "stage_relative_m":"m",
            "cell_area_m2":"m2", "internal_q_m3_s":"m3/s"})

    def test_adaptive_manifest_requires_explicit_scope_and_saved_bindings(self):
        self.manifest.update(backend="adaptive-saved-canonical-fan", evidence_status="adaptive-finite-window-evidence",
                             uniform_coarse_convergence_claim=False)
        self.manifest["scenarios"]["fixture"]["frames"] = [dict(frame=number, time_s=30.*number,
            artifact="frame.npz", snapshot="frame.npz", adaptive_geometry="frame.npz") for number in range(2)]
        self.assertEqual(self.load()["manifest"]["backend"], "adaptive-saved-canonical-fan")
        self.manifest["uniform_coarse_convergence_claim"] = True
        with self.assertRaises(ValueError):
            self.load()
        self.manifest["uniform_coarse_convergence_claim"] = False
        del self.manifest["scenarios"]["fixture"]["frames"][1]["snapshot"]
        with self.assertRaises(ValueError):
            self.load()


if __name__=="__main__":
    unittest.main()
