import unittest
from types import SimpleNamespace
import numpy as np
from terrain_pipeline.channel_geometry import formative_section
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry


class FormativeSectionTest(unittest.TestCase):
    def section(self, q=10., bed=.5, bank=.5, fracture=0., cohesion=0., **kw):
        return formative_section(q, bed, bank, fracture, cohesion, max_width_m=1000., **kw)

    def test_material_and_flow(self):
        base = self.section().width_m
        self.assertGreater(self.section(q=20).width_m, base)
        self.assertGreater(self.section(fracture=1).width_m, base)
        self.assertLess(self.section(cohesion=1).width_m, base)
        self.assertLess(self.section(bank=.9).width_m, base)
        self.assertGreater(self.section(bed=.9).width_m, base)
        self.assertIsNone(self.section().deposited_solid_m3)

    def test_finite_exchange_and_unknown(self):
        a = self.section(sediment_supply_solid_m3=5, transport_capacity_solid_m3=10, erodible_solid_m3=2)
        b = self.section(sediment_supply_solid_m3=15, transport_capacity_solid_m3=10, erodible_solid_m3=2)
        self.assertEqual(a.eroded_solid_m3, 2)
        self.assertEqual(b.deposited_solid_m3, 5)
        self.assertGreater(a.width_m, a.baseline_width_m)
        self.assertLess(b.width_m, b.baseline_width_m)
        with self.assertRaises(ValueError):
            self.section(sediment_supply_solid_m3=0)

    def test_geometry_consumes_section(self):
        shape = (12, 12)
        z, x = np.indices(shape)
        mesh = SimpleNamespace(node_x_m=x.ravel(), node_z_m=z.ravel(), origin_native_xz=(0, 0), spacing_m=1.)
        rec = np.full(x.size, -1, dtype=np.int64)
        rec[65] = 70
        mask = np.zeros(shape, bool)
        mask.ravel()[65] = True
        args = (np.full(shape, 10.), np.ones(shape), mask, mesh, rec)
        low = build_irregular_channel_geometry(*args, formative_section_inputs=dict(fracture=0., bank_cohesion=1.))
        high = build_irregular_channel_geometry(*args, formative_section_inputs=dict(fracture=1., bank_cohesion=0.))
        self.assertGreater(high['graph']['node_width_m'][65], low['graph']['node_width_m'][65])
        self.assertGreater(high['arrays']['cut_depth_m'].sum(), low['arrays']['cut_depth_m'].sum())


if __name__ == '__main__':
    unittest.main()
