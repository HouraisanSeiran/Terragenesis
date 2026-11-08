"""Differential tests: environment_contract must equal the three older contract modules."""
from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline import environment_contract as new
from terrain_pipeline import environment_contract as old_ctx
from terrain_pipeline import environment_contract as old_eco
from terrain_pipeline import environment_contract as old_proc
from tests.test_environment_process_product import fixture


def outcome(function, *args, **kwargs):
    try:
        return ("ok", function(*deepcopy(args), **deepcopy(kwargs)))
    except Exception as error:  # the exception type and message are part of the contract
        return ("err", type(error), str(error))


def same(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return (isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.dtype == b.dtype
                and a.shape == b.shape and np.array_equal(a, b, equal_nan=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


class ContractEquivalence(unittest.TestCase):
    def check(self, old, newer, *args, **kwargs):
        a, b = outcome(old, *args, **kwargs), outcome(newer, *args, **kwargs)
        self.assertTrue(same(a, b), (old.__name__, args, a, b))
        return a

    def test_mesh_results_are_identical_objects_by_value(self):
        ctx = fixture()["context"]
        for order in ("sorted", "stable"):
            a = old_ctx.prepare_mesh(deepcopy(ctx), ctx["height_m"].shape, edge_order=order)
            b = new.prepare_mesh(deepcopy(ctx), ctx["height_m"].shape, edge_order=order)
            self.assertEqual(type(a), type(b))
            for key in a.__dataclass_fields__:
                self.assertTrue(same(getattr(a, key), getattr(b, key)), (order, key))

    def test_grid_matches_old_process_contract(self):
        ctx = fixture()["context"]
        bad_height = deepcopy(ctx)
        bad_height["height_m"] = bad_height["height_m"].copy()
        bad_height["height_m"][0, 0] = np.nan
        big = dict(ctx, height_m=np.zeros((600, 600)))
        zero_spacing = dict(ctx, spacing_m=0.)
        masks = dict(ctx, protected_mask=np.eye(5, dtype=bool))
        for context in (ctx, bad_height, big, zero_spacing, masks):
            for dt in (1., 0., -1., np.nan, np.inf):
                self.check(old_proc.grid, new.grid, context, dt)

    def test_bounded_field_matches(self):
        for value, shape, lo, hi in ((1., (3, 3), None, None), (np.nan, (3, 3), None, None),
                                      (-1., (3, 3), 0., None), (2., (3, 3), None, 1.),
                                      (np.ones(4), (3, 3), None, None), (np.ones((3, 3)), (3, 3), 0., 1.)):
            self.check(old_proc.bounded_field, new.bounded_field, value, shape, "x", lo, hi)

    def test_positive_parameters_match(self):
        defaults = {"a": 1., "b": 2.}
        for parameters in (None, {}, {"a": 3.}, {"c": 1.}, {"a": 0.}, {"a": np.nan}, {"a": -1.}):
            self.check(old_proc.positive_parameters, new.positive_parameters, parameters, defaults)

    def test_frame_matches_including_zero_dt_and_bad_masks(self):
        ctx = fixture()["context"]
        variants = [ctx]
        for name in ("valid_mask", "protected_mask", "ocean_mask", "river_mask"):
            variants.append(dict(ctx, **{name: ctx[name].astype(int)}))
            variants.append(dict(ctx, **{name: ctx[name][:2]}))
        variants.append(dict(ctx, world_seed=-1))
        variants.append(dict(ctx, world_seed=True))
        variants.append(dict(ctx, origin_native_xz=[0.5, 0.]))
        variants.append(dict(ctx, origin_native_xz=[0, 0, 0]))
        variants.append(dict(ctx, receiver=ctx["receiver"].astype(float)))
        variants.append(dict(ctx, receiver=ctx["receiver"] + 100))
        variants.append(dict(ctx, spacing_m=-1.))
        for context in variants:
            for dt in (0., 1., -1., np.nan):
                self.check(old_eco.frame, new.frame, context, dt)

    def test_stocks_and_metadata_match(self):
        shape = (5, 5)
        state = {"a": np.ones(shape), "b": -np.ones(shape), "c": np.full(shape, np.nan), "d": np.ones((2, 2))}
        for names in (("a",), ("a", "b"), ("c",), ("d",), ("zz",), ()):
            for signed in ((), ("b",)):
                self.check(old_eco.stocks, new.stocks, state, names, shape, signed=signed)
        self.check(old_eco.stocks, new.stocks, [1], ("a",), shape)
        ctx = fixture()["context"]
        for dt in (1., 0.):
            self.check(old_eco.metadata, new.metadata, "alg", ctx, dt, ["l1"], {"p": 1.})

    def test_field_and_array_match(self):
        shape = (3, 3)
        mapping = {"ok": 1., "neg": -1., "nan": np.nan, "bad": np.ones(5), "grid": np.ones(shape)}
        for name in ("ok", "neg", "nan", "bad", "grid", "missing"):
            for nonnegative in (True, False):
                self.check(old_ctx.field, new.field, mapping, name, shape, nonnegative=nonnegative)
        self.check(old_ctx.field, new.field, mapping, "missing", shape, 2.)
        for value in (1., -1., np.nan, np.ones(5), np.ones(shape)):
            for nonnegative in (True, False):
                self.check(old_ctx.array, new.array, value, shape, "x", nonnegative=nonnegative)

    def test_context_arrays_match(self):
        ctx = fixture()["context"]
        bad_receiver = dict(ctx, receiver=ctx["receiver"] + 100)
        no_seed = {k: v for k, v in ctx.items() if k != "world_seed"}
        for context in (ctx, bad_receiver, no_seed, dict(ctx, spacing_m=0.)):
            for dt in (1., 0., -1., np.nan):
                a, b = outcome(old_ctx.context_arrays, context, dt), outcome(new.context_arrays, context, dt)
                self.assertEqual(a[0], b[0])
                if a[0] == "err":
                    self.assertEqual(a[1:], b[1:])
                else:
                    self.assertTrue(same(self._plain(a[1]), self._plain(b[1])), (dt,))

    @staticmethod
    def _plain(value):
        # context_arrays may return objects holding a mesh; compare their public numeric content
        if isinstance(value, tuple):
            return tuple(ContractEquivalence._plain(v) for v in value)
        if hasattr(value, "__dataclass_fields__"):
            return {k: ContractEquivalence._plain(getattr(value, k)) for k in value.__dataclass_fields__}
        if isinstance(value, dict):
            return {k: ContractEquivalence._plain(v) for k, v in value.items()}
        return value

    def test_contract_has_expected_surface(self):
        for name in ("grid", "bounded_field", "positive_parameters", "frame", "stocks", "metadata",
                     "field", "array", "prepare_mesh", "context_arrays"):
            self.assertTrue(callable(getattr(new, name)), name)
        self.assertEqual(new.CONTRACT_ID, "environment-array-contract-v1")


if __name__ == "__main__":
    unittest.main()
