"""Proof-bound domain meshes joined by an explicit original-H0 dry extension."""

import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline import surface_fine_mosaic as fine_mosaic
from terrain_pipeline.surface_domain_prepare import validate_surface_domains

VERSION = "surface-domain-mosaic-v1"
SOURCE_KINDS = ("accepted_domain_proof", "original_candidate_h0_dry_bilinear")


def _candidate_grid(candidate):
    inputs = candidate["inputs"]
    return {"origin_x_m": inputs["origin_x_m"], "origin_z_m": inputs["origin_z_m"],
            "spacing_x_m": inputs["spacing_x_m"], "spacing_z_m": inputs["spacing_z_m"]}


def _envelope(domain_meshes):
    bounds = [mesh["grid"]["bbox_xz_m"] for mesh in domain_meshes]
    return [min(item[0] for item in bounds), max(item[1] for item in bounds),
            min(item[2] for item in bounds), max(item[3] for item in bounds)]


def _grid(domain_meshes):
    bbox = _envelope(domain_meshes)
    spacing_x = min(mesh["grid"]["spacing_x_m"] for mesh in domain_meshes)
    spacing_z = min(mesh["grid"]["spacing_z_m"] for mesh in domain_meshes)
    if any(mesh["grid"]["spacing_x_m"] != spacing_x or mesh["grid"]["spacing_z_m"] != spacing_z for mesh in domain_meshes):
        raise ValueError("domain precision mismatch")
    dimensions = [(bbox[1] - bbox[0]) / spacing_x, (bbox[3] - bbox[2]) / spacing_z]
    if any(not math.isclose(value, round(value), abs_tol=1e-8, rel_tol=0) for value in dimensions):
        raise ValueError("incompatible domain grid envelope")
    if any(not math.isclose((mesh["grid"]["origin_x_m"] - bbox[0]) / spacing_x,
                                round((mesh["grid"]["origin_x_m"] - bbox[0]) / spacing_x), abs_tol=1e-8, rel_tol=0) or
           not math.isclose((mesh["grid"]["origin_z_m"] - bbox[2]) / spacing_z,
                                round((mesh["grid"]["origin_z_m"] - bbox[2]) / spacing_z), abs_tol=1e-8, rel_tol=0)
           for mesh in domain_meshes):
        raise ValueError("domain origins not aligned")
    return {"coordinate_system": "metric-xz-m", "origin_x_m": bbox[0], "origin_z_m": bbox[2],
            "spacing_x_m": spacing_x, "spacing_z_m": spacing_z,
            "shape_cells_zx": [round(dimensions[1]), round(dimensions[0])], "bbox_xz_m": bbox}


def _extension_value(candidate, x, z, indices, weights):
    inputs = candidate["inputs"]
    shape = inputs["height_m"].shape
    fine_mosaic._support_check(indices, weights, shape, np.asarray(x), np.asarray(z), _candidate_grid(candidate))
    positive = indices[weights > 0]
    if (not np.all(inputs["valid_mask"].ravel()[positive]) or
            not np.all(inputs["land_mask"].ravel()[positive]) or
            np.any(inputs["ocean_mask"].ravel()[positive]) or
            np.any(inputs["domain_labels"].ravel()[positive] <= 0)):
        raise ValueError("dry extension requires valid known original land support")
    height = float(np.dot(inputs["height_m"].ravel()[indices], weights))
    if not math.isfinite(height):
        raise ValueError("dry extension H0 is not finite")
    return height, bool(np.any(inputs["protected_mask"].ravel()[positive]))


def _check_node(nodes, node_id, values, seen, tolerance=1e-8):
    for name, value in values.items():
        previous = nodes[name][node_id]
        if seen[node_id] and (previous != value if isinstance(value, (bool, np.bool_)) else
                              abs(previous - value) > tolerance):
            raise ValueError("shared seam conflict in H0/H2/wet/stage/protection")
        nodes[name][node_id] = value
    seen[node_id] = True


def _domain_owner(record, cells, nodes, geometry_owner):
    candidate = record["evaluation"]["candidate"]
    inputs = candidate["inputs"]
    labels = inputs["domain_labels"]
    center_x = nodes["x_m"][cells].mean(axis=1)
    center_z = nodes["z_m"][cells].mean(axis=1)
    column = np.floor((center_x - inputs["origin_x_m"]) / inputs["spacing_x_m"] + .5).astype(int)
    row = np.floor((center_z - inputs["origin_z_m"]) / inputs["spacing_z_m"] + .5).astype(int)
    if np.any(row < 0) or np.any(row >= labels.shape[0]) or np.any(column < 0) or np.any(column >= labels.shape[1]):
        raise ValueError("cell center outside original candidate")
    owners = labels[row, column]
    for source_id, domain in enumerate(record["evaluation"]["domains"]):
        if np.any(owners[geometry_owner == source_id] != domain["domain_id"]):
            raise ValueError("domain cell center label mismatch")
    if np.any(owners <= 0):
        raise ValueError("extension has no hydrologic domain owner")
    return owners.astype(np.int64)


def _assemble(record, cancel=None):
    grid, meshes, candidate = record["grid"], record["domain_meshes"], record["evaluation"]["candidate"]
    rows, columns = grid["shape_cells_zx"]
    count, node_count = rows * columns, (rows + 1) * (columns + 1)
    cells, triangles = fine_mosaic._mesh(grid)
    nodes = {name: np.zeros(node_count, bool if name.endswith("mask") else float)
             for name in ("x_m", "z_m", "h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask")}
    nodes["x_m"] = np.tile(grid["origin_x_m"] + np.arange(columns + 1) * grid["spacing_x_m"], rows + 1)
    nodes["z_m"] = np.repeat(grid["origin_z_m"] + np.arange(rows + 1) * grid["spacing_z_m"], columns + 1)
    owner = np.full(count, -1, np.int64)
    contributors = {"indices": np.zeros((count, 4, 4), np.int64),
                    "weights": np.zeros((count, 4, 4), float)}
    for source_id, mesh in enumerate(meshes):
        source_grid = mesh["grid"]
        source_rows, source_columns = source_grid["shape_cells_zx"]
        left = (source_grid["origin_x_m"] - grid["origin_x_m"]) / grid["spacing_x_m"]
        top = (source_grid["origin_z_m"] - grid["origin_z_m"]) / grid["spacing_z_m"]
        if not math.isclose(left, round(left), abs_tol=1e-8) or not math.isclose(top, round(top), abs_tol=1e-8):
            raise ValueError("incompatible domain grid origin")
        if source_grid["spacing_x_m"] != grid["spacing_x_m"] or source_grid["spacing_z_m"] != grid["spacing_z_m"]:
            raise ValueError("domain precision mismatch")
        for row in range(source_rows):
            for column in range(source_columns):
                source_cell = row * source_columns + column
                target_cell = (round(top) + row) * columns + round(left) + column
                if owner[target_cell] != -1:
                    raise ValueError("overlapping domain cells")
                owner[target_cell] = source_id
                contributors["indices"][target_cell] = mesh["contributors"]["indices"][source_cell]
                contributors["weights"][target_cell] = mesh["contributors"]["weights"][source_cell]
    extension = np.flatnonzero(owner < 0)
    owner[extension] = len(meshes)
    seen = np.zeros(node_count, bool)
    for cell_id, cell in enumerate(cells):
        if cell_id % columns == 0:
            fine_mosaic._cancel(cancel)
        source_id = int(owner[cell_id])
        for corner, node_id in enumerate(cell):
            x, z = nodes["x_m"][node_id], nodes["z_m"][node_id]
            if source_id == len(meshes):
                source_grid = _candidate_grid(candidate)
                source_shape = candidate["inputs"]["height_m"].shape
                source_row = (z - source_grid["origin_z_m"]) / source_grid["spacing_z_m"]
                source_column = (x - source_grid["origin_x_m"]) / source_grid["spacing_x_m"]
                indices, weights = fine_mosaic._stencil(source_row, source_column, source_shape)
                contributors["indices"][cell_id, corner] = indices
                contributors["weights"][cell_id, corner] = weights
                height, protected = _extension_value(candidate, x, z, indices, weights)
                values = {"h0_m": height, "h2_m": height, "wet_mask": False,
                          "water_surface_m": 0., "protected_mask": protected}
            else:
                mesh = meshes[source_id]
                source_grid = mesh["grid"]
                source_row = round((z - source_grid["origin_z_m"]) / source_grid["spacing_z_m"])
                source_column = round((x - source_grid["origin_x_m"]) / source_grid["spacing_x_m"])
                source_node = source_row * (source_grid["shape_cells_zx"][1] + 1) + source_column
                values = {name: mesh["nodes"][name][source_node] for name in
                          ("h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask")}
            _check_node(nodes, node_id, values, seen)
    if np.any(~seen):
        raise ValueError("unowned nodes")
    wet_cells = nodes["wet_mask"][cells].all(axis=1)
    if np.any(wet_cells[extension]) or np.any(np.abs(nodes["h0_m"][cells[extension]] - nodes["h2_m"][cells[extension]]) > 1e-8):
        raise ValueError("extension wet or cut")
    output = {"nodes": nodes, "cells": cells, "triangles": triangles, "cell_owner": owner.reshape(rows, columns),
              "hydrologic_domain_owner": _domain_owner(record, cells, nodes, owner).reshape(rows, columns),
              "contributors": contributors, "wet_cells": wet_cells}
    area = grid["spacing_x_m"] * grid["spacing_z_m"]
    cut = float(((nodes["h0_m"] - nodes["h2_m"])[triangles].mean(axis=1) * area / 2).sum())
    wet_triangles = triangles[np.repeat(wet_cells, 2)]
    water = float(((nodes["water_surface_m"] - nodes["h2_m"])[wet_triangles].mean(axis=1) * area / 2).sum())
    output["summary"] = {"unique_cell_area_m2": count * area, "unique_cut_volume_m3": cut,
                         "actual_wet_water_volume_m3": water,
                         "q_outgoing_m3_s": sum(mesh["summary"]["q_outgoing_m3_s"] for mesh in meshes),
                         "q_incoming_m3_s": sum(mesh["summary"]["q_incoming_m3_s"] for mesh in meshes),
                         "q_local_m3_s": sum(mesh["summary"]["q_local_m3_s"] for mesh in meshes)}
    output["extension_cell_count"] = len(extension)
    return output


def prepare_domain_mosaic(evaluation, *, resources=fine_mosaic.MosaicResources(), cancel=None):
    if not isinstance(resources, fine_mosaic.MosaicResources):
        raise ValueError("invalid resource limits")
    fine_mosaic._cancel(cancel)
    if fine_mosaic._size(evaluation) > resources.max_retained_bytes:
        raise ValueError("evaluation retained resource preflight")
    validate_surface_domains(evaluation)
    if evaluation["kind"] != "evaluation" or len(evaluation["domains"]) < 2:
        raise ValueError("prepared multiple domains required")
    candidate = evaluation["candidate"]
    inputs = candidate["inputs"]
    declared = []
    for domain in evaluation["domains"]:
        fine = domain["recovery"]["inputs"]["fine"]
        declared.append({"grid": {"origin_x_m": fine["origin_x_m"], "origin_z_m": fine["origin_z_m"],
            "spacing_x_m": fine["spacing_x_m"], "spacing_z_m": fine["spacing_z_m"],
            "bbox_xz_m": [fine["origin_x_m"], fine["origin_x_m"] + (fine["shape_zx"][1] - 1) * fine["spacing_x_m"],
                          fine["origin_z_m"], fine["origin_z_m"] + (fine["shape_zx"][0] - 1) * fine["spacing_z_m"]]}})
    preflight_grid = _grid(declared)
    preflight_cells = math.prod(preflight_grid["shape_cells_zx"])
    if (preflight_cells > resources.max_cells or
            fine_mosaic._size(evaluation) + preflight_cells * 800 > min(resources.max_retained_bytes, resources.max_working_bytes)):
        raise ValueError("domain mosaic resource preflight")
    meshes = []
    for domain in evaluation["domains"]:
        fine_mosaic._cancel(cancel)
        mesh = fine_mosaic.prepare_fine_mosaic((fine_mosaic.DomainFineSource(domain["recovery"], domain["domain_id"]),),
            metric_grid={"coordinate_system": "metric-xz-m"}, vertical_datum=inputs["vertical_datum"],
            source_identity=candidate["identity_sha256"] + ":domain:" + str(domain["domain_id"]),
            sea_level_elevation_m=inputs["sea_level_elevation_m"], resources=resources, cancel=cancel)
        meshes.append(mesh)
    grid = _grid(meshes)
    count = math.prod(grid["shape_cells_zx"])
    if count > resources.max_cells or fine_mosaic._size({"evaluation": evaluation, "domain_meshes": meshes}) + count * 800 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError("domain mosaic resource preflight")
    record = {"algorithm_version": VERSION, "status": "prepared", "scope": "declared_rectangular_node_envelope",
              "evaluation": fine_mosaic._plain(evaluation), "candidate_identity_sha256": candidate["identity_sha256"],
              "domain_meshes": [fine_mosaic._plain(mesh) for mesh in meshes], "source_kinds": list(SOURCE_KINDS),
              "grid": grid, "resources": vars(resources), "declared_node_envelope_complete": True,
              "physical_footprint_complete": False, "natural_outlets_certified": False,
              "full_domain_mosaic_prepared": False}
    record.update(_assemble(record, cancel))
    sealed = fine_mosaic._seal(record)
    validate_domain_mosaic(sealed)
    return sealed


def validate_domain_mosaic(result):
    try:
        record = fine_mosaic._plain(result)
        identity = record.pop("identity_sha256")
        if set(record) != {"algorithm_version", "status", "scope", "evaluation", "candidate_identity_sha256",
                           "domain_meshes", "source_kinds", "grid", "resources", "declared_node_envelope_complete",
                           "physical_footprint_complete", "natural_outlets_certified", "full_domain_mosaic_prepared",
                           "nodes", "cells", "triangles", "cell_owner", "hydrologic_domain_owner",
                           "contributors", "wet_cells", "summary", "extension_cell_count"}:
            raise ValueError("invalid domain mosaic schema")
        if fine_mosaic._identity(record) != identity or record["algorithm_version"] != VERSION or record["status"] != "prepared":
            raise ValueError("domain mosaic identity/status mismatch")
        if (record["scope"] != "declared_rectangular_node_envelope" or
                record["source_kinds"] != list(SOURCE_KINDS) or
                record["declared_node_envelope_complete"] is not True or
                any(record[name] is not False for name in
                    ("physical_footprint_complete", "natural_outlets_certified", "full_domain_mosaic_prepared"))):
            raise ValueError("invalid engineering scope")
        resources = fine_mosaic.MosaicResources(**record["resources"])
        if (set(record["grid"]) != {"coordinate_system", "origin_x_m", "origin_z_m", "spacing_x_m",
                                    "spacing_z_m", "shape_cells_zx", "bbox_xz_m"} or
                record["grid"]["coordinate_system"] != "metric-xz-m" or
                set(record["nodes"]) != {"x_m", "z_m", "h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask"} or
                set(record["contributors"]) != {"indices", "weights"}):
            raise ValueError("invalid grid/node/contributor schema")
        rows, columns = record["grid"]["shape_cells_zx"]
        if type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0:
            raise ValueError("invalid grid shape")
        if rows * columns > resources.max_cells or fine_mosaic._size(result) > resources.max_retained_bytes or fine_mosaic._size(result) + rows * columns * 640 > resources.max_working_bytes:
            raise ValueError("domain mosaic resource limit")
        evaluation = record["evaluation"]
        support = {}
        for mesh in record["domain_meshes"]:
            for identity, saved in mesh["proof_h0_support"].items():
                if identity in support:
                    raise ValueError("duplicate domain recovery support")
                support[identity] = saved
        validate_surface_domains(evaluation, saved_support=support)
        if record["candidate_identity_sha256"] != evaluation["candidate"]["identity_sha256"] or len(record["domain_meshes"]) != len(evaluation["domains"]):
            raise ValueError("candidate/domain identity mismatch")
        for mesh, domain in zip(record["domain_meshes"], evaluation["domains"]):
            fine_mosaic.validate_fine_mosaic(mesh)
            fine = domain["recovery"]["inputs"]["fine"]
            if (len(mesh["sources"]) != 1 or mesh["sources"][0]["domain_id"] != domain["domain_id"] or
                    mesh["sources"][0]["proof_sha256"] != domain["recovery"]["identity_sha256"] or
                    mesh["sources"][0]["window_zx"] != [0, fine["shape_zx"][0], 0, fine["shape_zx"][1]] or
                    mesh["grid"]["bbox_xz_m"] != [fine["origin_x_m"],
                        fine["origin_x_m"] + (fine["shape_zx"][1] - 1) * fine["spacing_x_m"],
                        fine["origin_z_m"], fine["origin_z_m"] + (fine["shape_zx"][0] - 1) * fine["spacing_z_m"]]):
                raise ValueError("domain mesh proof binding mismatch")
            if (mesh["grid"]["spacing_x_m"] != record["grid"]["spacing_x_m"] or
                    mesh["grid"]["spacing_z_m"] != record["grid"]["spacing_z_m"]):
                raise ValueError("domain precision mismatch")
        if record["grid"] != _grid(record["domain_meshes"]):
            raise ValueError("declared envelope differs from saved domains")
        nodes, cells, triangles = record["nodes"], record["cells"], record["triangles"]
        count = rows * columns
        if (record["cell_owner"].dtype != np.int64 or record["cell_owner"].shape != (rows, columns) or
                cells.shape != (count, 4) or cells.dtype != np.int64 or triangles.shape != (2 * count, 3) or triangles.dtype != np.int64):
            raise ValueError("invalid saved topology")
        indices, weights = record["contributors"]["indices"], record["contributors"]["weights"]
        if indices.shape != (count, 4, 4) or weights.shape != indices.shape or indices.dtype != np.int64 or weights.dtype != np.float64:
            raise ValueError("invalid contributor arrays")
        for cell_id, cell in enumerate(cells):
            top_left = cell_id // columns * (columns + 1) + cell_id % columns
            if (tuple(cell) != (top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1) or
                    tuple(triangles[2 * cell_id]) != tuple(cell[[0, 1, 2]]) or
                    tuple(triangles[2 * cell_id + 1]) != tuple(cell[[0, 2, 3]])):
                raise ValueError("invalid unique cell/triangle topology")
        node_count = (rows + 1) * (columns + 1)
        expected_x = np.tile(record["grid"]["origin_x_m"] + np.arange(columns + 1) * record["grid"]["spacing_x_m"], rows + 1)
        expected_z = np.repeat(record["grid"]["origin_z_m"] + np.arange(rows + 1) * record["grid"]["spacing_z_m"], columns + 1)
        if (nodes["x_m"].dtype != np.float64 or nodes["z_m"].dtype != np.float64 or
                nodes["x_m"].shape != (node_count,) or nodes["z_m"].shape != (node_count,) or
                not np.array_equal(nodes["x_m"], expected_x) or not np.array_equal(nodes["z_m"], expected_z)):
            raise ValueError("invalid saved node coordinates")
        for name in ("h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask"):
            if nodes[name].shape != (node_count,) or nodes[name].dtype != (bool if name.endswith("mask") else np.float64) or not np.isfinite(nodes[name]).all():
                raise ValueError("invalid saved node fields")
        seen = np.zeros(node_count, bool)
        expected_owner = np.full(count, len(record["domain_meshes"]), np.int64)
        for source_id, mesh in enumerate(record["domain_meshes"]):
            source_grid = mesh["grid"]
            top = round((source_grid["origin_z_m"] - record["grid"]["origin_z_m"]) / record["grid"]["spacing_z_m"])
            left = round((source_grid["origin_x_m"] - record["grid"]["origin_x_m"]) / record["grid"]["spacing_x_m"])
            source_rows, source_columns = source_grid["shape_cells_zx"]
            for row in range(source_rows):
                for column in range(source_columns):
                    cell_id = (top + row) * columns + left + column
                    if expected_owner[cell_id] != len(record["domain_meshes"]):
                        raise ValueError("overlapping saved domain footprint")
                    expected_owner[cell_id] = source_id
        if not np.array_equal(record["cell_owner"].ravel(), expected_owner):
            raise ValueError("saved cell owner differs from domains")
        if (record["hydrologic_domain_owner"].dtype != np.int64 or
                record["hydrologic_domain_owner"].shape != (rows, columns) or
                not np.array_equal(record["hydrologic_domain_owner"].ravel(),
                                   _domain_owner(record, cells, nodes, expected_owner))):
            raise ValueError("saved hydrologic domain owner differs from candidate labels")
        candidate = evaluation["candidate"]
        for cell_id, cell in enumerate(cells):
            source_id = int(expected_owner[cell_id])
            for corner, node_id in enumerate(cell):
                x, z = nodes["x_m"][node_id], nodes["z_m"][node_id]
                if source_id == len(record["domain_meshes"]):
                    height, protected = _extension_value(candidate, x, z, indices[cell_id, corner], weights[cell_id, corner])
                    values = {"h0_m": height, "h2_m": height, "wet_mask": False,
                              "water_surface_m": 0., "protected_mask": protected}
                else:
                    mesh = record["domain_meshes"][source_id]
                    source_grid = mesh["grid"]
                    source_row = round((z - source_grid["origin_z_m"]) / source_grid["spacing_z_m"])
                    source_column = round((x - source_grid["origin_x_m"]) / source_grid["spacing_x_m"])
                    cell_top = round((nodes["z_m"][cell[0]] - source_grid["origin_z_m"]) / source_grid["spacing_z_m"])
                    cell_left = round((nodes["x_m"][cell[0]] - source_grid["origin_x_m"]) / source_grid["spacing_x_m"])
                    source_cell = cell_top * source_grid["shape_cells_zx"][1] + cell_left
                    if (not np.array_equal(indices[cell_id, corner], mesh["contributors"]["indices"][source_cell, corner]) or
                            not np.array_equal(weights[cell_id, corner], mesh["contributors"]["weights"][source_cell, corner])):
                        raise ValueError("saved domain contributor differs")
                    source_node = source_row * (source_grid["shape_cells_zx"][1] + 1) + source_column
                    values = {name: mesh["nodes"][name][source_node] for name in
                              ("h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask")}
                for name, value in values.items():
                    if (nodes[name][node_id] != value if isinstance(value, (bool, np.bool_)) else abs(nodes[name][node_id] - value) > 1e-8):
                        raise ValueError("saved node disagrees with domain/extension support")
                seen[node_id] = True
        if (not np.all(seen) or type(record["extension_cell_count"]) is not int or
                record["extension_cell_count"] != int(np.count_nonzero(expected_owner == len(record["domain_meshes"])))):
            raise ValueError("incomplete saved node envelope")
        wet_cells = nodes["wet_mask"][cells].all(axis=1)
        if (record["wet_cells"].dtype != bool or record["wet_cells"].shape != (count,) or
                not np.array_equal(record["wet_cells"], wet_cells) or
                np.any(wet_cells[expected_owner == len(record["domain_meshes"])])):
            raise ValueError("extension contains wet cells")
        area = record["grid"]["spacing_x_m"] * record["grid"]["spacing_z_m"]
        cut = float(((nodes["h0_m"] - nodes["h2_m"])[triangles].mean(axis=1) * area / 2).sum())
        wet_triangles = triangles[np.repeat(wet_cells, 2)]
        water = float(((nodes["water_surface_m"] - nodes["h2_m"])[wet_triangles].mean(axis=1) * area / 2).sum())
        expected_summary = {"unique_cell_area_m2": count * area, "unique_cut_volume_m3": cut,
                            "actual_wet_water_volume_m3": water}
        for name in ("q_outgoing_m3_s", "q_incoming_m3_s", "q_local_m3_s"):
            expected_summary[name] = sum(mesh["summary"][name] for mesh in record["domain_meshes"])
        if fine_mosaic._identity(record["summary"]) != fine_mosaic._identity(expected_summary):
            raise ValueError("saved volume or Q ledger differs")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid domain mosaic semantic record") from error


def save_domain_mosaic(result, path):
    validate_domain_mosaic(result)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = fine_mosaic._tree(result, arrays)
    manifest = {"format_version": 3, "tree": tree, "tree_sha256": fine_mosaic._identity(tree)}
    descriptor, temporary_name = tempfile.mkstemp(prefix="." + destination.name + "-", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", fine_mosaic._json(manifest))
                for name, array in arrays.items():
                    with io.BytesIO() as payload:
                        np.save(payload, np.ascontiguousarray(array), allow_pickle=False)
                        archive.writestr(name, payload.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
        with zipfile.ZipFile(temporary) as archive:
            fine_mosaic._preflight_archive(archive)
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def load_domain_mosaic(path):
    try:
        with Path(path).open("rb") as retained, zipfile.ZipFile(retained) as archive:
            if os.fstat(retained.fileno()).st_size > fine_mosaic.MAX_BYTES:
                raise ValueError("domain mosaic file byte cap")
            fine_mosaic._preflight_archive(archive)
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=fine_mosaic._pairs,
                                  parse_constant=fine_mosaic._constant)
            if (set(manifest) != {"format_version", "tree", "tree_sha256"} or manifest["format_version"] != 3 or
                    manifest["tree_sha256"] != fine_mosaic._identity(manifest["tree"])):
                raise ValueError("domain mosaic manifest mismatch")
            tree = manifest["tree"]
            resources = fine_mosaic.MosaicResources(**tree["resources"])
            rows, columns = tree["grid"]["shape_cells_zx"]
            if (type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0 or
                    rows * columns > resources.max_cells or
                    sum(entry.file_size for entry in archive.infolist()) > resources.max_retained_bytes or
                    sum(entry.file_size for entry in archive.infolist()) + rows * columns * 640 > resources.max_working_bytes):
                raise ValueError("archive JSON resource preflight")
            arrays = {}
            for name in archive.namelist():
                if name.endswith(".npy"):
                    with archive.open(name) as stream:
                        arrays[name] = np.load(stream, allow_pickle=False)
            used = set()
            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    name = value["$array"]
                    if set(value) != {"$array", "dtype", "shape", "sha256"} or name in used or name not in arrays:
                        raise ValueError("invalid/duplicate array reference")
                    array = arrays[name]
                    if value["dtype"] != array.dtype.str or value["shape"] != list(array.shape) or value["sha256"] != fine_mosaic.array_hash(array):
                        raise ValueError("array hash/shape mismatch")
                    used.add(name)
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            result = decode(tree)
            if used != set(arrays):
                raise ValueError("unreferenced arrays")
        validate_domain_mosaic(result)
        return fine_mosaic._freeze(result)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, EOFError) as error:
        raise ValueError("invalid domain mosaic bundle") from error
