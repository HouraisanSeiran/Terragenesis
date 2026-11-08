import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_distributary import FluvialDistributaryConfig, prepare_marine_transition, simulate_fluvial_distributary
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary
from tools.verify_fluvial_distributary import audit_archive, geometry_evidence, save_archive, synthetic_input


class DistributaryArchiveTests(unittest.TestCase):
    def fixture(self,path):
        terrain,boundary,forcing,source,raw = synthetic_input()
        result = simulate_fluvial_distributary(terrain,boundary,forcing,FluvialDistributaryConfig())
        save_archive(path,terrain,boundary,forcing,result,source,raw)
        return result

    def test_independent_cell_material_and_bed_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            result = self.fixture(path)
            self.assertGreater(result["source_eroded_solid_m3"].sum(),0.)
            with patch("terrain_pipeline.surface_rivers.metric_fluvial_distributary.simulate_fluvial_distributary",side_effect=AssertionError("generator called")):
                report = audit_archive(path)
            self.assertTrue(report["passed"])
            self.assertFalse(report["geometry"]["old_task14_cover_only_gate"])

    def test_source_inventory_bed_escrow_and_flux_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            self.fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                original = {key:archive[key].copy() for key in archive.files}
            for key in ("source_bulk","source_solid","source_eroded_bulk_m3","derived_base_bed_m","storage","escrow","beds_m","water","edge_volumes"):
                a = {name:value.copy() for name,value in original.items()}
                a[key].flat[0] += 1.
                bad = Path(directory)/(key+".npz")
                np.savez_compressed(bad,**a)
                with self.subTest(key=key),self.assertRaises((ValueError,AssertionError)):
                    audit_archive(bad)

    def test_shared_port_and_branch_path_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            self.fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                a = {key:archive[key].copy() for key in archive.files}
            meta = json.loads(str(a["metadata_json"].item()))
            meta["channel_paths"][-1]["branches"][1][0][0] += 1
            a["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"port.npz"
            np.savez_compressed(bad,**a)
            with self.assertRaises(ValueError):
                audit_archive(bad)

    def test_preparation_full_archive_and_supply_remainder_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            t,b,f,s,raw = synthetic_input()
            bed = t.elevation_m.copy()
            bed[b.initial_ocean_mask] -= 3.
            t = TerrainGrid(bed,t.valid_mask,0.,0.,5.,5.,"diagnostic_dem_proxy","SYNTHETIC-prepared","a"*64)
            prep = prepare_marine_transition(t,b,(20,5),radius_m=150.,slope_m_per_m=.02,maximum_raise_m=5.,maximum_fill_bulk_m3=500000.,supplied_solid_m3=325000.)
            self.assertGreater(prep["initial_cover_solid_m3"].sum(),0.)
            result = simulate_fluvial_distributary(t,b,f,FluvialDistributaryConfig(branch_landward_distance_m=15.),initial_cover_solid_m3=prep["initial_cover_solid_m3"])
            path = Path(directory)/"prepared.npz"
            save_archive(path,t,b,f,result,s,raw,prep)
            self.assertTrue(audit_archive(path)["passed"])
            with np.load(path,allow_pickle=False) as archive:
                a = {key:archive[key].copy() for key in archive.files}
            meta = json.loads(str(a["metadata_json"].item()))
            meta["preparation_ledger"]["unplaced_solid_m3"] += 1.
            a["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"supply.npz"
            np.savez_compressed(bad,**a)
            with self.assertRaises(AssertionError):
                audit_archive(bad)

    def test_zero_water_closed_material_cut_forgery_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            t,b,f,s,raw = synthetic_input()
            f = (replace(f[0],water_volume_m3=0.,sediment_solid_m3=0.),)
            result = simulate_fluvial_distributary(t,b,f,FluvialDistributaryConfig())
            path = Path(directory)/"zero.npz"
            save_archive(path,t,b,f,result,s,raw)
            self.assertTrue(audit_archive(path)["passed"])
            with np.load(path,allow_pickle=False) as archive:
                a = {key:archive[key].copy() for key in archive.files}
            cell = (20,5)
            for key in ("source_bulk","source_solid","escrow"):
                a[key][(0,)+cell] = 1.
            for key in ("source_eroded_bulk_m3","source_eroded_solid_m3","unresolved_solid_m3"):
                a[key][cell] = 1.
            for key in ("derived_base_bed_m","final_bed_m"):
                a[key][cell] -= 1./25.
            a["height_delta_m"][cell] -= 1./25.
            a["beds_m"][(0,)+cell] -= 1./25.
            meta = json.loads(str(a["metadata_json"].item()))
            for ledger in (meta["solid_ledger"],meta["interval_ledgers"][0]["solid"]):
                ledger.update(source_eroded_bulk_m3=1.,source_eroded_solid_m3=1.,unresolved_solid_m3=1.)
            a["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"cut.npz"
            np.savez_compressed(bad,**a)
            with self.assertRaises(ValueError):
                audit_archive(bad)

    def test_geometry_rejects_unincised_bed_and_insufficient_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            self.fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                arrays = {key:archive[key].copy() for key in archive.files if key != "metadata_json"}
                meta = json.loads(str(archive["metadata_json"].item()))
            flat = {key:value.copy() for key,value in arrays.items()}
            flat["beds_m"][:] = 0.
            self.assertFalse(geometry_evidence(flat,meta)["sourcecut_continuous_distributary_bed"])
            close = json.loads(json.dumps(meta))
            for paths in close["channel_paths"][-3:]:
                paths["branches"][1] = paths["branches"][0]
            self.assertFalse(geometry_evidence(arrays,close)["sourcecut_continuous_distributary_bed"])


if __name__ == "__main__":
    unittest.main()
