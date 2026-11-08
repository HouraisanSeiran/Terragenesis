import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from tests.test_td_hour_pages_acceptance_io import write_bundle, write_json
from tools.audit_td_accepted_topology import audit


class IndependentAcceptedTopologyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        original = make_td_source(np.array([[3., 2., 3.], [2., 0., 2.], [3., 2., 3.]]), spacing_m=30.)
        self.original = write_bundle(self.root / "original.npz", original["arrays"], original["metadata"])
        bed = original["arrays"]["height_m"].copy()
        bed[0, 1] -= .2
        source = make_td_source(bed, spacing_m=30., source_sha256=self.original["expected_sha256"])
        self.source = write_bundle(self.root / "derived.npz", source["arrays"], source["metadata"])
        topology = build_basin_hierarchy(source)
        self.hierarchy = write_bundle(self.root / "hierarchy.npz", topology["arrays"], topology["metadata"])
        parent = dict(identity_sha256="a" * 64, stage="geometry_only",
            inputs=dict(source_record=self.original), candidates=dict(valley_incision=dict(source=self.source)))
        self.parent = write_json(self.root / "parent.json", parent)
        self.parent["expected_identity"] = parent["identity_sha256"]
        self.path = self.root / "index.json"
        self.index = dict(schema="td-accepted-candidate-topology-review-v1", candidate_id="valley_incision",
            parent_manifest=self.parent, source=self.source, hierarchy=self.hierarchy,
            hydrology_solved=False, recoupling_required=True, selection="baseline pending",
            flags=dict(hydraulic_ready=False, publishable=False, natural_outlet_verified=False))
        write_json(self.path, self.index)

    def test_changed_bed_and_independent_threshold_capacity_checks(self):
        result = audit(self.path, file_sha256(self.path), self.parent)
        self.assertEqual(result["changed_bed_cells"], 1)
        self.assertEqual(result["independent_hierarchy_checks"]["uphill_edges"], 0)
        self.assertGreater(result["independent_hierarchy_checks"]["exact_capacity_checks"], 0)
        self.assertFalse(result["hydrology_solved"])

    def test_rehashed_parent_source_or_readiness_claim_is_rejected(self):
        for field, value in (("source", self.original), ("hydrology_solved", True)):
            changed = dict(self.index)
            changed[field] = value
            write_json(self.path, changed)
            with self.assertRaisesRegex(ValueError, "contract"):
                audit(self.path, file_sha256(self.path), self.parent)

    def test_rehashed_hierarchy_volume_is_independently_rejected(self):
        with np.load(self.hierarchy["path"]) as archive:
            arrays = {name: archive[name].copy() for name in archive.files if name != "manifest"}
            metadata = json.loads(archive["manifest"].tobytes())["metadata"]
        arrays["curve_volume_m3"][-1] += 10.
        changed = dict(self.index, hierarchy=write_bundle(self.root / "changed.npz", arrays, metadata))
        write_json(self.path, changed)
        with self.assertRaises(ValueError):
            audit(self.path, file_sha256(self.path), self.parent)


if __name__ == "__main__":
    unittest.main()
