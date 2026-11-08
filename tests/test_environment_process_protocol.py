"""The init/step protocol must return exactly what the legacy process modules return."""
from copy import deepcopy
from importlib import import_module
import unittest

import numpy as np

from terrain_pipeline import environment_processes as protocol
from tests.test_environment_process_product import fixture, forcing

DT = 60.


def process_forcing(name):
    base = deepcopy(forcing())
    driving = dict(base.get(name, {}))
    if name == "radiation":
        driving["time_s"] = 0.
    if name == "volcanism":
        driving.update(wind_x_m_s=base["wind_x_m_s"], wind_z_m_s=0.)
    if name == "aeolian":
        driving.update(wind_x_m_s=base["wind_x_m_s"], wind_z_m_s=0.)
    if name == "network_transition":
        driving["bed_change_m"] = np.zeros((5, 5))
    return driving


def same(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return (isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.dtype == b.dtype
                and a.shape == b.shape and np.array_equal(a, b, equal_nan=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    try:
        return a == b or (a != a and b != b)
    except Exception:
        return False


class ProtocolEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = fixture()

    def legacy(self, name):
        module, _, stepper, takes_parameters = protocol.PROCESSES[name]
        return getattr(import_module("terrain_pipeline." + module), stepper), takes_parameters

    def test_every_process_step_equals_legacy_step(self):
        for name in protocol.PROCESSES:
            with self.subTest(process=name):
                ctx = deepcopy(self.product["context"])
                arrays = deepcopy(self.product["states"][name])
                stepper, takes_parameters = self.legacy(name)
                driving = process_forcing(name)
                args = (deepcopy(arrays), deepcopy(driving), deepcopy(ctx), DT)
                expected = stepper(*args, None) if takes_parameters else stepper(*args)
                state = protocol.State(name, deepcopy(arrays), {"init": {}, "step": None})
                new_state, ledger = protocol.step(state, deepcopy(ctx), deepcopy(driving), DT)
                self.assertTrue(same(expected["state"], new_state.arrays))
                self.assertTrue(same(expected.get("fluxes", {}), new_state.last_fluxes))
                self.assertTrue(same(expected.get("metadata", {}), new_state.last_metadata))
                # the input state object and arrays are not modified by the protocol
                self.assertTrue(same(arrays, state.arrays))
                self.assertIs(type(ledger), protocol.Ledger)

    def test_ledger_classifies_every_legacy_key_exactly_once(self):
        for name in protocol.PROCESSES:
            with self.subTest(process=name):
                ctx = deepcopy(self.product["context"])
                stepper, takes_parameters = self.legacy(name)
                driving = process_forcing(name)
                args = (deepcopy(self.product["states"][name]), deepcopy(driving), ctx, DT)
                expected = stepper(*args, None) if takes_parameters else stepper(*args)
                legacy = expected["ledger"]
                state = protocol.State(name, deepcopy(self.product["states"][name]), {"init": {}, "step": None})
                _, ledger = protocol.step(state, deepcopy(ctx), deepcopy(driving), DT)
                groups = (ledger.stocks_before, ledger.stocks_after, ledger.fluxes_in,
                          ledger.fluxes_out, ledger.residual)
                seen = [key for group in groups for key in group]
                self.assertEqual(len(seen), len(set(seen)), "a key was classified twice")
                self.assertEqual(set(seen) - set(ledger.derived), set(legacy))
                self.assertEqual(set(ledger.units), set(seen))
                for group in groups:
                    for key, value in group.items():
                        if key not in ledger.derived:
                            self.assertEqual(value, float(legacy[key]), key)
                for key in legacy:
                    if "residual" in key:
                        self.assertIn(key, ledger.residual)
                self.assertEqual(ledger.max_abs_residual(),
                                 max((abs(v) for v in ledger.residual.values()), default=0.))

    def test_radiation_residual_is_the_only_derived_entry(self):
        derived = {}
        for name in protocol.PROCESSES:
            state = protocol.State(name, deepcopy(self.product["states"][name]), {"init": {}, "step": None})
            _, ledger = protocol.step(state, deepcopy(self.product["context"]), process_forcing(name), DT)
            if ledger.derived:
                derived[name] = ledger.derived
        self.assertEqual(derived, {"radiation": ("energy_residual_j",)} if derived else {})
        if derived:
            self.assertLess(abs(self.radiation_residual()), 1.e-6)

    def radiation_residual(self):
        state = protocol.State("radiation", deepcopy(self.product["states"]["radiation"]),
                               {"init": {}, "step": None})
        _, ledger = protocol.step(state, deepcopy(self.product["context"]), process_forcing("radiation"), DT)
        return ledger.residual["energy_residual_j"]

    def test_init_equals_legacy_initializer(self):
        ctx = self.product["context"]
        for name, (module, initializer, _, _) in protocol.PROCESSES.items():
            with self.subTest(process=name):
                legacy_init = getattr(import_module("terrain_pipeline." + module), initializer)
                try:
                    expected = legacy_init(deepcopy(ctx))
                except TypeError:
                    self.skipTest("initializer needs explicit arguments")
                state = protocol.init(name, deepcopy(ctx))
                self.assertEqual(state.process, name)
                self.assertTrue(same(expected, state.arrays))

    def test_protocol_rejects_bad_requests(self):
        ctx = self.product["context"]
        with self.assertRaises(ValueError):
            protocol.init("not_a_process", ctx)
        with self.assertRaises(ValueError):
            protocol.init("mass", ctx, {"other": {}})
        state = protocol.State("groundwater", deepcopy(self.product["states"]["groundwater"]),
                               {"init": {}, "step": {"x": 1.}})
        with self.assertRaises(ValueError):
            protocol.step(state, deepcopy(ctx), {}, DT)


if __name__ == "__main__":
    unittest.main()
