import unittest

from tools.audit_hybrid_surface_composition_v6 import iter_input_pins


class SurfaceCompositionV6SavedAuditTests(unittest.TestCase):
    def test_explicit_pin_walk_ignores_container_dicts_and_keeps_nested_pins(self):
        record = {"inputs": {
            "geometry": {"path": "g", "sha256": "1"},
            "geometry_audit": {"path": "ga", "sha256": "2"},
            "graph": {"path": "gr", "sha256": "3"},
            "original_source_sampling": {"path": "s", "sha256": "4"},
            "surface_attachments": {"path": "a", "sha256": "5"},
            "vdm": {"path": "v", "sha256": "6"},
            "mesh_pins": {"rock_after": {"path": "m", "sha256": "7"}},
            "surface_nodes": {"sink": {"path": "n", "sha256": "8"}},
            "ordinary_metadata": {"units": "m", "origin": [0, 0, 0]}}}
        walked = list(iter_input_pins(record))
        self.assertEqual([label for label, _ in walked], [
            "inputs.geometry", "inputs.geometry_audit", "inputs.graph",
            "inputs.original_source_sampling", "inputs.surface_attachments", "inputs.vdm",
            "inputs.mesh_pins.rock_after", "inputs.surface_nodes.sink"])
        self.assertNotIn("ordinary_metadata", [label for label, _ in walked])


if __name__ == "__main__":
    unittest.main()
