from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle
from terrain_pipeline.surface_rivers.metric_channel_product import (
    LEGACY_SEMANTICS, make_channel_product, validate_channel_product,
)
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelForcing
from tests.test_metric_lake_channel_coupling import fixture
from tools.audit_td_river_geometry_sediment import load_geometry_water


class GeometryWaterColdLoadTests(unittest.TestCase):
    def test_saved_v1_and_v2_water_use_linked_geometry_without_rewriting(self):
        _, geometry, network, _ = fixture()
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 2)), "b" * 64)
        current = make_channel_product(network, forcing, solve_channel(network, forcing))
        legacy = deepcopy(current)
        legacy["arrays"].pop("network_receiver_distance_m")
        legacy["metadata"].update(schema="terragenesis-channel-diagnostic-v1", semantics=LEGACY_SEMANTICS)
        legacy["identity_sha256"] = identity(legacy["arrays"], legacy["metadata"])
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            validate_channel_product(legacy)
        with tempfile.TemporaryDirectory() as directory:
            for bundle in (legacy, current):
                path = Path(directory) / (bundle["metadata"]["schema"] + ".npz")
                distance = network.receiver_distance_m if bundle is legacy else None
                save_bundle(path, bundle, validator=lambda saved: validate_channel_product(
                    saved, legacy_receiver_distance_m=distance))
                pin = {"sha256": file_sha256(path), "identity_sha256": bundle["identity_sha256"]}
                with patch('terrain_pipeline.surface_hydraulics.solve_channel',
                           side_effect=AssertionError("cold load invoked solver")):
                    loaded = load_geometry_water(path, pin, geometry)
                self.assertEqual(loaded["identity_sha256"], bundle["identity_sha256"])
                self.assertEqual(file_sha256(path), pin["sha256"])
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    load_geometry_water(path, dict(pin, identity_sha256="c" * 64), geometry)

    def test_rehashed_distance_and_source_tampering_reject(self):
        _, geometry, network, _ = fixture()
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 2)), "b" * 64)
        product = make_channel_product(network, forcing, solve_channel(network, forcing))
        with tempfile.TemporaryDirectory() as directory:
            for tamper in ("distance", "source"):
                altered = deepcopy(product)
                if tamper == "distance":
                    altered["arrays"]["network_receiver_distance_m"] = network.receiver_distance_m / 2.
                    altered["arrays"]["network_bed_slope"] = network.bed_slope * 2.
                else:
                    altered["metadata"]["network_source_identity_sha256"] = "c" * 64
                altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
                path = Path(directory) / (tamper + ".npz")
                save_bundle(path, altered, validator=validate_channel_product)
                pin = {"sha256": file_sha256(path), "identity_sha256": altered["identity_sha256"]}
                with self.subTest(tamper=tamper), self.assertRaisesRegex(ValueError, "identity mismatch|receiver distance"):
                    load_geometry_water(path, pin, geometry)


if __name__ == "__main__":
    unittest.main()
