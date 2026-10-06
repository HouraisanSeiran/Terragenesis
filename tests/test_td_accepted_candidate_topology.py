import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_source import load_td_source_bundle, make_td_source, save_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_surface_reaches import _hash, _plain
from tests import test_td_accepted_water_morphology as morphology_fixture
from tools.rebuild_td_accepted_candidate_topology import publish_topology, load_topology_index


class AcceptedCandidateTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = morphology_fixture.AcceptedWaterMorphologyTests()
        cls.fixture.setUp()
        result = cls.fixture.export()
        cls.parent = dict(path=str(cls.fixture.root / "candidate/index.json"),
            expected_sha256=file_sha256(cls.fixture.root / "candidate/index.json"), expected_identity=result["identity_sha256"])
        cls.source = _plain(result["candidates"]["source_deposition"]["source"])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDown()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "topology"

    def make(self):
        return publish_topology(self.parent, self.source, self.output, candidate_id="source_deposition")

    def load(self, result):
        return load_topology_index(self.output / "index.json", expected_sha256=file_sha256(self.output / "index.json"),
            expected_identity=result["identity_sha256"], parent_record=self.parent, source_record=self.source)

    def test_actual_derived_source_chain_and_cold_no_rebuild(self):
        original_sha = file_sha256(self.fixture.source_record["path"])
        result = self.make()
        with patch("tools.rebuild_td_accepted_candidate_topology.build_basin_hierarchy", side_effect=AssertionError("cold rebuild")):
            loaded = self.load(result)
        self.assertEqual(loaded["source"], self.source)
        self.assertTrue(loaded["recoupling_required"])
        self.assertFalse(loaded["hydrology_solved"])
        self.assertEqual(file_sha256(self.fixture.source_record["path"]), original_sha)

    def test_wrong_parent_source_pins_and_candidate_rejected(self):
        for role in ("parent", "source"):
            parent, source = copy.deepcopy(self.parent), copy.deepcopy(self.source)
            target = parent if role == "parent" else source
            target["expected_identity"] = "0" * 64
            with self.assertRaises(ValueError):
                publish_topology(parent, source, self.output, candidate_id="source_deposition")
        with self.assertRaises(ValueError):
            publish_topology(self.parent, self.source, self.output, candidate_id="baseline")
        self.assertFalse(self.output.exists())

    def test_rehashed_wrong_actual_source_hierarchy_rejected(self):
        result = self.make()
        source = load_td_source_bundle(**self.source)
        bed = source["arrays"]["height_m"].copy()
        bed[0, 0] += .01
        forged = make_td_source(bed, spacing_m=30., source_sha256=source["metadata"]["source_sha256"])
        hierarchy = build_basin_hierarchy(forged)
        path = self.output / "hierarchy.npz"
        path.unlink()
        save_basin_hierarchy(path, hierarchy)
        result["hierarchy"].update(expected_sha256=file_sha256(path), expected_identity=hierarchy["identity_sha256"])
        result.pop("identity_sha256")
        result["identity_sha256"] = _hash(result)
        (self.output / "index.json").write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.load(result)

    def test_post_save_failure_has_no_final_or_staging(self):
        with patch("tools.rebuild_td_accepted_candidate_topology.load_topology_index", side_effect=ValueError("cold failed")):
            with self.assertRaises(ValueError):
                self.make()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob(".accepted-topology-*")), [])

    def test_resource_failure_and_existing_output_rejected(self):
        with patch("tools.rebuild_td_accepted_candidate_topology.memory", side_effect=MemoryError("private")):
            with self.assertRaises(MemoryError):
                self.make()
        self.assertFalse(self.output.exists())
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.make()


if __name__ == "__main__":
    unittest.main()
