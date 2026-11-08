
from terrain_pipeline.environment_processes import inventory_totals as _merged_product_inventory_totals
import terrain_pipeline.environment_contract as _merged_patch_module_mass_context_arrays
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import environment_product as product
from terrain_pipeline import environment_processes as mass
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from terrain_pipeline.common_infra import identity
from tests.test_environment_mass_processes import rates


def fixture(coastal=False):
    rr, cc = np.indices((5, 5))
    height = 4. - cc + .1 * rr
    ocean = np.zeros((5, 5), bool)
    if coastal:
        ocean[:, -1] = True
        height[:, -1] = -1.
    mesh = build_mesh(height.shape, origin_native_xz=(0, 0), spacing_m=1., world_seed=20261020)
    receiver, _, _ = strict_receivers(height, mesh, outlet_mask=ocean)
    ctx = dict(height_m=height, receiver=receiver.reshape(height.shape), ocean_mask=ocean,
               river_mask=np.ones(height.shape, bool), valid_mask=np.ones(height.shape, bool),
               protected_mask=np.zeros(height.shape, bool), origin_native_xz=[0, 0], spacing_m=1.,
               world_seed=20261020)
    ctx["source_terminal_mask"] = receiver.reshape(height.shape) < 0
    initial = {"mass": {"bedrock_thickness_m": .1, "bed_hardness": 0.},
               "frozen_ground": {"liquid_water_m": 0., "ground_ice_m": .02, "soil_temperature_c": 0.},
               "aeolian": {"loose_solid_m3": .1},
               "succession": {"biomass_carbon_kg_m2": 1.},
               "habitat": {"population_individuals": .00001}}
    return product.initialize(ctx, initial=initial)


def forcing():
    eruption = np.zeros((5, 5))
    eruption[2, 2] = .01
    return {"rainfall_m_s": 1.e-6, "air_temperature_c": 20., "wind_x_m_s": 8.,
            "radiation": {"longitude_deg": 180.},
            "volcanism": {"lava_input_m3": eruption, "ash_input_m3": eruption, "geothermal_w_m2": 1.},
            "mass": {"weathering_parameters": rates(1.e-3), "transport_fraction_per_s": .01, "repose_angle_deg": 0.},
            "succession": {"fire_hazard_s": 1.e-5},
            "groundwater": {"lateral_conductance_m2_s": .0001, "surface_conductance_m2_s": 1.e-8},
            "coastal_exchange": {"tide_amplitude_m": .2, "tide_period_s": 7200., "wave_height_m": .5}}


class ProcessProductTests(unittest.TestCase):
    def test_storage_algorithm_header_matches_product_mode(self):
        bundle = product._pack(fixture())
        bundle["metadata"]["algorithm"] = "finite-environment-seasonal-coupling-v1"
        bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])
        with self.assertRaisesRegex(ValueError, "algorithm header/tree mismatch"):
            product._validate_bundle(bundle)

    def test_step_output_and_inputs_keep_independent_ownership(self):
        original = fixture(True)
        original_identity = product.product_identity(original)
        driving = forcing()
        result = product.advance(original, driving, 60.)
        self.assertEqual(product.product_identity(original), original_identity)
        for key, value in result["context"].items():
            if isinstance(value, np.ndarray):
                self.assertFalse(np.shares_memory(value, original["context"][key]), key)
        for name, state in result["states"].items():
            for key, value in state.items():
                self.assertFalse(np.shares_memory(value, original["states"][name][key]), name + "." + key)
        result["context"]["protected_mask"][0, 0] = True
        result["states"]["mass"]["bedrock_solid_m3"][0, 0] = 999.
        driving["volcanism"]["lava_input_m3"][:] = 999.
        self.assertEqual(product.product_identity(original), original_identity)
        self.assertEqual(result["forcing_history"][0]["declaration"]["volcanism"]["lava_input_m3"][0, 0], 0.)

    def test_actual_all_process_consumers_and_coupled_budgets(self):
        original = fixture(True)
        unchanged = deepcopy(original)
        result = product.advance(original, forcing(), 60.)
        self.assertEqual(set(result["results"]), set(product.MODULES) | {"mass", "groundwater", "network_transition"})
        for residual in result["last_budget"].values():
            self.assertAlmostEqual(residual, 0., places=8)
        self.assertGreater(result["results"]["radiation"]["ledger"]["absorbed_j"], 0.)
        self.assertGreater(result["results"]["mass"]["fluxes"]["weathered_solid_m3"].sum(), 0.)
        self.assertGreater(result["results"]["frozen_ground"]["fluxes"]["thawed_water_m"].sum(), 0.)
        self.assertGreater(result["last_transfers"]["river_to_coast_water_m3"].sum(), 0.)
        self.assertGreater(result["last_transfers"]["soil_nutrient_to_plant_kg"].sum(), 0.)
        self.assertGreater(result["results"]["habitat"]["ledger"]["gross_migration_individuals"], 0.)
        self.assertEqual(result["results"]["network_transition"]["metadata"]["status"], "committed_separate_revision")
        np.testing.assert_array_equal(original["context"]["height_m"], unchanged["context"]["height_m"])
        for name in original["states"]:
            for key in original["states"][name]:
                np.testing.assert_array_equal(original["states"][name][key], unchanged["states"][name][key])

    def test_split_save_cold_load_resume_matches_and_hash_rejection(self):
        first = product.advance(fixture(), forcing(), 60.)
        direct = product.advance(first, forcing(), 60.)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "product.npz"
            digest = product.save_product(first, path)
            with patch.object(product, "advance", side_effect=AssertionError("cold read advanced")), patch.object(_merged_patch_module_mass_context_arrays, "context_arrays", side_effect=AssertionError("cold read generated graph")):
                loaded = product.load_product(path, expected_sha256=digest)
                queried = product.query_product(loaded, 2, 2)
                self.assertEqual(queried["time_s"], 60.)
                self.assertFalse(loaded["context"]["height_m"].flags.writeable)
            resumed = product.advance(loaded, forcing(), 60.)
            self.assertEqual(product.product_identity(first), product.product_identity(loaded))
            for name in direct["states"]:
                for key in direct["states"][name]:
                    np.testing.assert_array_equal(direct["states"][name][key], resumed["states"][name][key])
            self.assertEqual(direct["last_budget"], resumed["last_budget"])
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                product.load_product(path, expected_sha256="0" * 64)
            with self.assertRaises(FileExistsError):
                product.save_product(first, path)
            code = ("from terrain_pipeline.environment_product import load_product,query_product; "
                    f"p=load_product({str(path)!r},expected_sha256={digest!r}); "
                    "assert query_product(p,2,2)['time_s']==60.")
            subprocess.run([str(Path(__file__).resolve().parents[1] / "runtime/venv/Scripts/python.exe"), "-B", "-c", code], check=True)

    def test_window_export_is_not_ocean_and_rain_partition_is_single_supply(self):
        source = fixture()
        source["context"]["external_receiver_mask"][:, -1] = True
        source["states"]["groundwater"]["surface_water_m3"][:, -1] = .01
        source["initial_inventory"] = _merged_product_inventory_totals(source)
        result = product.advance(source, {"rainfall_m_s": .001}, 1.)
        self.assertFalse(result["context"]["ocean_mask"].any())
        self.assertGreater(result["cumulative_ledger"]["window_water_export_m3"], 0.)
        transfers = result["last_transfers"]
        np.testing.assert_allclose(sum(transfers[key] for key in ("rain_to_soil_m3", "rain_to_aquifer_m3", "rain_to_frozen_m3", "rain_to_runoff_m3")), transfers["rainfall_m3"])
        for residual in result["last_budget"].values():
            self.assertAlmostEqual(residual, 0., places=8)

    def test_leached_solutes_remain_inside_patch_and_coupled_inputs_refused(self):
        source = product.initialize(fixture()["context"], initial={"soil_chemistry": {"salinity_kg_m3": 1.}})
        result = product.advance(source, {"soil_chemistry": {"drainage_m3_s": .001}}, 60.)
        self.assertGreater(result["pending_packets"]["subsurface_salt_kg"].sum(), 0.)
        self.assertGreater(result["pending_packets"]["subsurface_nutrient_kg"].sum(), 0.)
        self.assertEqual(result["cumulative_ledger"]["salt_boundary_export_kg"], 0.)
        self.assertEqual(result["cumulative_ledger"]["nutrient_boundary_export_kg"], 0.)
        for residual in result["last_budget"].values():
            self.assertAlmostEqual(residual, 0., places=8)
        with self.assertRaisesRegex(ValueError, "internally coupled"):
            product.advance(source, {"groundwater": {"recharge_m3": 1.}}, 1.)
