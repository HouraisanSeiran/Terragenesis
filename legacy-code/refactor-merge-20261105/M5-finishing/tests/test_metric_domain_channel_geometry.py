import unittest

import numpy as np

from terrain_pipeline.channel_geometry import build_domain_channel_geometry, validate_domain_channel_geometry
from terrain_pipeline.channel_geometry import GeometryConfig
from tests.test_metric_channel_geometry import terrain


def inputs():
    source = terrain()
    shape = source.elevation_m.shape
    ids = np.array([29, 31, 32], np.int64)
    receiver = np.full(source.elevation_m.size, -1, np.int64)
    receiver[ids[:-1]] = ids[1:]
    topology = {"height_m": source.elevation_m, "accepted": np.ones(shape, bool),
                "owner_outlet_x_m": np.full(shape, 20.),
                "owner_outlet_z_m": np.full(shape, 12.),
                "ocean_terminal": np.ones(shape, bool), "receiver": receiver.reshape(shape)}
    options = dict(node_cell_ids=ids, receiver=np.array([1, 2, -1]),
                   width_m=np.full(3, 2.), depth_m=np.full(3, .5),
                   owner_xz_m=np.tile([20., 12.], (3, 1)), owner_grid=np.zeros(shape, np.int64),
                   corridor_mask=np.ones(shape, bool), lake_mask=np.zeros(shape, bool),
                   anchor_mask=np.zeros(3, bool), outlet_x_m=20., outlet_z_m=12.,
                   terminal_kind="ocean", config=GeometryConfig(fine_spacing_m=.5))
    return source, topology, options


class DomainChannelGeometryTests(unittest.TestCase):
    def test_three_node_chain_with_terminal_builds_and_validates(self):
        source, topology, options = inputs()
        record = build_domain_channel_geometry(source, topology, **options)
        self.assertTrue(validate_domain_channel_geometry(record))
        np.testing.assert_array_equal(record["arrays"]["channel_receiver"], [1, 2, -1])
        self.assertEqual(record["metadata"]["node_count"], 3)

    def test_actual_link_crossing_owner_is_refused(self):
        source, topology, options = inputs()
        options["owner_grid"].ravel()[31] = 1
        with self.assertRaisesRegex(ValueError, "receiver crosses domain ownership"):
            build_domain_channel_geometry(source, topology, **options)
