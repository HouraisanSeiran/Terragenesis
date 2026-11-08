from pathlib import Path
import unittest

from terrain_pipeline.regional_surface_source import load_source
from tools.verify_regional_source_network import export_network


class RegionalNetworkTests(unittest.TestCase):
    def test_actual_edge_partition_and_uphill_diagnostics(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-source/run-20261001T095258008789Z'
        source = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        network = export_network(source)
        self.assertEqual(network['channel_cells'], 1583)
        self.assertEqual(network['covered_channel_edges'], 1578)
        self.assertEqual(network['H0_uphill_channel_edges'], 520)
        self.assertAlmostEqual(network['max_H0_channel_uphill_m'], 13.0069580078125)
        self.assertTrue(all(not segment['hydraulic_connectivity_certified'] for segment in network['segments']))
        self.assertTrue(all(0 not in segment['static_lake_ids'] for segment in network['segments']))
        self.assertEqual(len({segment['id'] for segment in network['segments']}), len(network['segments']))


if __name__ == '__main__':
    unittest.main()
