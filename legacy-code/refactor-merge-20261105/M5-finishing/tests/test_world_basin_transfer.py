import unittest

from terrain_pipeline.surface_hydraulics import transfer_basins


def item(label, local, capacity, downstream=None, complete=True):
    return {"label": label, "local_m3": local, "capacity_m3": capacity,
            "downstream": downstream, "destination": "lake" if downstream is not None else "ocean",
            "complete": complete}


class BasinTransferTest(unittest.TestCase):
    def test_partial_retention_and_global_balance(self):
        result = transfer_basins([item(1, 10., 4., 2), item(2, 2., 10.)])
        self.assertEqual(result[1]["outflow_m3"], 6.)
        self.assertEqual(result[2]["stored_m3"], 8.)
        self.assertEqual(result[2]["outflow_m3"], 0.)
        self.assertEqual(12., result[1]["stored_m3"] + result[2]["stored_m3"] + result[2]["outflow_m3"])

    def test_pending_target_keeps_known_upstream_input(self):
        result = transfer_basins([item(1, 10., 4., 2), item(2, 2., 10., complete=False)])
        self.assertEqual(result[2]["inflow_m3"], 8.)
        self.assertIsNone(result[2]["stored_m3"])
        self.assertEqual(12., result[1]["stored_m3"] + result[2]["inflow_m3"])

    def test_cycle_does_not_affect_independent_basin(self):
        result = transfer_basins([item(1, 2., 1., 2), item(2, 3., 1., 1), item(3, 5., 2.)])
        self.assertFalse(result[1]["complete"])
        self.assertFalse(result[2]["complete"])
        self.assertEqual(result[3]["stored_m3"], 2.)
        self.assertEqual(result[3]["outflow_m3"], 3.)
        self.assertEqual(10., result[1]["inflow_m3"] + result[2]["inflow_m3"] + result[3]["stored_m3"] + result[3]["outflow_m3"])


if __name__ == "__main__":
    unittest.main()
