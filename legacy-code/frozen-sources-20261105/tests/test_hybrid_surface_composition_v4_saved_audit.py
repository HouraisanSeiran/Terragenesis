import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import audit_hybrid_surface_composition_v4 as audit
from tools.hybrid_exact_solid_saved_audit import ExactSolid
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid, load_native_bound
from tools.td_shared_channel_fine_saved_audit import digest, file_sha256


def sealed(record):
    record = dict(record)
    record.pop("identity_sha256", None)
    record["identity_sha256"] = digest(record)
    return record


class SurfaceCompositionV4SavedAuditTests(unittest.TestCase):
    def test_native_identity_explicitly_from_sections_preserves_original_sha_only_pin(self):
        identity = "a" * 64
        manifest = {"identity_sha256": identity, "metadata": {"origin_m_xz": [0., 0.], "spacing_m": 1.}}
        with tempfile.TemporaryDirectory(dir=audit.ROOT / ".scratch") as temporary:
            path = Path(temporary) / "tiny-native.npz"
            np.savez_compressed(path, manifest=np.frombuffer(json.dumps(manifest).encode("utf-8"), dtype=np.uint8),
                height_m=np.asarray([[1., 2.], [3., 4.]]), valid_mask=np.ones((2, 2), dtype=bool),
                protected_mask=np.zeros((2, 2), dtype=bool), open_boundary_mask=np.zeros((2, 2), dtype=bool),
                cell_owner=np.zeros((2, 2), dtype=np.int64), contribution_owner=np.zeros((2, 2), dtype=np.int64),
                node_unknown_contact=np.asarray([False]))
            pin = {"path": str(path.resolve()), "sha256": file_sha256(path)}
            before = copy.deepcopy(pin)
            native, binding = load_native_bound(pin, identity, [0], {"covered_native_cell_ids": [], "stage_by_leaf": []})
            self.assertEqual(native.sample([.5, .5])["height_m"], 2.5)
            self.assertEqual(pin, before)
            self.assertNotIn("identity_sha256", pin)
            self.assertEqual(binding["expected_hierarchy_identity_sha256"], binding["manifest_hierarchy_identity_sha256"])
            self.assertFalse(binding["original_inputs_or_pin_modified"])
            with self.assertRaisesRegex(ValueError, "manifest/sections"):
                load_native_bound(pin, "b" * 64, [0], {"covered_native_cell_ids": [], "stage_by_leaf": []})
            with self.assertRaisesRegex(ValueError, "optional hierarchy pin"):
                load_native_bound({**pin, "identity_sha256": "b" * 64}, identity, [0],
                                  {"covered_native_cell_ids": [], "stage_by_leaf": []})

    def test_validated_view_binds_all_original_arrays_flags_volume_and_failure_stage(self):
        vertices = [[0., 0., 0.], [1., 0., 0.], [0., 1e-20, 0.], [0., 0., 1.]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        validated = ExactSolid(vertices, triangles, "tiny existing evidence")
        evidence = validated.validation_evidence
        mesh = sealed({"schema": "td-hybrid-local-solid-mesh-v1", "role": "tiny",
            "local_origin_xyz_m": [0., 0., 0.], "vertices_local_xyz_m": vertices,
            "triangles": triangles, "signed_volume_m3": validated.signed_volume})
        view = ValidatedSolid(mesh, evidence, "tiny byte-bound view")
        self.assertEqual(view.vertices.tolist(), vertices)
        self.assertEqual(view.triangles.tolist(), triangles)
        self.assertEqual(view.exact_signed_volume, validated.exact_signed_volume)
        self.assertIs(view.validation_evidence, evidence)
        changed = copy.deepcopy(mesh)
        changed["vertices_local_xyz_m"][1][0] = 2.
        with self.assertRaisesRegex(ValueError, "digest"):
            ValidatedSolid(sealed(changed), evidence, "changed arrays")
        changed_evidence = copy.deepcopy(evidence)
        changed_evidence["all_original_faces_retained"] = False
        with self.assertRaisesRegex(ValueError, "closed/oriented/retained"):
            ValidatedSolid(mesh, changed_evidence, "incomplete retained proof")
        changed_evidence = copy.deepcopy(evidence)
        changed_evidence["exact_signed_volume_m3"] = ["1", "1"]
        with self.assertRaisesRegex(ValueError, "exact volume"):
            ValidatedSolid(mesh, changed_evidence, "changed volume proof")

        def fail_native(pin, parent_pin, report):
            report["current_stage"] = "native_manifest_binding"
            report["inherited_evidence"] = {"mesh_validation_inherited": True}
            raise KeyError("manifest-test-field")

        with patch.object(audit, "resume", side_effect=fail_native):
            report = audit.audit({"sha256": "tiny"}, {"sha256": "tiny"})
        self.assertEqual(report["status"], "refused")
        self.assertEqual(report["failure_stage"], "native_manifest_binding")
        self.assertEqual(report["failures"][0]["error_type"], "KeyError")
        self.assertIn("manifest-test-field", report["errors"][0])
        self.assertTrue(report["inherited_evidence"]["mesh_validation_inherited"])
        self.assertFalse(report["native_half_arm_sources_verified"])
        self.assertFalse(report["two_sided_complete_port_verified"])


if __name__ == "__main__":
    unittest.main()
