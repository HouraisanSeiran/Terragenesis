"""The default-value registry must match live behaviour, and identity must be stable.

``environment_defaults`` registers every hard-coded environment default so that drift
in the module that actually owns the literal shows up as a test failure. Each test
below therefore does not restate the number: it reads the number back out of the live
behaviour (a dataclass field, an exported ``PARAMETERS`` dict, or the ``parameters``
block a ``step`` reports for its own defaults) and compares it with the registry entry.

Three groups of assertions, one per thing that can go wrong silently:

* ``DefaultValueTests``    -- the registry entry and the live default agree;
* ``DefaultIdentityTests`` -- registry id / keys / metadata are stable, units stay in
  the declared vocabulary and the pinned flag tracks the sha-index;
* ``DefaultRejectionTests``-- illegal values are still refused by the module that owns
  the literal, so a registry entry can never certify a value the live code rejects.
"""
from dataclasses import fields
import importlib
import ast
import inspect
import json
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline import environment_contract as contract
from terrain_pipeline import environment_contract as registry
from terrain_pipeline.environment_processes import aeolian_initialize
from terrain_pipeline.environment_processes import frozen_ground_initialize as frozen_initialize
from terrain_pipeline.environment_processes import radiation_initialize
from terrain_pipeline.environment_processes import volcanism_initialize
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters

# sha-index of the refactor baseline: the source of the ``pinned`` flag.
SHA_INDEX = Path(".scratch/algorithm-refactor-20261105/r0/sha-index.json")

UNITS = {"mm/h", "mm", "m", "s", "day", "mm/day", "mm/day/degC", "degC", "degC/m", "W/m2",
         "1", "J/m3", "J/m2/K", "W/m2/K", "1/m", "m2/s", "m/s", "s/m", "s/m^(1/3)", "kg/m3",
         "deg", "m/s2"}


def context():
    """Small closed basin: every node drains, no ocean, unit spacing."""
    rr, cc = np.indices((5, 5))
    height = 4. - cc + .1 * rr
    ocean = np.zeros((5, 5), bool)
    mesh = build_mesh(height.shape, origin_native_xz=(0, 0), spacing_m=1., world_seed=20261020)
    receiver, _, _ = strict_receivers(height, mesh, outlet_mask=ocean)
    return {"height_m": height, "receiver": receiver.reshape(height.shape), "ocean_mask": ocean,
            "river_mask": np.ones(height.shape, bool), "valid_mask": np.ones(height.shape, bool),
            "protected_mask": np.zeros(height.shape, bool), "origin_native_xz": [0, 0],
            "spacing_m": 1., "world_seed": 20261020}


def step_parameters(stepper, initialize):
    """The ``parameters`` block a process reports for its own defaults."""
    ctx = context()
    return stepper(initialize(ctx), {}, ctx, 1.)["metadata"]["parameters"]


def fields_of(cls):
    return {field.name: field.default for field in fields(cls)}


def pin_count(source_file):
    entry = json.loads(SHA_INDEX.read_text(encoding="utf-8"))["sources"][source_file]
    return entry["pin_files_count"]


class DefaultValueTests(unittest.TestCase):
    """Each registry entry equals the live default of the module that owns the literal."""

    def test_runoff_entries_match_runoff_parameters(self):
        live = fields_of(RunoffParameters)
        expected = {
            "runoff.infiltration_capacity_mm_h": "infiltration_capacity_mm_h",
            "runoff.soil_capacity_mm": "soil_capacity_mm",
            "runoff.potential_et_mm_h": "potential_et_mm_h",
            "runoff.percolation_mm_h": "percolation_mm_h",
            "runoff.fast_tau_s": "fast_tau_s",
            "runoff.slow_tau_s": "slow_tau_s",
            "runoff.initial_soil_mm": "initial_soil_mm",
        }
        self.assertEqual(len(registry.group("runoff")), len(expected))
        for key, attribute in expected.items():
            self.assertEqual(registry.get(key), live[attribute], key)

    def test_runoff_does_not_inherit_the_seasonal_soil_capacity(self):
        # Two live copies of a soil bucket: 150 mm here, 120 mm in SeasonalConfig.
        # The registry keeps them apart rather than picking one.
        self.assertNotEqual(registry.get("runoff.soil_capacity_mm"),
                            fields_of(SeasonalConfig)["soil_capacity_mm"])
        self.assertIn("differs from seasonal.soil_capacity_mm",
                      registry.DEFAULTS["runoff.soil_capacity_mm"].note)

    def test_seasonal_entries_match_seasonal_config(self):
        live = fields_of(SeasonalConfig)
        self.assertEqual(registry.get("seasonal.soil_capacity_mm"), live["soil_capacity_mm"])
        self.assertEqual(registry.get("seasonal.soil_drainage_days"), live["soil_drainage_days"])
        self.assertEqual(registry.get("seasonal.climate_noise_scale_m"), live["climate_noise_scale_m"])

    def test_pet_entries_match_both_copies(self):
        from terrain_pipeline.soil_water import PetEtParameters
        seasonal, pet = fields_of(SeasonalConfig), fields_of(PetEtParameters)
        base = registry.get("pet.base_mm_per_day")
        slope = registry.get("pet.temperature_mm_per_day_c")
        self.assertEqual(base, seasonal["pet_base_mm_per_day"])
        self.assertEqual(base, pet["pet_base_mm_per_day"])
        self.assertEqual(slope, seasonal["pet_temperature_mm_per_day_c"])
        self.assertEqual(slope, pet["pet_temperature_mm_per_day_c"])
        self.assertEqual(registry.get("pet.freezing_threshold_c"), pet["freezing_threshold_c"])

    def test_lapse_rate_matches_noise_climate_parameters(self):
        from terrain_pipeline.climate_forcing import NoiseClimateParameters
        self.assertEqual(registry.get("climate.lapse_rate_c_per_m"),
                         fields_of(NoiseClimateParameters)["lapse_rate_c_per_m"])

    def test_radiation_entries_match_step_defaults(self):
        from terrain_pipeline import environment_processes as radiation
        live = step_parameters(radiation.radiation_step, radiation_initialize)
        for short, live_value in live.items():
            self.assertEqual(registry.group("radiation")[short], live_value, short)
        # ``albedo`` is a forcing default, not a step parameter.
        self.assertEqual(len(registry.group("radiation")), len(live) + 1)
        self.assertIn("albedo", registry.group("radiation"))

    def test_radiation_albedo_is_the_forcing_default(self):
        from terrain_pipeline import environment_processes as radiation
        ctx = context()
        observed = registry.get("radiation.albedo")
        self.assertEqual(observed, 0.2, "registry says 0.2; the forcing default must match")
        # Local noon on the equator: the sun is up, so incident (and absorbed) energy is
        # positive and the albedo is observable from the absorbed-energy ratio.
        forcing = {"latitude_deg": 0., "longitude_deg": 0., "time_s": 43200.}
        state = radiation.radiation_initialize(ctx)
        baseline = radiation.radiation_step(state, forcing, ctx, 1.)["fluxes"]["absorbed_shortwave_w_m2"]
        self.assertGreater(float(baseline.max()), 0.)
        doubled = radiation.radiation_step(state, dict(forcing, albedo=2. * observed),
                                 ctx, 1.)["fluxes"]["absorbed_shortwave_w_m2"]
        # Absorbed = incident * (1 - albedo): the default albedo is recoverable from the
        # ratio without reading source text.
        np.testing.assert_allclose(doubled, baseline * (1. - 2. * observed) / (1. - observed),
                                   rtol=0., atol=1e-12)

    def test_frozen_ground_entries_match_step_defaults(self):
        from terrain_pipeline import environment_processes as frozen
        live = step_parameters(frozen.frozen_ground_step, frozen_initialize)
        self.assertEqual(registry.get("frozen.latent_heat_j_m3"), float(frozen.LATENT_J_M3))
        for short, live_value in live.items():
            self.assertEqual(registry.group("frozen")[short], live_value, short)
        self.assertEqual(len(registry.group("frozen")), len(live) + 1)

    def test_aeolian_entries_match_step_defaults(self):
        from terrain_pipeline import environment_processes as aeolian
        self.assertEqual(registry.group("aeolian"), step_parameters(aeolian.aeolian_step, aeolian_initialize))

    def test_volcanism_entries_match_step_defaults(self):
        from terrain_pipeline import environment_processes as volcanism
        self.assertEqual(registry.group("volcanism"), step_parameters(volcanism.volcanism_step, volcanism_initialize))

    def test_succession_entries_match_the_module_parameters(self):
        from terrain_pipeline import environment_processes as succession
        roughness = registry.group("succession")
        self.assertEqual(set(roughness), {"bare_manning_n", "vegetated_manning_increment"})
        for short, value in roughness.items():
            self.assertEqual(value, succession.SUCCESSION_PARAMETERS[short], short)
        self.assertLess(roughness["bare_manning_n"], roughness["vegetated_manning_increment"])
        self.assertGreater(roughness["bare_manning_n"], 0.)

    def test_process_parameter_sources_are_live_dicts(self):
        for name, path in registry.PROCESS_PARAMETER_SOURCES.items():
            module_name, attribute = path.rsplit(".", 1)
            module = importlib.import_module("terrain_pipeline." + module_name)
            self.assertIsInstance(getattr(module, attribute), dict, name)
        from terrain_pipeline import environment_processes as coastal
        self.assertEqual(registry.get("coastal.bed_porosity"), coastal.COASTAL_EXCHANGE_PARAMETERS["porosity"])

    def test_regolith_porosity_matches_the_weathering_declaration(self):
        from terrain_pipeline import soil_water as weathering
        declared = weathering.normalize_parameters(None)["regolith_porosity"]
        self.assertEqual(registry.get("regolith.porosity"), declared["value"])
        # The same number appears as the coastal bed porosity: two copies, both kept.
        self.assertEqual(registry.get("regolith.porosity"), registry.get("coastal.bed_porosity"))

    def test_land_cover_entry_matches_land_cover_parameters(self):
        from terrain_pipeline.soil_water import LandCoverParameters
        self.assertEqual(registry.get("land_cover.available_water_fraction"),
                         fields_of(LandCoverParameters)["available_water_fraction"])

    def test_mass_and_groundwater_entries_match_the_step_constants(self):
        # These literals sit inline inside ``step`` (1800 and 9.80665 even share one
        # expression), so the live value is read from source text rather than a symbol.
        self.assertEqual(registry.group("mass"), {"bulk_density_kg_m3": 1800.,
                                                 "repose_angle_deg": 34.,
                                                 "gravity_m_s2": 9.80665})
        self.assertEqual(registry.group("groundwater"), {"specific_yield": .2,
                                                       "aquifer_base_depth_m": 10.})
        from terrain_pipeline import environment_processes
        mass_source = ast.unparse(ast.parse(inspect.getsource(environment_processes.mass_step)))
        self.assertIn("1800.0 * 9.80665", mass_source)
        self.assertIn("'repose_angle_deg', 34.0", mass_source)
        groundwater_source = ast.unparse(ast.parse(inspect.getsource(environment_processes.groundwater_step)))
        self.assertIn("'specific_yield', 0.2", groundwater_source)
        self.assertIn("height - 10.0", groundwater_source)


class DefaultIdentityTests(unittest.TestCase):
    """The registry's own identity and metadata may not drift silently."""

    def test_registry_identity_is_stable(self):
        self.assertEqual(registry.REGISTRY_ID, "environment-defaults-v1")
        self.assertEqual(contract.REGISTRY_ID, registry.REGISTRY_ID)

    def test_the_contract_module_also_carries_the_registry(self):
        # M3-D: environment_defaults is folded into environment_contract. Both modules are
        # importable while the old file still exists, so the registry is compared by value
        # (identical ids, keys, entries and reports) rather than by object identity.
        for name in ("DEFAULTS", "Default", "get", "group", "describe", "REGISTRY_ID",
                     "PROCESS_PARAMETER_SOURCES"):
            self.assertTrue(hasattr(contract, name), name)
        self.assertEqual(contract.REGISTRY_ID, registry.REGISTRY_ID)
        self.assertEqual(list(contract.DEFAULTS), list(registry.DEFAULTS))
        for key, entry in registry.DEFAULTS.items():
            # Two copies of the class exist while both modules are importable, so the
            # entries are compared field by field rather than by dataclass identity.
            other = contract.DEFAULTS[key]
            for attribute in ("value", "unit", "source", "status", "pinned", "note"):
                self.assertEqual(getattr(other, attribute), getattr(entry, attribute), (key, attribute))
        self.assertEqual(contract.PROCESS_PARAMETER_SOURCES, registry.PROCESS_PARAMETER_SOURCES)
        self.assertEqual(contract.describe(), registry.describe())
        self.assertEqual(contract.get("runoff.soil_capacity_mm"), registry.get("runoff.soil_capacity_mm"))
        self.assertEqual(contract.group("runoff"), registry.group("runoff"))
        for name in ("grid", "bounded_field", "positive_parameters", "frame", "stocks", "metadata",
                     "field", "array", "prepare_mesh", "context_arrays"):
            self.assertTrue(callable(getattr(contract, name)), name)

    def test_every_entry_is_a_frozen_complete_record(self):
        prefixes = set()
        for name, entry in registry.DEFAULTS.items():
            self.assertIsInstance(entry, registry.Default, name)
            with self.assertRaises(Exception):
                entry.value = 0.  # frozen: an entry cannot be edited in place
            prefix, _, short = name.partition(".")
            self.assertTrue(prefix and short, name)
            self.assertNotIn(".", short, name)
            prefixes.add(prefix)
            self.assertIsInstance(entry.value, float, name)
            self.assertTrue(np.isfinite(entry.value), name)
            self.assertIn(entry.unit, UNITS, name)
            self.assertEqual(entry.status, "declared/uncalibrated", name)
            self.assertIn(".py", entry.source, name)
            self.assertIsInstance(entry.pinned, bool, name)
            self.assertIsInstance(entry.note, str, name)
        self.assertEqual(len(registry.DEFAULTS), 45)
        self.assertEqual(sorted(prefixes),
                         ["aeolian", "climate", "coastal", "frozen", "groundwater", "land_cover",
                          "mass", "pet", "radiation", "regolith", "runoff", "seasonal",
                          "succession", "volcanism"])

    def test_every_entry_names_an_existing_source_file(self):
        # ``source`` is ``file:symbol``; the file part must name a real module so that a
        # renamed/archived module is caught here rather than silently going stale.
        for name, entry in registry.DEFAULTS.items():
            files = [part.split(":")[0].strip() for part in entry.source.split(";")]
            for relative in files:
                candidates = [Path("terrain_pipeline") / relative,
                              Path("terrain_pipeline/surface_rivers") / relative]
                self.assertTrue(any(candidate.is_file() for candidate in candidates),
                                (name, relative))

    def test_entry_order_and_keys_are_stable(self):
        # Insertion order is part of the registry's readable identity: grouped by source
        # module, runoff first. A silent reorder means someone reshuffled the file.
        keys = list(registry.DEFAULTS)
        self.assertEqual(keys[:7], ["runoff.infiltration_capacity_mm_h", "runoff.soil_capacity_mm",
                                    "runoff.potential_et_mm_h", "runoff.percolation_mm_h",
                                    "runoff.fast_tau_s", "runoff.slow_tau_s",
                                    "runoff.initial_soil_mm"])
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(list(registry.describe()), sorted(keys))

    def test_pinned_flags_track_the_sha_index(self):
        pinned = {name for name, entry in registry.DEFAULTS.items() if entry.pinned}
        self.assertEqual(pinned, {"runoff.infiltration_capacity_mm_h", "runoff.soil_capacity_mm",
                                  "runoff.potential_et_mm_h", "runoff.percolation_mm_h",
                                  "runoff.fast_tau_s", "runoff.slow_tau_s",
                                  "runoff.initial_soil_mm", "seasonal.soil_capacity_mm",
                                  "seasonal.soil_drainage_days", "seasonal.climate_noise_scale_m",
                                  "pet.base_mm_per_day", "pet.temperature_mm_per_day_c"})
        for source_file in ('terrain_pipeline/runoff.py',
                            'terrain_pipeline/runoff.py',
                            "terrain_pipeline/environment_radiation.py",
                            "terrain_pipeline/surface_rivers/metric_pet_et.py"):
            expected = pin_count(source_file) > 0
            for entry in registry.DEFAULTS.values():
                first = entry.source.split(";")[0].split(":")[0].strip()
                if first == Path(source_file).name and ";" not in entry.source:
                    self.assertEqual(entry.pinned, expected, (source_file, entry.source))

    def test_describe_is_a_plain_copy(self):
        described = registry.describe()
        entry = registry.DEFAULTS["runoff.soil_capacity_mm"]
        self.assertEqual(described["runoff.soil_capacity_mm"],
                         {"value": entry.value, "unit": entry.unit, "source": entry.source,
                          "status": entry.status, "pinned": entry.pinned, "note": entry.note})
        # describe() must not alias the registry: editing the report leaves it intact.
        described["runoff.soil_capacity_mm"]["value"] = -1.
        self.assertEqual(registry.get("runoff.soil_capacity_mm"), 150.)

    def test_group_and_get_are_consistent(self):
        self.assertEqual(registry.get("coastal.bed_porosity"),
                         registry.group("coastal")["bed_porosity"])
        self.assertEqual(set(registry.group("pet")),
                         {"base_mm_per_day", "temperature_mm_per_day_c", "freezing_threshold_c"})
        self.assertEqual(registry.group("no-such-prefix"), {})
        self.assertEqual(registry.group("runoff."), {})
        with self.assertRaises(KeyError):
            registry.get("no.such.default")


class DefaultRejectionTests(unittest.TestCase):
    """The owning module still rejects illegal values; the registry never hides that."""

    def test_runoff_parameters_still_reject_illegal_values(self):
        for bad in ({"soil_capacity_mm": -1.}, {"soil_capacity_mm": np.nan},
                    {"fast_tau_s": 0.}, {"fast_tau_s": np.inf},
                    {"infiltration_capacity_mm_h": True}):
            with self.assertRaises(ValueError, msg=str(bad)):
                RunoffParameters(**bad)
        with self.assertRaisesRegex(ValueError, "initial soil exceeds capacity"):
            RunoffParameters(soil_capacity_mm=1.)

    def test_seasonal_config_still_rejects_illegal_values(self):
        for bad in ({"soil_capacity_mm": 0.}, {"soil_capacity_mm": -5.},
                    {"pet_base_mm_per_day": np.nan}, {"max_cells": 0}):
            with self.assertRaises(ValueError, msg=str(bad)):
                SeasonalConfig(**bad)
        with self.assertRaisesRegex(ValueError, "seasonal work budget exceeded"):
            SeasonalConfig(substeps_per_day=25)

    def test_lapse_rate_range_is_enforced(self):
        from terrain_pipeline.climate_forcing import NoiseClimateParameters
        with self.assertRaisesRegex(ValueError, "lapse rate"):
            NoiseClimateParameters(lapse_rate_c_per_m=-.02)
        with self.assertRaisesRegex(ValueError, "lapse rate"):
            NoiseClimateParameters(lapse_rate_c_per_m=.001)

    def test_step_parameter_contract_rejects_unknown_and_nonpositive(self):
        # Processes read their defaults through the shared contract validator, so the
        # registry may only claim "positive" about keys that validator accepts.
        defaults = {"a": 1., "b": 2.}
        with self.assertRaisesRegex(ValueError, "unknown process parameter"):
            contract.positive_parameters({"zz": 1.}, defaults)
        for bad in (0., -1., np.nan, np.inf):
            with self.assertRaisesRegex(ValueError, "finite and positive", msg=str(bad)):
                contract.positive_parameters({"a": bad}, defaults)
        self.assertEqual(contract.positive_parameters(None, defaults), defaults)
        # The returned mapping is a copy: the declared defaults survive a caller edit.
        returned = contract.positive_parameters({"a": 3.}, defaults)
        returned["a"] = -1.
        self.assertEqual(defaults, {"a": 1., "b": 2.})

    def test_land_cover_fraction_must_stay_below_one(self):
        from terrain_pipeline.soil_water import LandCoverParameters
        with self.assertRaisesRegex(ValueError, "available_water_fraction must be below 1"):
            LandCoverParameters(available_water_fraction=1.)
        with self.assertRaises(ValueError):
            LandCoverParameters(available_water_fraction=-.1)

    def test_pet_threshold_must_be_finite(self):
        from terrain_pipeline.soil_water import PetEtParameters
        with self.assertRaisesRegex(ValueError, "freezing_threshold_c"):
            PetEtParameters(freezing_threshold_c=np.inf)
        with self.assertRaisesRegex(ValueError, "pet_base_mm_per_day"):
            PetEtParameters(pet_base_mm_per_day=-1.)


if __name__ == "__main__":
    unittest.main()
