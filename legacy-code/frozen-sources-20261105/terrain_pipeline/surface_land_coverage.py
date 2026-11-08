"""Explicit half-pixel land coverage and uniquely cropped engineering outlets."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline import surface_coast_drop as coast
from terrain_pipeline import surface_engineering_prepare as engineering


VERSION = "surface-land-coverage-v1"
INTERPRETATION = "clamped_engineering_interpretation"
MAX_BYTES = 128 * 1024 * 1024
SOURCE_ID = "381e60743e03cee6859c5cce46cb6337c8ea601ed5eb4cc1258e18cf51092860"


@dataclass(frozen=True)
class CoverageResources:
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES
    max_archive_members: int = 2048

    def __post_init__(self):
        for name, ceiling in (("max_retained_bytes", MAX_BYTES), ("max_working_bytes", MAX_BYTES),
                              ("max_archive_members", 2048)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid coverage resource: " + name)


def _cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError("land coverage cancelled")


def _preflight(source, resources):
    if not isinstance(resources, CoverageResources):
        raise ValueError("CoverageResources required")
    retained = coast._retained(source) + 10011 * 600 + 19600 * 64 + 2 * 64 * 256
    if retained > resources.max_retained_bytes or retained * 3 > resources.max_working_bytes:
        raise ValueError("coverage generated retained/working preflight")
    return retained


def _source_gate(source):
    engineering.validate_surface_engineering(source)
    if source["identity_sha256"] != SOURCE_ID:
        raise ValueError("fixed frozen engineering bundle required")
    inputs = source["evaluation"]["candidate"]["inputs"]
    if (list(source["domain_ids"]) != [1, 2] or inputs["height_m"].shape != (9, 16) or
            tuple(source["domain_mosaic"]["grid"]["bbox_xz_m"]) != (10., 140., 10., 70.) or
            inputs["origin_x_m"] != 0. or inputs["origin_z_m"] != 0. or
            inputs["spacing_x_m"] != 10. or inputs["spacing_z_m"] != 10.):
        raise ValueError("unsupported fixed land source geometry")


def _topology():
    rows, columns = np.indices((70, 140))
    first = (rows * 141 + columns).ravel()
    cells = np.column_stack((first, first + 1, first + 142, first + 141)).astype(np.int64)
    triangles = np.empty((19600, 3), np.int64)
    triangles[0::2] = cells[:, [0, 1, 2]]
    triangles[1::2] = cells[:, [0, 2, 3]]
    return cells, triangles


def _algebra(source):
    inputs = source["evaluation"]["candidate"]["inputs"]
    mesh = source["domain_mosaic"]
    xz = np.column_stack((np.tile(np.arange(5., 146.), 71), np.repeat(np.arange(5., 76.), 141)))
    clamped = np.column_stack((np.clip(xz[:, 0], 10., 140.), np.clip(xz[:, 1], 10., 70.)))
    coordinates = clamped / 10.
    left = np.floor(coordinates[:, 0]).astype(np.int64)
    top = np.floor(coordinates[:, 1]).astype(np.int64)
    fraction_x = coordinates[:, 0] - left
    fraction_z = coordinates[:, 1] - top
    indices = np.column_stack((top * 16 + left, top * 16 + left + 1,
                               (top + 1) * 16 + left, (top + 1) * 16 + left + 1))
    weights = np.column_stack(((1 - fraction_x) * (1 - fraction_z), fraction_x * (1 - fraction_z),
                               (1 - fraction_x) * fraction_z, fraction_x * fraction_z))
    positive = weights > 0
    valid_land = inputs["valid_mask"].ravel()[indices] & inputs["land_mask"].ravel()[indices]
    protected_support = inputs["protected_mask"].ravel()[indices]
    if np.any(positive & ~valid_land):
        raise ValueError("positive interpolation support is not valid land")
    h0 = (inputs["height_m"].ravel()[indices] * weights).sum(axis=1)
    protected = np.any(positive & protected_support, axis=1)
    h2 = h0.copy()
    water = np.zeros(10011)
    wet = np.zeros(10011, bool)
    old_ids = (np.arange(5, 66)[:, None] * 141 + np.arange(5, 136)[None, :]).ravel()
    if not np.allclose(h0[old_ids], mesh["nodes"]["h0_m"], atol=1e-12, rtol=0):
        raise ValueError("original candidate H0 differs from interior source")
    for target, name in ((h0, "h0_m"), (h2, "h2_m"), (water, "water_surface_m"),
                         (wet, "wet_mask"), (protected, "protected_mask")):
        target[old_ids] = mesh["nodes"][name]
    strip_domain = np.zeros(10011, np.int64)
    bank = np.zeros(10011, bool)
    for domain_id, drop in zip((1, 2), source["drops"]):
        bed = drop["arrays"]["bed_xyz_m"].reshape(21, 4, 3)
        drop_water = drop["arrays"]["water_xyz_m"].reshape(21, 4, 3)
        left_x = 38 if domain_id == 1 else 108
        if not np.array_equal(bed[:, :, 0], np.tile(np.arange(left_x, left_x + 4), (21, 1))):
            raise ValueError("actual outlet strip mismatch")
        for station in range(6):
            node_ids = (65 + station) * 141 + np.arange(left_x - 5, left_x - 1)
            if station == 0:
                if (not np.array_equal(h2[node_ids], bed[0, :, 1]) or
                        not np.array_equal(water[node_ids], drop_water[0, :, 1]) or not np.all(wet[node_ids])):
                    raise ValueError("original row70 does not match actual full-width drop")
            else:
                h2[node_ids] = bed[station, :, 1]
                water[node_ids] = drop_water[station, :, 1]
                wet[node_ids] = True
            strip_domain[node_ids] = domain_id
        bank_x = np.array([35, 36, 37, 42, 43]) + (domain_id - 1) * 70
        original_bank_ids = 65 * 141 + bank_x - 5
        delta = h0[original_bank_ids] - h2[original_bank_ids]
        for station in range(1, 6):
            node_ids = (65 + station) * 141 + bank_x - 5
            h2[node_ids] = h0[node_ids] - delta * (1 - station / 5.)
            bank[node_ids] = True
    cells, triangles = _topology()
    interior = np.zeros((70, 140), bool)
    interior[5:65, 5:135] = True
    interior = interior.ravel()
    owners = np.tile(np.where(np.arange(140) < 70, 1, 2), 70).astype(np.int64)
    if not np.array_equal(owners[interior], mesh["hydrologic_domain_owner"].ravel()):
        raise ValueError("interior domain ownership changed")
    old_to_land = old_ids[mesh["triangles"]]
    if not np.array_equal(triangles[np.repeat(interior, 2)], old_to_land):
        raise ValueError("interior triangle topology changed")
    nodes = {"xz_m": xz, "h0_m": h0, "h2_m": h2, "water_surface_m": water,
             "wet_mask": wet, "protected_mask": protected}
    audit = {"clamped_xz_m": clamped, "indices": indices, "weights": weights, "positive_mask": positive,
             "valid_land_support": valid_land, "protected_support": protected_support,
             "interior_node_ids": old_ids, "interior_cell_mask": interior,
             "engineering_strip_domain": strip_domain, "dry_cut_bank_mask": bank}
    outside = []
    for domain_id, drop in zip((1, 2), source["drops"]):
        left_x = 38 if domain_id == 1 else 108
        bed = drop["arrays"]["bed_xyz_m"][20:]
        drop_water = drop["arrays"]["water_xyz_m"][20:]
        source_triangles = drop["arrays"]["triangles"][30:]
        boundary_ids = 70 * 141 + np.arange(left_x - 5, left_x - 1)
        outside.append({"domain_id": domain_id, "source_drop_sha256": drop["identity_sha256"],
                        "source_node_ids": np.arange(20, 84, dtype=np.int64),
                        "source_triangle_ids": np.arange(30, 120, dtype=np.int64),
                        "bed_xyz_m": bed, "water_xyz_m": drop_water, "triangles": source_triangles - 20,
                        "shared_land_node_ids": boundary_ids.astype(np.int64),
                        "terminal_q_m3_s": drop["attachment"]["terminal_q_m3_s"]})
    return nodes, cells, triangles, owners, audit, outside


def _ledger(nodes, cells, triangles, audit, outside):
    cut = nodes["h0_m"] - nodes["h2_m"]
    if (np.any(~np.isfinite(cut)) or np.min(cut) < -1e-10 or np.max(cut) > 4. + 1e-10 or
            np.any(nodes["protected_mask"] & (cut > 1e-10)) or
            np.any(nodes["wet_mask"] & (nodes["water_surface_m"] < nodes["h2_m"] - 1e-10)) or
            np.any(nodes["water_surface_m"][~nodes["wet_mask"]] != 0)):
        raise ValueError("land cut/depth/protection/water violation")
    volumes = (cut[triangles].mean(axis=1) * .5).reshape(-1, 2).sum(axis=1)
    inner = float(volumes[audit["interior_cell_mask"]].sum())
    outer = float(volumes[~audit["interior_cell_mask"]].sum())
    if outer > 100. + 1e-9:
        raise ValueError("outer land cut budget exceeded: " + str(outer))
    wet_cells = np.all(nodes["wet_mask"][cells], axis=1)
    wet_triangles = triangles[np.repeat(wet_cells, 2)]
    water_volume = float(((nodes["water_surface_m"] - nodes["h2_m"])[wet_triangles].mean(axis=1) * .5).sum())
    outside_water = 0.
    for outlet in outside:
        outside_water += float(((outlet["water_xyz_m"][:, 1] - outlet["bed_xyz_m"][:, 1])[
            outlet["triangles"]].mean(axis=1) * .5).sum())
    return {"land_area_m2": 9800., "interior_area_m2": 7800., "outer_land_area_m2": 2000.,
            "outside_attachment_area_m2": 90., "interior_cut_volume_m3": inner,
            "outer_cut_volume_m3": outer, "land_cut_volume_m3": inner + outer,
            "land_static_water_volume_m3": water_volume, "outside_static_water_volume_m3": outside_water,
            "max_cut_depth_m": float(cut.max()), "outer_cut_budget_m3": 100.,
            "land_static_wet_cells": int(wet_cells.sum()), "source_dynamic_wet_cells": 676,
            "cut_depth_limit_m": 4., "static_terminal_q_sum_m3_s": sum(item["terminal_q_m3_s"] for item in outside)}


def prepare_surface_land_coverage(source, *, resources=CoverageResources(), cancel=None):
    """Generate only the fixed clamped engineering footprint; no natural certification."""
    if cancel is not None and not callable(cancel):
        raise ValueError("callable cancel required")
    _cancel(cancel)
    _preflight(source, resources)
    _source_gate(source)
    _cancel(cancel)
    nodes, cells, triangles, owners, audit, outside = _algebra(source)
    ledger = _ledger(nodes, cells, triangles, audit, outside)
    result = {"algorithm_version": VERSION, "status": "prepared", "interpretation": INTERPRETATION,
              "source": source, "source_identity_sha256": source["identity_sha256"], "resources": asdict(resources),
              "grid": {"bbox_xz_m": [5., 145., 5., 75.], "shape_nodes_zx": [71, 141], "spacing_m": 1.},
              "nodes": nodes, "cells": cells, "triangles": triangles, "domain_owner": owners,
              "audit": audit, "outside_outlets": outside, "ledger": ledger,
              "land_pixel_footprint_represented": True, "natural_outlets_certified": False,
              "general_cross_precision": False, "dynamic_fine": False, "ready_for_3d": False,
              "full_dynamic_wave_prepared": False,
              "phase": "original_land_clamped_h0_with_engineering_bed_water",
              "dynamic_boundary_z_m": 70., "static_geometry_coast_z_m": 75.,
              "outlet_dynamic_storage_included": False}
    result["identity_sha256"] = coast.fingerprint(result)
    sealed = coast._freeze(result)
    validate_surface_land_coverage(sealed)
    _cancel(cancel)
    return sealed


def _equal(actual, expected):
    if isinstance(expected, np.ndarray):
        if (not isinstance(actual, np.ndarray) or actual.dtype != expected.dtype or
                actual.shape != expected.shape or not np.array_equal(actual, expected)):
            raise ValueError("saved coverage array differs from source algebra")
    elif hasattr(expected, "items"):
        if not hasattr(actual, "items") or set(actual) != set(expected):
            raise ValueError("saved coverage schema differs")
        for key, value in expected.items():
            _equal(actual[key], value)
    elif isinstance(expected, (tuple, list)):
        if not isinstance(actual, (tuple, list)) or len(actual) != len(expected):
            raise ValueError("saved coverage sequence differs")
        for item, value in zip(actual, expected):
            _equal(item, value)
    elif type(expected) in (bool, int):
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError("strict saved bool/integer mismatch")
    elif type(expected) is float and type(actual) is not float:
        raise ValueError("strict saved float mismatch")
    elif actual != expected:
        raise ValueError("saved coverage scalar differs")


def _static_geometry(record):
    nodes, cells, triangles, audit = record["nodes"], record["cells"], record["triangles"], record["audit"]
    source = record["source"]
    inputs = source["evaluation"]["candidate"]["inputs"]
    mesh = source["domain_mosaic"]
    if (set(nodes) != {"xz_m", "h0_m", "h2_m", "water_surface_m", "wet_mask", "protected_mask"} or
            set(audit) != {"clamped_xz_m", "indices", "weights", "positive_mask", "valid_land_support",
                          "protected_support", "interior_node_ids", "interior_cell_mask",
                          "engineering_strip_domain", "dry_cut_bank_mask"}):
        raise ValueError("land node/audit schema")
    specs = [(nodes["xz_m"], (10011, 2), "float64"), (cells, (9800, 4), "int64"),
             (triangles, (19600, 3), "int64"), (record["domain_owner"], (9800,), "int64"),
             (audit["clamped_xz_m"], (10011, 2), "float64"), (audit["indices"], (10011, 4), "int64"),
             (audit["weights"], (10011, 4), "float64"), (audit["interior_node_ids"], (7991,), "int64"),
             (audit["interior_cell_mask"], (9800,), "bool"),
             (audit["engineering_strip_domain"], (10011,), "int64"),
             (audit["dry_cut_bank_mask"], (10011,), "bool")]
    for name in ("h0_m", "h2_m", "water_surface_m", "wet_mask", "protected_mask"):
        specs.append((nodes[name], (10011,), "bool" if name.endswith("mask") else "float64"))
    for name in ("positive_mask", "valid_land_support", "protected_support"):
        specs.append((audit[name], (10011, 4), "bool"))
    for array, shape, dtype in specs:
        if (not isinstance(array, np.ndarray) or array.shape != shape or array.dtype != np.dtype(dtype) or
                not np.all(np.isfinite(array))):
            raise ValueError("strict coverage shape/dtype/finite check")
    xz = nodes["xz_m"]
    node_number = np.arange(10011)
    if (not np.array_equal(xz[:, 0], node_number % 141 + 5.) or
            not np.array_equal(xz[:, 1], node_number // 141 + 5.)):
        raise ValueError("saved node coordinates/order")
    cell_number = np.arange(9800)
    start = cell_number // 140 * 141 + cell_number % 140
    if (not np.array_equal(cells[:, 0], start) or not np.array_equal(cells[:, 1], start + 1) or
            not np.array_equal(cells[:, 2], start + 142) or not np.array_equal(cells[:, 3], start + 141) or
            not np.array_equal(triangles[0::2], cells[:, [0, 1, 2]]) or
            not np.array_equal(triangles[1::2], cells[:, [0, 2, 3]])):
        raise ValueError("saved unique land topology")
    if not np.array_equal(record["domain_owner"], np.where(cell_number % 140 < 70, 1, 2)):
        raise ValueError("saved unique domain owner")
    clamped = audit["clamped_xz_m"]
    if (not np.array_equal(clamped[:, 0], np.clip(xz[:, 0], 10., 140.)) or
            not np.array_equal(clamped[:, 1], np.clip(xz[:, 1], 10., 70.))):
        raise ValueError("saved clamp algebra")
    indices, weights = audit["indices"], audit["weights"]
    left = np.floor(clamped[:, 0] / 10).astype(np.int64)
    top = np.floor(clamped[:, 1] / 10).astype(np.int64)
    fraction_x = clamped[:, 0] / 10 - left
    fraction_z = clamped[:, 1] / 10 - top
    expected_indices = (top * 16 + left, top * 16 + left + 1,
                        (top + 1) * 16 + left, (top + 1) * 16 + left + 1)
    expected_weights = ((1 - fraction_x) * (1 - fraction_z), fraction_x * (1 - fraction_z),
                        (1 - fraction_x) * fraction_z, fraction_x * fraction_z)
    for corner in range(4):
        if not np.array_equal(indices[:, corner], expected_indices[corner]) or not np.array_equal(weights[:, corner], expected_weights[corner]):
            raise ValueError("saved stencil algebra")
    positive = weights > 0
    valid = inputs["valid_mask"].ravel()[indices] & inputs["land_mask"].ravel()[indices]
    protected_support = inputs["protected_mask"].ravel()[indices]
    if (not np.array_equal(audit["positive_mask"], positive) or
            not np.array_equal(audit["valid_land_support"], valid) or np.any(positive & ~valid) or
            not np.array_equal(audit["protected_support"], protected_support)):
        raise ValueError("saved positive land/protection support")
    interior_nodes = (xz[:, 0] >= 10) & (xz[:, 0] <= 140) & (xz[:, 1] >= 10) & (xz[:, 1] <= 70)
    old_ids = audit["interior_node_ids"]
    if not np.array_equal(old_ids, np.flatnonzero(interior_nodes)):
        raise ValueError("saved interior node mapping")
    corner_xz = xz[cells[:, 0]]
    interior_cells = (corner_xz[:, 0] >= 10) & (corner_xz[:, 0] < 140) & (corner_xz[:, 1] >= 10) & (corner_xz[:, 1] < 70)
    if (not np.array_equal(audit["interior_cell_mask"], interior_cells) or
            not np.array_equal(triangles[np.repeat(interior_cells, 2)], old_ids[mesh["triangles"]]) or
            not np.array_equal(record["domain_owner"][interior_cells], mesh["hydrologic_domain_owner"].ravel())):
        raise ValueError("saved interior cells/triangles changed")
    original_h0 = (inputs["height_m"].ravel()[indices] * weights).sum(axis=1)
    if not np.allclose(nodes["h0_m"], original_h0, atol=1e-12, rtol=0):
        raise ValueError("original land H0 algebra")
    for name in ("h0_m", "h2_m", "water_surface_m", "wet_mask", "protected_mask"):
        if not np.array_equal(nodes[name][old_ids], mesh["nodes"][name]):
            raise ValueError("saved interior array changed")
    if not np.array_equal(nodes["protected_mask"], np.any(positive & protected_support, axis=1)):
        raise ValueError("saved protected nodal support")
    strips = audit["engineering_strip_domain"]
    bank = audit["dry_cut_bank_mask"]
    expected_strip = np.where((xz[:, 1] >= 70) & (xz[:, 0] >= 38) & (xz[:, 0] <= 41), 1,
                      np.where((xz[:, 1] >= 70) & (xz[:, 0] >= 108) & (xz[:, 0] <= 111), 2, 0))
    bank_x = np.isin(xz[:, 0], [35, 36, 37, 42, 43, 105, 106, 107, 112, 113])
    if not np.array_equal(strips, expected_strip) or not np.array_equal(bank, bank_x & (xz[:, 1] > 70)):
        raise ValueError("saved engineered strip/bank audit")
    dry = ~interior_nodes & (strips == 0) & ~bank
    if (not np.array_equal(nodes["h2_m"][dry], nodes["h0_m"][dry]) or np.any(nodes["wet_mask"][dry]) or
            np.any(nodes["water_surface_m"][dry] != 0)):
        raise ValueError("dry outer rim algebra")
    for domain_id, drop, outlet in zip((1, 2), source["drops"], record["outside_outlets"]):
        selected = np.flatnonzero(strips == domain_id)
        source_ids = (xz[selected, 1].astype(np.int64) - 70) * 4 + xz[selected, 0].astype(np.int64) - (38 if domain_id == 1 else 108)
        if (not np.array_equal(nodes["h2_m"][selected], drop["arrays"]["bed_xyz_m"][source_ids, 1]) or
                not np.array_equal(nodes["water_surface_m"][selected], drop["arrays"]["water_xyz_m"][source_ids, 1]) or
                not np.all(nodes["wet_mask"][selected])):
            raise ValueError("saved actual drop bed/water algebra")
        selected_bank = np.flatnonzero(bank & (xz[:, 0] < 75 if domain_id == 1 else xz[:, 0] > 75))
        original_ids = 65 * 141 + xz[selected_bank, 0].astype(np.int64) - 5
        delta = nodes["h0_m"][original_ids] - nodes["h2_m"][original_ids]
        expected_bed = nodes["h0_m"][selected_bank] - delta * (1 - (xz[selected_bank, 1] - 70) / 5.)
        if (not np.array_equal(nodes["h2_m"][selected_bank], expected_bed) or
                np.any(nodes["wet_mask"][selected_bank]) or np.any(nodes["water_surface_m"][selected_bank] != 0)):
            raise ValueError("saved tapered bank algebra")
        expected_outlet = {"domain_id": domain_id, "source_drop_sha256": drop["identity_sha256"],
                           "source_node_ids": np.arange(20, 84, dtype=np.int64),
                           "source_triangle_ids": np.arange(30, 120, dtype=np.int64),
                           "bed_xyz_m": drop["arrays"]["bed_xyz_m"][20:],
                           "water_xyz_m": drop["arrays"]["water_xyz_m"][20:],
                           "triangles": drop["arrays"]["triangles"][30:] - 20,
                           "shared_land_node_ids": selected[-4:].astype(np.int64),
                           "terminal_q_m3_s": drop["attachment"]["terminal_q_m3_s"]}
        _equal(outlet, expected_outlet)


def validate_surface_land_coverage(record):
    """Recheck saved source algebra, geometry, audit and budgets without preparation."""
    try:
        required = {"algorithm_version", "status", "interpretation", "source", "source_identity_sha256", "resources",
                    "grid", "nodes", "cells", "triangles", "domain_owner", "audit", "outside_outlets", "ledger",
                    "land_pixel_footprint_represented", "natural_outlets_certified", "general_cross_precision",
                    "dynamic_fine", "ready_for_3d", "identity_sha256", "full_dynamic_wave_prepared", "phase",
                    "dynamic_boundary_z_m", "static_geometry_coast_z_m", "outlet_dynamic_storage_included"}
        if (set(record) != required or record["algorithm_version"] != VERSION or record["status"] != "prepared" or
                record["interpretation"] != INTERPRETATION or record["land_pixel_footprint_represented"] is not True or
                any(record[name] is not False for name in
                    ("natural_outlets_certified", "general_cross_precision", "dynamic_fine", "ready_for_3d",
                     "full_dynamic_wave_prepared", "outlet_dynamic_storage_included")) or
                record["phase"] != "original_land_clamped_h0_with_engineering_bed_water" or
                record["dynamic_boundary_z_m"] != 70. or record["static_geometry_coast_z_m"] != 75. or
                record["identity_sha256"] != coast.fingerprint({key: value for key, value in record.items()
                                                                if key != "identity_sha256"})):
            raise ValueError("coverage schema/identity/scope mismatch")
        resources = CoverageResources(**record["resources"])
        _preflight(record["source"], resources)
        size = coast._retained(record)
        if size > resources.max_retained_bytes or size * 3 > resources.max_working_bytes:
            raise ValueError("coverage retained/working cap")
        _source_gate(record["source"])
        if record["source_identity_sha256"] != record["source"]["identity_sha256"]:
            raise ValueError("coverage source chain mismatch")
        _equal(record["grid"], {"bbox_xz_m": [5., 145., 5., 75.], "shape_nodes_zx": [71, 141], "spacing_m": 1.})
        if len(record["outside_outlets"]) != 2:
            raise ValueError("two outside outlets required")
        _static_geometry(record)
        nodes, cells, triangles, audit, outside = (record[name] for name in
                                                   ("nodes", "cells", "triangles", "audit", "outside_outlets"))
        _equal(record["ledger"], _ledger(nodes, cells, triangles, audit, outside))
        for outlet in record["outside_outlets"]:
            ids = outlet["shared_land_node_ids"]
            bed = np.column_stack((nodes["xz_m"][ids, 0], nodes["h2_m"][ids], nodes["xz_m"][ids, 1]))
            water = np.column_stack((nodes["xz_m"][ids, 0], nodes["water_surface_m"][ids], nodes["xz_m"][ids, 1]))
            if not np.array_equal(bed, outlet["bed_xyz_m"][:4]) or not np.array_equal(water, outlet["water_xyz_m"][:4]):
                raise ValueError("cropped drop shared boundary mismatch")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid saved coverage") from error


def query_surface_land_coverage(record):
    validate_surface_land_coverage(record)
    return coast._freeze({"identity_sha256": record["identity_sha256"], "interpretation": INTERPRETATION,
                          "grid": record["grid"], "nodes": record["nodes"], "cells": record["cells"],
                          "triangles": record["triangles"], "domain_owner": record["domain_owner"],
                          "engineering_strip_domain": record["audit"]["engineering_strip_domain"],
                          "outside_outlets": record["outside_outlets"], "ledger": record["ledger"],
                          "land_pixel_footprint_represented": True, "natural_outlets_certified": False,
                          "general_cross_precision": False, "dynamic_fine": False, "ready_for_3d": False,
                          "fixed_dynamic_wet_cells": 676,
                          "phase": record["phase"], "dynamic_boundary_z_m": 70., "static_geometry_coast_z_m": 75.,
                          "outlet_dynamic_storage_included": False, "full_dynamic_wave_prepared": False,
                          "source_identity_sha256": record["source_identity_sha256"]})


def save_surface_land_coverage(record, path):
    validate_surface_land_coverage(record)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    metadata = coast._json({"format": VERSION + "-npy-v1", "tree": coast._tree(record, arrays)}).encode("ascii")
    if len(metadata) > 8 * 1024 * 1024 or len(arrays) + 1 > record["resources"]["max_archive_members"]:
        raise ValueError("coverage archive metadata/member cap")
    archive_bound = len(metadata) + sum(array.nbytes + 2048 + 256 for array in arrays.values()) + 256
    if archive_bound > record["resources"]["max_retained_bytes"] or archive_bound * 3 > record["resources"]["max_working_bytes"]:
        raise ValueError("coverage archive byte preflight")
    descriptor, temporary = tempfile.mkstemp(prefix=".land-coverage-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("metadata.json", metadata)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def load_surface_land_coverage(path):
    """Bound every metadata and NPY header before loading any array payload."""
    with Path(path).open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > MAX_BYTES:
            raise ValueError("coverage file cap")
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names) > 2048 or len(names) != len(set(names)) or "metadata.json" not in names or
                    any(info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos) or
                    sum(info.file_size for info in infos) > MAX_BYTES or
                    archive.getinfo("metadata.json").file_size > 8 * 1024 * 1024):
                raise ValueError("coverage ZIP preflight")
            metadata = json.loads(archive.read("metadata.json"), object_pairs_hook=coast._pairs,
                                  parse_constant=coast._constant)
            if set(metadata) != {"format", "tree"} or metadata["format"] != VERSION + "-npy-v1":
                raise ValueError("coverage archive format")
            references = {}
            def inspect(value, depth=0):
                if depth > 80:
                    raise ValueError("coverage metadata nesting cap")
                if isinstance(value, dict) and "$array" in value:
                    if set(value) != {"$array", "shape", "dtype", "sha256"}:
                        raise ValueError("coverage array reference schema")
                    name, shape = value["$array"], value["shape"]
                    if (not isinstance(name, str) or name in references or not name.startswith("array_") or
                            not name.endswith(".npy") or "/" in name or "\\" in name or
                            not isinstance(shape, list) or len(shape) > 4 or
                            any(type(size) is not int or not 0 <= size <= 1000000 for size in shape) or
                            math.prod(shape) > 1000000 or not isinstance(value["dtype"], str) or
                            not isinstance(value["sha256"], str) or len(value["sha256"]) != 64 or
                            any(character not in "0123456789abcdef" for character in value["sha256"])):
                        raise ValueError("coverage array reference cap")
                    dtype = np.dtype(value["dtype"])
                    if dtype.kind not in "bifu" or dtype.itemsize > 8:
                        raise ValueError("coverage unsupported/object dtype")
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        inspect(child, depth + 1)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child, depth + 1)
            inspect(metadata["tree"])
            resources = CoverageResources(**metadata["tree"]["resources"])
            archive_size = sum(info.file_size for info in infos)
            if (set(names) != {"metadata.json"} | set(references) or len(names) > resources.max_archive_members or
                    archive_size > resources.max_retained_bytes or archive_size * 3 > resources.max_working_bytes):
                raise ValueError("coverage saved resource preflight")
            for name, reference in references.items():
                with archive.open(name) as member:
                    if np.lib.format.read_magic(member) != (1, 0):
                        raise ValueError("coverage NPY v1 required")
                    length = member.read(2)
                    if len(length) != 2 or int.from_bytes(length, "little") > 2038:
                        raise ValueError("coverage NPY header cap")
                    header = member.read(int.from_bytes(length, "little"))
                    if len(header) != int.from_bytes(length, "little"):
                        raise ValueError("coverage truncated header")
                    shape, fortran, dtype = engineering._strict_header(header)
                    if (list(shape) != reference["shape"] or dtype.str != reference["dtype"] or fortran or
                            member.tell() + math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError("coverage NPY payload/header mismatch")
            arrays = {}
            for name, reference in references.items():
                with archive.open(name) as member:
                    array = np.load(member, allow_pickle=False)
                if coast._array_hash(array) != reference["sha256"]:
                    raise ValueError("coverage array hash mismatch")
                arrays[name] = array
    def decode(value):
        if isinstance(value, dict) and "$array" in value:
            return arrays[value["$array"]]
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    result = coast._freeze(decode(metadata["tree"]))
    validate_surface_land_coverage(result)
    return result
