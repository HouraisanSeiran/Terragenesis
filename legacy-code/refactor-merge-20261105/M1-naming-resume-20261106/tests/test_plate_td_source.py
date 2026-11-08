import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.plate_td_conditioning import WORLD_SEED, make_plate_factory
from terrain_pipeline.tectonic import TectonicConfig, evolve
from terrain_pipeline.tectonic import freeze, save_product
from terrain_pipeline.tectonic import prepare_plate_source as prepare, read_plate_source as read_product


class PlateConditioningTests(unittest.TestCase):
    def test_portable_fixture_overlap_reconstruction_and_rejection(self):
        config = TectonicConfig(shape=(12, 16), plate_count=4, steps=3,
                                origin_x_m=-80000., origin_z_m=-60000.)
        product = freeze(config, evolve(config))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.npz"
            save_product(product, path)
            factory = make_plate_factory(path, product.identity, WORLD_SEED, PhysicalGenerationConfig())
            whole = factory.sample_raw(-2, -2, 3, 3)
            np.testing.assert_array_equal(whole[:, 1:4, 1:4], factory.sample_raw(-1, -1, 2, 2))
            for z in reversed(range(-2, 3)):
                for x in reversed(range(-2, 3)):
                    np.testing.assert_array_equal(whole[:, z + 2, x + 2], factory.sample_raw(x, z, x + 1, z + 1)[:, 0, 0])
            with self.assertRaises(ValueError):
                make_plate_factory(path, "0" * 64, WORLD_SEED, PhysicalGenerationConfig())
            with self.assertRaises(ValueError):
                make_plate_factory(path, product.identity, WORLD_SEED + 1, PhysicalGenerationConfig())
            with self.assertRaises(ValueError):
                factory.sample_raw(-100, 0, -99, 1)
            code = ("import numpy as np,sys; from diffusion.plate_td_conditioning import make_plate_factory,WORLD_SEED; "
                    "from diffusion.physical_config import PhysicalGenerationConfig; "
                    "a=make_plate_factory(sys.argv[1],sys.argv[2],WORLD_SEED,PhysicalGenerationConfig()).sample_raw(-2,-2,3,3); "
                    "np.save(sys.argv[3],a)")
            dest = Path(directory) / "fresh.npy"
            subprocess.run([sys.executable, "-c", code, str(path), product.identity, str(dest)], check=True)
            np.testing.assert_array_equal(whole, np.load(dest))

    def test_direct_cli_help_and_conditioning_bounds(self):
        from diffusion.plate_td_conditioning import conditioning_footprint
        result = subprocess.run([sys.executable, "tools/prepare_plate_td_source.py", "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--expected-plate-identity", result.stdout)
        self.assertIn("--generate", result.stdout)
        self.assertEqual(conditioning_footprint((-495, -289), 913), [-48, -48, 64, 64])
        # low=-33 intersects tile [-96,-32); low=-32 excludes it exactly.
        self.assertEqual(conditioning_footprint((-21 * 256, -20 * 256), 1),
                         [-96, -48, 16, 16])

    def test_backend_refuses_insufficient_ram_before_worker(self):
        from diffusion.plate_td_backend import generate
        from diffusion.world_layout_backend import BudgetExceeded
        from types import SimpleNamespace
        with patch("diffusion.plate_td_backend.make_plate_factory") as factory, \
             patch("psutil.virtual_memory", return_value=SimpleNamespace(available=1)), \
             patch("multiprocessing.get_context") as context:
            with self.assertRaises(BudgetExceeded):
                generate("source", (0, 0), 1, PhysicalGenerationConfig(), expected_identity="a" * 64)
            context.assert_not_called()



if __name__ == "__main__":
    unittest.main()
