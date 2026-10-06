"""Synthetic pinned IO fixtures; no hydrology execution or source generation."""

import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, file_sha256, save_bundle
from terrain_pipeline.single_domain_surface_archive import (
    _page_coverage, _validate_hour, audit_single_domain_chain,
    load_accepted_single_domain_chain, load_single_domain_index,
)
from tests import test_td_native_weather_storage_v10_io as native_fixture


class SingleDomainSurfaceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.fixture = native_fixture.NativeWeatherV10IoTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.storage = copy.deepcopy(self.fixture.storage)
        metadata = self.storage["metadata"]
        metadata.update(substep_s=.625, substeps=5760, positivity_cfl=.0125)
        metadata["parameters"]["substep_s"] = .625
        self.checkpoint = copy.deepcopy(self.fixture.checkpoint)
        self.checkpoint["metadata"] = dict(metadata, schema="td-v10-hour-checkpoint-v1")
        self.context = dict(hierarchy=self.fixture.hierarchy, rain=np.ones((24, 1, 2)),
                            forcing_identity="a"*64, step_s=.625, direction="eastward")

    def tearDown(self):
        self.fixture.tearDown()

    def _pair(self, storage=None, checkpoint=None):
        storage = self.storage if storage is None else storage
        checkpoint = self.checkpoint if checkpoint is None else checkpoint
        storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
        checkpoint["metadata"]["last_page_identity"] = storage["identity_sha256"]
        checkpoint["identity_sha256"] = identity(checkpoint["arrays"], checkpoint["metadata"])
        return storage, checkpoint

    def test_saved_0625_hour_and_compartments(self):
        storage, checkpoint = self._pair()
        budget = _validate_hour(storage, checkpoint, context=self.context, hour=0, previous=None)
        self.assertTrue(budget["budget_passed"])
        self.assertAlmostEqual(budget["rain_m3"], 1.8)

    def test_rehashed_state_cumulative_and_source_mismatch(self):
        for kind in ("state", "cumulative", "source", "coordinate", "rain", "outlet", "certification", "compartment"):
            with self.subTest(kind=kind):
                storage, checkpoint = copy.deepcopy(self.storage), copy.deepcopy(self.checkpoint)
                if kind == "state":
                    checkpoint["arrays"]["soil_mm"][0] += .1
                elif kind == "cumulative":
                    checkpoint["arrays"]["cumulative_face_forward_m3"][0] += .1
                elif kind == "source":
                    storage["arrays"]["height_m"][0, 0] += .1
                elif kind == "coordinate":
                    checkpoint["metadata"]["origin_m_xz"] = [2., 3.]
                elif kind == "rain":
                    storage["arrays"]["rain_mm_h"][0, 0] = 2.
                elif kind == "outlet":
                    storage["arrays"]["boundary_outflow_m3"][0, 0] = 1.
                elif kind == "certification":
                    storage["metadata"]["natural_outlet_verified"] = True
                else:
                    storage["arrays"]["rain_infiltration_m3"][:] = .4
                    storage["arrays"]["rain_excess_m3"][:] = .5
                storage, checkpoint = self._pair(storage, checkpoint)
                with self.assertRaises(ValueError):
                    _validate_hour(storage, checkpoint, context=self.context, hour=0, previous=None)

    def test_prior_checkpoint_all_four_states_required(self):
        storage, checkpoint = self._pair()
        for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
            with self.subTest(name=name):
                previous = {key: value.copy() for key, value in checkpoint["arrays"].items()}
                previous[name][0] += 1.
                with self.assertRaisesRegex(ValueError, "four-state"):
                    _validate_hour(storage, checkpoint, context=self.context, hour=0, previous=previous)

    def test_complete_24_hour_stream_and_whole_budget(self):
        pages = []
        for hour in range(24):
            storage, checkpoint = copy.deepcopy(self.storage), copy.deepcopy(self.checkpoint)
            storage["arrays"]["soil_mm"][:] = [[30.+hour]*2, [31.+hour]*2]
            checkpoint["arrays"]["soil_mm"][:] = 31.+hour
            for result in (storage, checkpoint):
                result["metadata"].update(forcing_hour_offset=hour, start_s=hour*3600., end_s=(hour+1)*3600.)
            storage, checkpoint = self._pair(storage, checkpoint)
            records = {}
            for role, result in (("storage", storage), ("checkpoint", checkpoint)):
                path = self.root / f"{role}-{hour}.npz"
                save_bundle(path, result, validator=lambda value: True)
                records[role] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            pages.append(dict(hour=hour, forcing_identity="a"*64, chunk_work_face_steps=5760, **records))
        acceptance = self.root / "accepted.txt"
        acceptance.write_text("synthetic fixture only", encoding="ascii")
        self.context.update(pages=pages, acceptance_record=dict(path=str(acceptance), expected_sha256=file_sha256(acceptance)))
        audit = audit_single_domain_chain(self.context)
        self.assertEqual(len(audit["hours"]), 24)
        self.assertAlmostEqual(audit["whole_period_residual_m3"], 0.)
        self.assertFalse(audit["hydraulic_ready"])
        self.assertFalse(audit["natural_outlet_verified"])
        self.assertFalse(audit["publishable"])

    def test_missing_duplicate_or_boolean_hour_rejected(self):
        pages = [dict(hour=hour) for hour in range(24)]
        for bad in (pages[:-1], pages+[dict(hour=24)], [dict(hour=False)]+pages[1:], [dict(hour=1)]+pages[1:]):
            with self.assertRaises(ValueError):
                _page_coverage(bad)

    def test_nonaccepted_pin_and_false_acceptance_rejected(self):
        with self.assertRaisesRegex(ValueError, "fixed native"):
            load_accepted_single_domain_chain(dict(expected_sha256="a"*64))
        from terrain_pipeline.single_domain_surface_archive import ACCEPTANCE_SHA256
        with patch("terrain_pipeline.single_domain_surface_archive._json", return_value=dict(
                hydraulic_ready=False, publishable=False, schema="td-independent-final-temporal-refinement-v1",
                io_chain_accepted=False, all_saved_numerical_gates_passed=True, solver_advanced=False)):
            with self.assertRaisesRegex(ValueError, "accepted temporal"):
                load_accepted_single_domain_chain(dict(expected_sha256=ACCEPTANCE_SHA256))

    def test_index_missing_direction_and_raised_flags_rejected(self):
        for index in (dict(schema="single-domain-surface-index-v1", hydraulic_ready=False, publishable=False,
                           natural_outlet_verified=False, limitations=["fixture"], directions={"eastward":{}}),
                      dict(hydraulic_ready=True, publishable=False)):
            with patch("terrain_pipeline.single_domain_surface_archive._json", return_value=index):
                with self.assertRaises(ValueError):
                    load_single_domain_index("fixture.json", expected_sha256="a"*64)

    def test_derived_path_escape_and_wrong_digest_rejected(self):
        from terrain_pipeline.single_domain_surface_archive import _derived_record
        artifact = self.root / "artifact.txt"
        artifact.write_text("fixture", encoding="ascii")
        record = dict(path=str(artifact), expected_sha256=file_sha256(artifact))
        self.assertEqual(_derived_record(record, self.root), artifact.resolve())
        inside = self.root / "published"
        inside.mkdir()
        with self.assertRaisesRegex(ValueError, "containment"):
            _derived_record(record, inside)
        with self.assertRaisesRegex(ValueError, "SHA"):
            _derived_record(dict(record, expected_sha256="a"*64), self.root)

    def test_rehashed_report_and_resource_substitution_rejected(self):
        from terrain_pipeline.single_domain_surface_archive import BUDGETS, REQUIRED_CODE_FILES
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        codes = {name:file_sha256(repo/name) for name in REQUIRED_CODE_FILES if (repo/name).exists()}
        # Publication tooling may be concurrently implemented; this test pins the required set through a mock.
        for kind in ("report_schema", "resource_schema", "report_binding", "budget", "inventory", "elapsed"):
            with self.subTest(kind=kind):
                index = dict(schema="single-domain-surface-index-v1", hydraulic_ready=False, publishable=False,
                             natural_outlet_verified=False, limitations=["synthetic fixture"],
                             directions={"eastward":dict(geometry={}, frames=[]), "westward":dict(geometry={}, frames=[])},
                             source_records={}, acceptance_record={}, code_sha256=codes)
                report = dict(index, schema="single-domain-surface-report-v1")
                resource = dict(schema="single-domain-surface-resource-v1", budgets=dict(BUDGETS), complete=True,
                                peak_rss_bytes=1, peak_private_bytes=1, output_bytes=1, elapsed_s=1., artifact_records=[])
                if kind == "report_schema":
                    report["schema"] = "other"
                elif kind == "resource_schema":
                    resource["schema"] = "other"
                elif kind == "report_binding":
                    report["source_records"] = dict(forged=True)
                elif kind == "budget":
                    resource["budgets"]["max_wall_s"] += 1
                elif kind == "inventory":
                    resource["artifact_records"] = [{}]
                else:
                    resource["elapsed_s"] = 1801.
                for role, value in (("report", report), ("resource", resource)):
                    target = self.root / f"{role}-{kind}.json"
                    target.write_text(json.dumps(value), encoding="utf-8")
                    index[role] = dict(path=str(target), expected_sha256=file_sha256(target))
                target = self.root / f"index-{kind}.json"
                target.write_text(json.dumps(index), encoding="utf-8")
                with patch("terrain_pipeline.single_domain_surface_archive.REQUIRED_CODE_FILES", set(codes)):
                    with self.assertRaises(ValueError):
                        load_single_domain_index(target, expected_sha256=file_sha256(target))


if __name__ == "__main__":
    unittest.main()
