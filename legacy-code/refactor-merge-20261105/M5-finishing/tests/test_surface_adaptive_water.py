import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle
from terrain_pipeline.adaptive_mesh import build_adaptive_geometry
from terrain_pipeline.adaptive_mesh import _bundle
from terrain_pipeline.adaptive_mesh import build_adaptive_water_frame, validate_bound_adaptive_water_frame, load_consumer_adaptive_frame
from tests.test_single_domain_fine_geometry import fixture


class AdaptiveWaterTests(unittest.TestCase):
    def setUp(self):
        _, self.bed = fixture()
        canonical = self.bed["arrays"]["H2_m"]
        requested = np.full(canonical.shape, 4, np.int64)
        requested[:4, :4] = 1
        self.geometry = build_adaptive_geometry(canonical, requested,
            origin_m_xz=self.bed["metadata"]["origin_m_xz"])
        a = self.geometry["arrays"]
        stage = canonical.max()+.25-self.geometry["metadata"]["hydraulic_datum_m"]
        depth = stage-(canonical-self.geometry["metadata"]["hydraulic_datum_m"])
        mean = np.bincount(a["canonical_owner"].ravel(), weights=depth.ravel())/a["leaf_area_m2"]
        record = dict(state=np.column_stack((mean, np.zeros((len(mean), 2)))),
            geometry_identity=self.geometry["identity_sha256"], time_s=30.,
            leaf_counts=self.geometry["metadata"]["leaf_counts"], leaf_area_m2=self.geometry["metadata"]["leaf_area_m2"],
            leaf_stage_relative_m=np.full(len(mean), stage), canonical_depth_m=depth,
            canonical_momentum_m2_s=np.zeros((*depth.shape, 2)),
            **{name: a[name].copy() for name in ("leaf_row", "leaf_column", "leaf_spacing_m", "canonical_owner")})
        self.snapshot = _bundle(record, "surface-adaptive-canonical-snapshot-v1")

    def test_mixed_leaf_inventory_fan_preserves_each_canonical_volume(self):
        frame = build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=1)
        np.testing.assert_allclose(frame["arrays"]["cell_volume_m3"], self.snapshot["arrays"]["canonical_depth_m"], atol=1e-10)
        self.assertEqual(frame["metadata"]["adaptive_snapshot_identity"], self.snapshot["identity_sha256"])
        self.assertEqual(frame["metadata"]["leaf_count"], 240)
        self.assertEqual(frame["metadata"]["omitted_wet_cell_count"], 0)

    def test_resigned_snapshot_and_frame_source_substitution_rejected(self):
        frame = build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=1)
        changed = copy.deepcopy(self.snapshot)
        changed["arrays"]["canonical_depth_m"][0, 0] += .1
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_bound_adaptive_water_frame(frame, self.bed, changed, self.geometry)
        changed_frame = copy.deepcopy(frame)
        changed_frame["metadata"]["adaptive_snapshot_identity"] = "a"*64
        changed_frame["identity_sha256"] = identity(changed_frame["arrays"], changed_frame["metadata"])
        with self.assertRaises(ValueError):
            validate_bound_adaptive_water_frame(changed_frame, self.bed, self.snapshot, self.geometry)

    def test_public_consumer_loads_relocated_sources_and_rejects_frame_order(self):
        frame = build_adaptive_water_frame(self.bed, self.snapshot, self.geometry, state_index=0)
        geometry = _bundle(dict(self.geometry["arrays"], raw_geometry_metadata=self.geometry["metadata"],
            raw_geometry_identity=self.geometry["identity_sha256"]), "surface-adaptive-geometry-v1")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)/"source"
            source.mkdir()
            artifacts = []
            for name, bundle in (("bed.npz", self.bed), ("snapshot.npz", self.snapshot), ("geometry.npz", geometry), ("frame.npz", frame)):
                target = source/name
                save_bundle(target, bundle, validator=lambda value:True)
                artifacts.append(dict(path=name, sha256=file_sha256(target), identity_sha256=bundle["identity_sha256"]))
            moved = Path(temporary)/"moved"
            shutil.move(str(source), str(moved))
            context = dict(manifest=dict(backend="adaptive-saved-canonical-fan", artifacts=artifacts,
                scenarios=dict(test=dict(geometry="bed.npz", frames=[dict(frame=0, time_s=30., artifact="frame.npz",
                    snapshot="snapshot.npz", adaptive_geometry="geometry.npz")]))),
                allowlist={item["path"]:moved/item["path"] for item in artifacts})
            loaded = load_consumer_adaptive_frame(context, scenario="test", frame_index=0)
            self.assertFalse(loaded["solver_advanced"])
            self.assertEqual(loaded["frame"]["identity_sha256"], frame["identity_sha256"])
            context["manifest"]["scenarios"]["test"]["frames"][0]["time_s"] = 60.
            with self.assertRaises(ValueError):
                load_consumer_adaptive_frame(context, scenario="test", frame_index=0)


if __name__ == "__main__":
    unittest.main()
