
from terrain_pipeline.surface_identity import _plain as _merged_mosaic__plain
from builtins import ValueError as _merged_mosaic_MosaicCoverageError
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import numpy as np

from terrain_pipeline import surface_domain as mosaic
from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.surface_domain import FineGrid, _fingerprint, recover_surface_network
from terrain_pipeline.surface_domain import evaluate_surface_domains, plan_surface_domains
from terrain_pipeline.channel_geometry import ChannelRecipe, plan_channel
from tests.test_surface_domain_prepare import complete_two_domain_inputs, fine_configurations
from tests.test_surface_network_recovery import recovery_case


def engineering_proofs():
    first_case = recovery_case()
    second_case = recovery_case()
    empty = np.zeros((31, 31), bool)
    legal = empty.copy()
    legal[-1, 14:17] = True
    second_case["fine"] = FineGrid(0., 0., 2., 2., (31, 31), ~empty, empty, legal)
    first = recover_surface_network(**first_case)
    second = recover_surface_network(**second_case)
    if not first["accepted"] or not second["accepted"]:
        raise AssertionError("actual recovery fixture not accepted")
    return first, second


def positive_sources(proofs):
    return (mosaic.DomainFineSource(proofs[0], 1, (0, 61, 0, 7)),
            mosaic.DomainFineSource(proofs[1], 2, (0, 31, 3, 7)))


def wet_sources(proofs):
    return (mosaic.DomainFineSource(proofs[0], 1, (20, 61, 20, 31)),
            mosaic.DomainFineSource(proofs[1], 2, (10, 31, 15, 21)))


def build(sources, **kwargs):
    return mosaic.prepare_fine_mosaic(sources, metric_grid={"coordinate_system": "metric-xz-m"},
        vertical_datum="engineering-relative-sea-zero", source_identity="accepted-recovery-cross-precision-slice",
        sea_level_elevation_m=0., **kwargs)


def mutable(value):
    return deepcopy(_merged_mosaic__plain(value))


def rehash(value):
    value.pop("identity_sha256", None)
    value["identity_sha256"] = mosaic._identity(value)
    return value


def rehash_surface(proof):
    surface = proof["surface"]
    params = surface["identity"]["parameters"]
    params["output_sha256"] = digest({name: array_hash(array) for name, array in surface["arrays"].items()})
    params["summary_sha256"] = digest(surface["summary"])
    surface["identity_sha256"] = ArtifactIdentity(**surface["identity"]).sha256
    proof["identity_sha256"] = _fingerprint({key: child for key, child in proof.items() if key != "identity_sha256"})


def write_bundle(result, path):
    arrays = {}
    tree = mosaic._surface_fine_mosaic_tree(result, arrays)
    manifest = {"format_version": 2, "tree": tree, "tree_sha256": mosaic._identity(tree)}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", mosaic._surface_fine_mosaic_json(manifest))
        for name, array in arrays.items():
            with io.BytesIO() as stream:
                np.save(stream, np.ascontiguousarray(array), allow_pickle=False)
                archive.writestr(name, stream.getvalue())


class SurfaceFineMosaicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proofs = engineering_proofs()
        cls.sources = positive_sources(cls.proofs)
        cls.result = build(cls.sources)

    def test_continuous_cross_precision_cells_shared_nodes(self):
        result = self.result
        self.assertEqual(result["grid"]["spacing_x_m"], 1.)
        self.assertEqual(result["cells"].shape, (720, 4))
        self.assertEqual(result["triangles"].shape, (1440, 3))
        self.assertEqual(len(result["nodes"]["x_m"]), 793)
        self.assertEqual(len(set(zip(result["nodes"]["x_m"], result["nodes"]["z_m"]))), 793)
        np.testing.assert_array_equal(result["cells"][5, [1, 2]], result["cells"][6, [0, 3]])
        self.assertFalse(result["full_domain_mosaic_prepared"])
        self.assertEqual(result["summary"]["unique_cell_area_m2"], 720.)
        self.assertTrue(np.any(result["contributors"]["weights"] == .5))
        self.assertAlmostEqual(result["summary"]["q_local_m3_s"], .14)
        self.assertEqual(len(result["q_cuts"]), 1)

    def test_independent_proof_inactive_nonzero_seam_q_rejected(self):
        case = recovery_case()
        plan = case["plan"]
        arrays, params = plan["arrays"], plan["identity"]["parameters"]
        discharge = arrays["discharge_m3_s"].copy()
        discharge[0, 0] += .001
        case["plan"] = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
            arrays["outlet_mask"], discharge, 10., 10., 0., 0., 0., "independent-Q-proof",
            ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__}))
        proof = recover_surface_network(**case)
        self.assertTrue(proof["accepted"])
        with self.assertRaisesRegex(ValueError, "duplicate nonzero Q"):
            build((replace(self.sources[0], window_zx=(0, 61, 0, 11)),
                   replace(self.sources[1], proof=proof, window_zx=(0, 61, 10, 13))))

    def test_same_graph_shared_nonzero_inactive_q_counted_once(self):
        positions = np.column_stack((np.arange(13), np.zeros(13)))
        arrays = {"receiver": np.full(13, -1, np.int64), "order": np.arange(13),
                  "world_xz_m": positions, "discharge_m3_s": np.full(13, .01),
                  "local_discharge_m3_s": np.full(13, .01), "active_mask": np.zeros(13, bool),
                  "outlet_mask": np.ones(13, bool), "node_stage_m": np.zeros(13)}
        fine = {"origin_x_m": 0., "origin_z_m": 0., "spacing_x_m": 1., "spacing_z_m": 1.}
        result = {"grid": {"bbox_xz_m": [0., 12., 0., 1.]}, "q_tolerance_m3_s": 1e-8,
                  "proofs": {"first": {"inputs": {"fine": fine}}, "second": {"inputs": {"fine": fine}}},
                  "sources": [{"proof_sha256": "first", "window_zx": [0, 2, 0, 7]},
                              {"proof_sha256": "second", "window_zx": [0, 2, 6, 13]}]}
        cuts, summary = mosaic._q_cut(result, {"first": arrays, "second": arrays})
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(summary["q_local_m3_s"], .13)
        changed = {name: array.copy() for name, array in arrays.items()}
        changed["local_discharge_m3_s"][0] += .001
        changed["discharge_m3_s"][0] += .001
        with self.assertRaisesRegex(ValueError, "duplicate nonzero Q"):
            mosaic._q_cut(result, {"first": arrays, "second": changed})

    def test_terminal_q_not_all_accumulated_nodes(self):
        result = build((mosaic.DomainFineSource(self.proofs[0], 1),))
        graph = mosaic._payload(_merged_mosaic__plain(self.proofs[0]))
        terminal = float(graph["discharge_m3_s"][graph["receiver"] < 0].sum())
        self.assertAlmostEqual(result["summary"]["q_outgoing_m3_s"], terminal)
        self.assertAlmostEqual(result["summary"]["q_local_m3_s"], terminal)
        self.assertGreater(float(graph["discharge_m3_s"].sum()), terminal)

    def test_real_wet_cross_precision_seam_and_unique_local_cut(self):
        result = build(wet_sources(self.proofs))
        self.assertEqual(result["cells"].shape, (800, 4))
        self.assertEqual(int(result["wet_cells"].sum()), 645)
        self.assertEqual(int((result["nodes"]["wet_mask"] & (result["nodes"]["x_m"] == 30)).sum()), 41)
        self.assertGreater(result["summary"]["unique_cut_volume_m3"], 90.)
        self.assertGreater(result["summary"]["actual_wet_water_volume_m3"], 220.)
        # The new path puts node 10 upstream of this window. Its .01 local
        # contribution has already joined the .1 incoming branch discharge.
        graph = mosaic._payload(_merged_mosaic__plain(self.proofs[0]))
        selected = np.array([row * 7 + col for row in range(2, 7) for col in range(2, 5)])
        local = float(graph["local_discharge_m3_s"][selected].sum())
        self.assertAlmostEqual(local, .09)
        self.assertAlmostEqual(result["summary"]["q_local_m3_s"], local)
        self.assertAlmostEqual(result["summary"]["q_outgoing_m3_s"], .2 + local)
        self.assertAlmostEqual(result["summary"]["q_incoming_m3_s"], .2)
        self.assertEqual(len(result["q_cuts"]), 1)
        self.assertTrue(mosaic.validate_fine_mosaic(result))

    def test_real_wet_cross_precision_nonmatching_seam_rejected(self):
        with self.assertRaisesRegex(ValueError, "seam conflict"):
            build((mosaic.DomainFineSource(self.proofs[0], 1, (0, 61, 20, 31)),
                   mosaic.DomainFineSource(self.proofs[1], 2, (0, 31, 15, 21))))

    def test_explicit_proof_bound_gap_extension(self):
        first, second = self.sources
        second = replace(second, window_zx=(0, 31, 4, 7))
        with self.assertRaises(_merged_mosaic_MosaicCoverageError):
            build((first, second))
        extension = mosaic.DomainFineSource(self.proofs[0], 3, (0, 61, 6, 9), role="extension")
        result = build((first, second), source_extensions=(extension,))
        self.assertEqual(int((result["cell_owner"] == 2).sum()), 120)

    def test_actual_wet_sloping_stage_is_interpolated(self):
        arrays = {"source_surface_m": np.full((2, 2), 5.), "final_surface_m": np.full((2, 2), 3.),
                  "total_cut_m": np.full((2, 2), 2.), "domain_mask": np.ones((2, 2), bool),
                  "wet_mask": np.ones((2, 2), bool), "water_surface_m": np.array([[4., 4.1], [4.2, 4.3]])}
        source = {"unknown_mask": np.zeros((2, 2), bool), "protected_mask": np.zeros((2, 2), bool)}
        values = mosaic._evaluate_support(source, arrays, np.arange(4), np.full(4, .25), 1e-8)
        self.assertTrue(values[2])
        self.assertAlmostEqual(values[3], 4.15)
        arrays["water_surface_m"][1, :] = np.nan
        arrays["wet_mask"][1, :] = False
        values = mosaic._evaluate_support(source, arrays, np.arange(4), np.array([.5, .5, 0., 0.]), 1e-8)
        self.assertTrue(values[2])
        self.assertAlmostEqual(values[3], 4.05)

    def test_real_old_domain_gap_rejected_and_retained(self):
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        prepared = evaluate_surface_domains(candidate, fine_configurations(candidate))
        with self.assertRaises(_merged_mosaic_MosaicCoverageError) as caught:
            build(prepared)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic["missing_cell_count"], 600)
        self.assertEqual(diagnostic["status"], "diagnostic")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gap.npz"
            mosaic.save_fine_mosaic(diagnostic, path, allow_unprepared=True)
            with self.assertRaises(ValueError):
                mosaic.load_fine_mosaic(path)
            loaded = mosaic.load_fine_mosaic(path, allow_unprepared=True)
            self.assertEqual(loaded["missing_cell_count"], 600)

    def test_plain_source_self_certification_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot self-certify"):
            build(({"h0_m": np.ones((2, 2)), "status": "prepared"},))

    def test_unknown_positive_weight_support_rejected(self):
        unknown = np.zeros((61, 61), bool)
        unknown[1, 1] = True
        with self.assertRaisesRegex(ValueError, "unknown"):
            build((replace(self.sources[0], unknown_mask=unknown), self.sources[1]))

    def test_protection_on_modified_actual_wet_support_rejected(self):
        protected = np.zeros((61, 61), bool)
        graph = mosaic._payload(_merged_mosaic__plain(self.proofs[0]))
        protected[tuple(np.argwhere(graph["wet_mask"])[0])] = True
        with self.assertRaisesRegex(ValueError, "protected"):
            build((mosaic.DomainFineSource(self.proofs[0], 1, protected_mask=protected),))

    def test_overlap_and_seam_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            build((self.sources[0], replace(self.sources[0], domain_id=2)))
        restriction = np.zeros((31, 31), bool)
        restriction[:, 3] = True
        with self.assertRaisesRegex(ValueError, "seam conflict"):
            build((self.sources[0], replace(self.sources[1], protected_mask=restriction)))

    def test_cancel_and_retained_resource_preflight(self):
        with self.assertRaises(InterruptedError):
            build(self.sources, cancel=lambda: True)
        with patch.object(mosaic, "_source", side_effect=AssertionError("proof allocation before preflight")):
            with self.assertRaisesRegex(ValueError, "preflight"):
                build(self.sources, resources=mosaic.MosaicResources(max_retained_bytes=100))
        with self.assertRaisesRegex(ValueError, "cell resource"):
            build(self.sources, resources=mosaic.MosaicResources(max_cells=10))

    def test_load_readonly_no_generation_or_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cells.npz"
            mosaic.save_fine_mosaic(self.result, path)
            with ExitStack() as stack:
                for name in ("_assemble", "_mesh", "_h0_support", "_stencil", "_grid", "_ownership", "prepare_fine_mosaic", "_proof_gate"):
                    stack.enter_context(patch.object(mosaic, name, side_effect=AssertionError("load generated: " + name)))
                for target in ('terrain_pipeline.surface_domain._fine_source',
                               'terrain_pipeline.surface_domain.recover_surface_network',
                               'terrain_pipeline.surface_domain.evaluate_surface_domains',
                               'terrain_pipeline.surface_domain.prepare_surface_network'):
                    stack.enter_context(patch(target, side_effect=AssertionError("load generated")))
                loaded = mosaic.load_fine_mosaic(path)
                query = mosaic.query_fine_mosaic(loaded)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            with self.assertRaises(ValueError):
                query["h0_m"].flags.writeable = True
            with self.assertRaises(TypeError):
                loaded["status"] = "other"

    def test_atomic_no_overwrite_and_fd_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cells.npz"
            descriptors = []
            original = tempfile.mkstemp
            def track(*args, **kwargs):
                result = original(*args, **kwargs)
                descriptors.append(result[0])
                return result
            with patch.object(mosaic.tempfile, "mkstemp", side_effect=track):
                mosaic.save_fine_mosaic(self.result, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                mosaic.save_fine_mosaic(self.result, path)
            self.assertEqual(before, path.read_bytes())
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    __import__("os").fstat(descriptor)
            failed = Path(directory) / "failed.npz"
            with patch.object(mosaic.os, "link", side_effect=OSError("publication failed")):
                with self.assertRaises(OSError):
                    mosaic.save_fine_mosaic(self.result, failed)
            self.assertFalse(failed.exists())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_rehashed_contributors_mesh_q_unknown_rejected(self):
        for kind in ("weights", "mesh", "q", "unknown", "height"):
            record = mutable(self.result)
            if kind == "weights":
                record["contributors"]["weights"][0, 0] = [.5, .5, 0., 0.]
            elif kind == "mesh":
                record["triangles"][0, 0] = 2
            elif kind == "q":
                record["summary"]["q_local_m3_s"] += 1.
            elif kind == "unknown":
                record["sources"][0]["unknown_mask"][0, 0] = True
            else:
                record["nodes"]["h2_m"][0] -= .1
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "tampered.npz"
                write_bundle(rehash(record), path)
                with self.assertRaises(ValueError):
                    mosaic.load_fine_mosaic(path)

    def test_npy_payload_duplicate_zip_json_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.npz"
            mosaic.save_fine_mosaic(self.result, good)
            with zipfile.ZipFile(good) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for kind in ("truncated", "trailing", "duplicate_zip", "duplicate_json", "raw_header"):
                path = Path(directory) / (kind + ".npz")
                modified = dict(members)
                name = next(name for name in modified if name.endswith(".npy"))
                if kind == "truncated":
                    modified[name] = modified[name][:-1]
                elif kind == "trailing":
                    modified[name] += b"extra"
                elif kind == "duplicate_json":
                    modified["manifest.json"] = modified["manifest.json"].replace(b'{', b'{"format_version":2,', 1)
                elif kind == "raw_header":
                    modified[name] = b'\x93NUMPY\x01\x00\xff\xff' + b' ' * 65535
                with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as archive:
                    warnings.simplefilter("ignore")
                    for entry, payload in modified.items():
                        archive.writestr(entry, payload)
                    if kind == "duplicate_zip":
                        archive.writestr(name, modified[name])
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    mosaic.load_fine_mosaic(path)

    def test_manifest_resource_gate_precedes_numpy_allocation(self):
        for name in ("max_retained_bytes", "max_working_bytes"):
            record = mutable(self.result)
            record["resources"][name] = 100
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "resource.npz"
                write_bundle(rehash(record), path)
                with patch.object(mosaic.np, "load", side_effect=AssertionError("allocated before resource gate")):
                    with self.assertRaisesRegex(ValueError, "resource preflight"):
                        mosaic.load_fine_mosaic(path)

    def test_coherently_rehashed_original_budget_and_source_stage_rejected(self):
        for kind in ("area", "volume", "depth", "stage"):
            record = mutable(self.result)
            old_identity = record["sources"][0]["proof_sha256"]
            proof = record["proofs"].pop(old_identity)
            support = record["proof_h0_support"].pop(old_identity)
            if kind == "stage":
                wet = proof["surface"]["arrays"]["wet_mask"]
                proof["surface"]["arrays"]["water_surface_m"][wet] += .01
            else:
                name = {"area": "max_area_m2", "volume": "max_cut_volume_m3", "depth": "max_bed_cut_m"}[kind]
                proof["inputs"]["budget"][name] = 0.
                proof["surface"]["identity"]["parameters"][name] = 0.
            rehash_surface(proof)
            new_identity = proof["identity_sha256"]
            record["proofs"][new_identity], record["proof_h0_support"][new_identity] = proof, support
            record["sources"][0]["proof_sha256"] = new_identity
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "coherent.npz"
                write_bundle(rehash(record), path)
                with self.assertRaises(ValueError):
                    mosaic.load_fine_mosaic(path)


if __name__ == "__main__":
    unittest.main()
