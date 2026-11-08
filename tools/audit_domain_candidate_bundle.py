"""Cold-read accounting audit; never generates, solves, or republishes terrain."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity, load_bundle

DEFAULT = ROOT / ".scratch/river-r7-r9-candidate-20261022"


def read_json(path):
    def reject_constant(value):
        raise ValueError("non-finite JSON: " + value)
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant,
                      object_pairs_hook=unique_pairs)


class Audit:
    def __init__(self):
        self.checks = []
        self.products = []
        self.domain_accounting = []

    def check(self, name, passed, detail=None):
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})

    def close(self, name, actual, expected):
        actual, expected = np.broadcast_arrays(np.asarray(actual), np.asarray(expected))
        error = np.abs(actual - expected)
        tolerance = 1e-5 + 1e-10 * np.maximum(np.abs(actual), np.abs(expected))
        ok = np.isfinite(actual) & np.isfinite(expected) & (error <= tolerance)
        self.check(name, np.all(ok), {"values": int(ok.size), "failed_values": int(np.count_nonzero(~ok)),
                                    "max_abs_error": float(np.max(error, initial=0.0)),
                                    "tolerance": "1e-5 + 1e-10 * max(abs(actual), abs(expected))"})

    def validate_bundle(self, result):
        if identity(result["arrays"], result["metadata"]) != result["identity_sha256"]:
            raise ValueError("content identity mismatch")
        for key, value in result["arrays"].items():
            if value.dtype.kind in "fc" and not np.isfinite(value).all():
                raise ValueError("non-finite array " + key)

    def members(self, name, arrays, metadata):
        n = metadata["domain_count"]
        offsets = arrays["cell_offsets"]
        counts = arrays["cell_count"]
        cells = np.column_stack((arrays["cells_x_m"], arrays["cells_z_m"]))
        valid = (offsets.dtype.kind in "iu" and offsets.shape == (n + 1,) and
                 counts.shape == (n,) and offsets[0] == 0 and offsets[-1] == len(cells) and
                 np.all(np.diff(offsets) == counts) and np.all(counts > 0))
        self.check(name + "/offsets", valid)
        self.check(name + "/unique_cells", len(np.unique(cells, axis=0)) == len(cells))
        outlets = np.column_stack((arrays["outlet_x_m"], arrays["outlet_z_m"]))
        self.check(name + "/unique_outlets", len(np.unique(outlets, axis=0)) == n)
        self.check(name + "/kind", np.isin(arrays["kind"], ["marine", "inland"]).all())
        spacing = metadata["spacing_m"]
        self.close(name + "/cell_area", metadata["cell_area_m2"], spacing ** 2)
        self.close(name + "/areas", arrays["area_m2"], counts * spacing ** 2)
        self.close(name + "/world_lattice", cells / spacing, np.rint(cells / spacing))
        origin = np.asarray(metadata["tile_origin_m_xz"])
        local = np.rint((cells - origin) / spacing).astype(np.int64)
        rows, columns = metadata["tile_shape"]
        self.check(name + "/tile_bounds", np.all((local >= 0) & (local < [columns, rows])))
        return local[:, 1] * columns + local[:, 0]

    def ledger(self, root, tile):
        records = {}
        for role in ("flow", "sediment", "coupled", "bed_feedback"):
            declaration = tile["ledgers"][role]
            path = root / tile["directory"] / declaration["file"]
            name = tile["directory"] + "/" + role
            record = load_bundle(path, expected_sha256=declaration["sha256"], validator=self.validate_bundle)
            records[role] = record
            a, m = record["arrays"], record["metadata"]
            self.check(name + "/identity", record["identity_sha256"] == declaration["identity_sha256"])
            self.check(name + "/declaration", all(m[k] == declaration[k] for k in ("schema", "algorithm", "domain_count", "interval_count")))
            self.check(name + "/claims", all(m["claims"].get(k) is False for k in ("hydraulic_ready", "natural_outlet_verified", "publishable")))
            self.check(name + "/declared_totals", all(m["totals"].get(k) == v for k, v in declaration["totals"].items()))
            for key in ("rain_input_m3", "actual_et_m3", "terminal_release_m3", "water_release_m3", "weathered_m3", "entrained_m3", "deposited_m3", "delivered_m3", "deposited_solid_m3", "deposited_bulk_m3", "pore_m3"):
                if key in a:
                    self.check(name + "/nonnegative/" + key, np.all(a[key] >= 0))
            flat = self.members(name, a, m)
            self.products.append({"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path),
                                  "identity_sha256": record["identity_sha256"], "domain_count": m["domain_count"]})
            if role in ("flow", "coupled"):
                release = a["terminal_release_m3"] if role == "flow" else a["water_release_m3"]
                water = a["rain_input_m3"] - a["actual_et_m3"] - a["soil_storage_change_m3"] - release
                self.close(name + "/water_per_domain", a["rain_input_m3"], a["actual_et_m3"] + a["soil_storage_change_m3"] + release)
                if role == "flow":
                    self.close(name + "/stored_water_residual", a["domain_residual_m3"], water)
                self.close(name + "/rain_total", np.sum(a["rain_input_m3"]), m["totals"]["routed_rain_m3"])
                release_key = "released_total_m3" if role == "flow" else "water_release_total_m3"
                self.close(name + "/release_total", np.sum(release), m["totals"][release_key])
                if role == "flow":
                    for key in ("actual_et_m3", "soil_storage_change_m3"):
                        self.close(name + "/" + key + "_total", np.sum(a[key]), m["totals"][key])
                rain_parts = sum(m["totals"][key] for key in ("routed_rain_m3", "ocean_direct_rain_m3", "outside_core_rain_m3", "unresolved_rain_m3"))
                self.close(name + "/requested_rain_partition", rain_parts, m["totals"]["requested_rain_m3"])
                for kind, total_key in (("marine", "exported_to_sea_m3"), ("inland", "retained_in_basins_m3")):
                    if role == "flow":
                        self.close(name + "/" + total_key, np.sum(release[a["kind"] == kind]), m["totals"][total_key])
            if role in ("sediment", "coupled"):
                source = a["weathered_m3"] - a["entrained_m3"] - a["store_change_m3"]
                routing = a["entrained_m3"] - a["deposited_m3"] - a["delivered_m3"]
                self.close(name + "/source_per_domain", a["weathered_m3"], a["entrained_m3"] + a["store_change_m3"])
                self.close(name + "/routing_per_domain", a["entrained_m3"], a["deposited_m3"] + a["delivered_m3"])
                self.close(name + "/stored_source_residual", a["source_residual_m3"], source)
                self.close(name + "/stored_routing_residual", a["routing_residual_m3"], routing)
                p = m["parameters"]
                self.close(name + "/weathering_from_parameters", a["weathered_m3"], a["area_m2"] * p["weathered_m_per_interval"] * m["interval_count"])
                for key in ("weathered", "entrained", "deposited", "delivered", "store_change"):
                    self.close(name + "/" + key + "_total", np.sum(a[key + "_m3"]), m["totals"][key + "_total_m3"])
                for kind, key in (("marine", "delivered_to_sea_m3"), ("inland", "delivered_to_basins_m3")):
                    self.close(name + "/" + key, np.sum(a["delivered_m3"][a["kind"] == kind]), m["totals"][key])
                if role == "coupled":
                    self.check(name + "/capacity", np.all(a["entrained_m3"] <= a["capacity_volume_m3"] + 1e-5))
                self.domain_accounting.append({"tile": tile["directory"], "role": role,
                    "source_residual_m3": source.tolist(), "routing_residual_m3": routing.tolist()})
            if role in ("flow", "coupled"):
                self.domain_accounting.append({"tile": tile["directory"], "role": role, "water_residual_m3": water.tolist()})
            if role == "bed_feedback":
                parent = records["coupled"]
                self.check(name + "/parent_binding", m["parent_identity_sha256"] == parent["identity_sha256"] == declaration["parent_identity_sha256"] and m["parent_schema"] == parent["metadata"]["schema"])
                self.close(name + "/parent_deposition", a["deposited_solid_m3"], parent["arrays"]["deposited_m3"])
                porosity = m["parameters"]["porosity"]
                self.check(name + "/porosity_range", 0 <= porosity < 1)
                self.close(name + "/bulk_porosity", a["deposited_bulk_m3"] * (1 - porosity), a["deposited_solid_m3"])
                self.close(name + "/pore_volume", a["pore_m3"], a["deposited_bulk_m3"] - a["deposited_solid_m3"])
                expected_change = np.repeat(a["deposited_bulk_m3"] / a["area_m2"], a["cell_count"])
                self.close(name + "/uniform_placement", a["bed_change_m"], expected_change)
                self.check(name + "/only_raises_bed", np.all(a["bed_change_m"] >= 0))
                per_domain_bulk = np.array([np.sum(a["bed_change_m"][lo:hi]) * m["cell_area_m2"] for lo, hi in zip(a["cell_offsets"][:-1], a["cell_offsets"][1:])])
                self.close(name + "/bed_integral_per_domain", per_domain_bulk, a["deposited_bulk_m3"])
                raster = np.zeros(np.prod(m["tile_shape"]))
                raster[flat] = a["bed_change_m"]
                self.close(name + "/raster_scatter", a["bed_change_raster_m"], raster)
                self.check(name + "/requires_revalidation", m["revalidation"]["needs_geometry_and_hydraulic_revalidation"] is True and m["revalidation"]["bed_rejection_applied"] is False)
                for key in ("deposited_solid", "deposited_bulk", "pore"):
                    self.close(name + "/" + key + "_total", np.sum(a[key + "_m3"]), m["totals"][key + "_total_m3"])
        f, c = records["flow"], records["coupled"]
        self.check(tile["directory"] + "/same_runoff_parameters", f["metadata"]["parameters"] == c["metadata"]["parameters"]["runoff"])
        for role, record in records.items():
            for key in ("outlet_x_m", "outlet_z_m", "kind", "cell_count", "area_m2", "cell_offsets", "cells_x_m", "cells_z_m"):
                self.check(tile["directory"] + "/same_members/" + role + "/" + key, np.array_equal(f["arrays"][key], record["arrays"][key]))
            for key in ("seed", "config_id", "spacing_m", "interval_count", "tile_shape", "tile_origin_m_xz"):
                self.check(tile["directory"] + "/same_metadata/" + role + "/" + key, f["metadata"][key] == record["metadata"][key])
        for key in ("dt_s",):
            self.check(tile["directory"] + "/same_" + key, f["metadata"][key] == c["metadata"][key])
        self.close(tile["directory"] + "/flow_coupled_release", f["arrays"]["terminal_release_m3"], c["arrays"]["water_release_m3"])
        for key in ("rain_input_m3", "actual_et_m3", "soil_storage_change_m3"):
            self.close(tile["directory"] + "/flow_coupled/" + key, f["arrays"][key], c["arrays"][key])
        return f

    def domains(self, index_path, index, flows):
        records = []
        for entry in index["domains"]:
            path = index_path.parent / entry["product"]
            a = checked_archive(path, expected_sha256=file_sha256(path))
            scalar = lambda key: a[key].item()
            metadata = {key: scalar(key) for key in ("schema", "kind", "seed", "config_id", "spacing_m", "area_m2")}
            metadata.update(bbox_origin_xz_m=a["bbox_origin_xz_m"].tolist(), raster_shape=list(a["territory_raster"].shape),
                cell_count=int(a["cells_x_m"].size), territory_raster_policy=index["territory_raster_policy"],
                identity_policy=index["identity_policy"], limitations=a["limitations"].tolist(), receiver_stored=False)
            computed = identity({k: v for k, v in a.items() if k != "identity_sha256"}, metadata)
            name = "domain/" + entry["product"]
            self.check(name + "/identity", computed == scalar("identity_sha256") == entry["identity_sha256"])
            self.check(name + "/index_fields", scalar("kind") == entry["kind"] and a["cells_x_m"].size == entry["territory_cells"] and list(a["territory_raster"].shape) == entry["raster_shape"])
            self.close(name + "/outlet", a["outlet_xz_m"], [entry["outlet_x_m"], entry["outlet_z_m"]])
            self.close(name + "/area", scalar("area_m2"), entry["area_m2"])
            self.close(name + "/cell_area", scalar("area_m2"), len(a["cells_x_m"]) * scalar("spacing_m") ** 2)
            cells = np.column_stack((a["cells_x_m"], a["cells_z_m"]))
            spacing = scalar("spacing_m")
            self.close(name + "/bbox_origin", a["bbox_origin_xz_m"], np.min(cells, axis=0))
            local = np.rint((cells - a["bbox_origin_xz_m"]) / spacing).astype(int)
            expected = np.zeros(a["territory_raster"].shape, dtype=bool)
            expected[local[:, 1], local[:, 0]] = True
            self.check(name + "/raster_membership", np.array_equal(a["territory_raster"], expected) and np.count_nonzero(expected) == len(cells))
            self.check(name + "/land_and_finite", not np.any(a["ocean_mask"][expected]) and np.isfinite(a["base_height_m"]).all())
            self.check(name + "/shared_identity", all(scalar(k) == index[k] for k in ("seed", "config_id", "spacing_m")))
            matches = []
            for flow in flows:
                f = flow["arrays"]
                selected = np.flatnonzero((f["outlet_x_m"] == entry["outlet_x_m"]) & (f["outlet_z_m"] == entry["outlet_z_m"]))
                for i in selected:
                    lo, hi = f["cell_offsets"][i:i+2]
                    matches.extend(zip(f["cells_x_m"][lo:hi].tolist(), f["cells_z_m"][lo:hi].tolist()))
            self.check(name + "/ledger_membership", set(map(tuple, cells.tolist())) == set(matches))
            self.products.append({"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path), "identity_sha256": computed,
                                  "domain_cells": len(cells), "digest_pin": "domain index pins content identity, not archive bytes"})
            records.append({k: entry[k] for k in ("outlet_x_m", "outlet_z_m", "product", "territory_cells", "identity_sha256")})
        set_metadata = {"schema": "river-domain-product-v1", "seed": index["seed"], "config_id": index["config_id"],
                        "spacing_m": index["spacing_m"], "requested_points": index["requested_points"], "domain_count": len(records), "domains": records}
        self.check("domain_index/product_set_identity", identity({}, set_metadata) == index["product_set_sha256"])
        self.check("domain_index/count", len(records) == index["domain_count"])
        self.check("domain_index/point_partition", index["accepted_points"] + index["refused_points"] == index["requested_points"] and len(index["refusals"]) == index["refused_points"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT / "bundle/bundle.json")
    parser.add_argument("--report", type=Path, default=DEFAULT / "bundle-accounting-report.json")
    args = parser.parse_args()
    bundle_path, report_path = args.bundle.resolve(), args.report.resolve()
    if report_path.exists():
        raise FileExistsError("Refusing to overwrite an existing report: " + str(report_path))
    root = bundle_path.parent
    before = {str(p.relative_to(root)): file_sha256(p) for p in root.rglob("*") if p.is_file()}
    audit = Audit()
    bundle, flows = {}, []
    try:
        bundle = read_json(bundle_path)
        flows = [audit.ledger(root, tile) for tile in bundle["tiles"]]
        index_path = ROOT / bundle["domain_products"]["index"].replace("\\", "/")
        index = read_json(index_path)
        audit.domains(index_path, index, flows)
        audit.check("bundle/domain_index_binding", bundle["domain_products"]["product_set_sha256"] == index["product_set_sha256"] and bundle["domain_products"]["domain_count"] == index["domain_count"])
        for f in flows:
            audit.check("bundle/runoff_parameters", f["metadata"]["parameters"] == bundle["runoff_parameters"])
            audit.check("bundle/run_identity", all(f["metadata"][k] == bundle[k] for k in ("seed", "config_id", "dt_s")))
    except Exception as exc:
        audit.check("cold_read_exception", False, {"type": type(exc).__name__, "message": str(exc)})
    after = {str(p.relative_to(root)): file_sha256(p) for p in root.rglob("*") if p.is_file()}
    audit.check("source_files_unchanged", before == after)
    passed = all(c["passed"] for c in audit.checks)
    report = {"schema": "domain-candidate-independent-accounting-audit-v1", "bundle": str(bundle_path.relative_to(ROOT)),
        "cold_read_chain_passed": passed, "all_phases_complete": False, "production_default_decided": False,
        "cross_tile_accumulations_certified": False,
        "scope": "Read saved artifacts only; no publisher, generator, solver, or production validator imported. Residual arrays are recomputed for every domain, not trusted from metadata.",
        "limitations": ["R7 hydraulics are not included in this bundle; geometry and hydraulic readiness are not certified.",
            "R8 uniformly redistributes deposited volume within each domain and only raises the bed; geometry and hydraulics must be recomputed, including bed rejection.",
            "Production default remains undecided; this is an unregistered candidate consumer.",
            "Cross-tile accumulated volumes are not certified; tile-clipped domain products are not whole-world domains.",
            "This audit verifies saved accounting and identities, not physical calibration, naturalness, or a rerun of the sediment/hydraulic evolution.",
            "The bundle has no external trust anchor: hashes bind the saved declarations, not original provenance."],
        "check_count": len(audit.checks), "passed_count": sum(c["passed"] for c in audit.checks),
        "checks": audit.checks, "products": audit.products, "per_domain_accounting": audit.domain_accounting,
        "domain_accounting_index": [{"tile": t["directory"], "outlet_x_m": f["arrays"]["outlet_x_m"].tolist(),
            "outlet_z_m": f["arrays"]["outlet_z_m"].tolist()} for t, f in zip(bundle.get("tiles", []), flows)],
        "input_sha256_before": before, "input_sha256_after": after}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"cold_read_chain_passed": passed, "all_phases_complete": False,
                      "checks": len(audit.checks), "passed": report["passed_count"],
                      "failures": [c for c in audit.checks if not c["passed"]],
                      "report": str(report_path.relative_to(ROOT))}, ensure_ascii=True, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
