"""Register immutable metre sources and derive explicit, unresolved tile cuts."""

from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, save_bundle

from .metric_contracts import BoundaryGrid, TerrainGrid


SCHEMA = "terragenesis-metric-source-registration-v1"
ARRAYS = ("elevation_m", "valid_mask", "boundary_kind", "boundary_allow_inflow")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("lowercase SHA256 required")


def _validate_evidence(terrain, boundary, source_metadata):
    if source_metadata is None:
        return {}
    if not isinstance(source_metadata, dict):
        raise ValueError("source_metadata must be an object")
    evidence = dict(source_metadata)
    if "source_identity_sha256" in evidence:
        _sha(evidence["source_identity_sha256"])
        if evidence["source_identity_sha256"] != terrain.source_id:
            raise ValueError("source identity differs from TerrainGrid source_id")
    if "boundary_evidence_sha256" in evidence and evidence["boundary_evidence_sha256"] != boundary.source_sha256:
        raise ValueError("boundary evidence differs from BoundaryGrid")
    generation = evidence.get("generation_metadata", evidence)
    if not isinstance(generation, dict):
        raise ValueError("generation_metadata must be an object")
    seed = generation.get("seed")
    if seed is not None and str(seed) != str(terrain.generation_seed):
        raise ValueError("generation seed differs from TerrainGrid")
    model = generation.get("model")
    revision = generation.get("model_revision", generation.get("model_version"))
    if revision is None and isinstance(model, dict):
        revision = model.get("revision")
    if revision is not None and revision != terrain.model_version:
        raise ValueError("model revision differs from TerrainGrid")
    if "vertical_datum" in generation and generation["vertical_datum"] != terrain.vertical_datum:
        raise ValueError("vertical datum differs from TerrainGrid")
    for key in ("conditioning_identity", "conditioning_sha256"):
        if key in generation:
            _sha(generation[key])
            if generation[key] != terrain.condition_summary:
                raise ValueError("conditioning identity differs from TerrainGrid")
    if "seam_audit" in evidence and not isinstance(evidence["seam_audit"], dict):
        raise ValueError("seam audit must be an object")
    return evidence


def register_source(terrain: TerrainGrid, boundary: BoundaryGrid, *, source_metadata=None):
    """Bind source bytes, metre grid, boundary declaration, and optional TD pins."""
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, BoundaryGrid):
        raise TypeError("TerrainGrid and BoundaryGrid required")
    if terrain.valid_mask.shape != boundary.kind.shape:
        raise ValueError("terrain and boundary shapes differ")
    valid, kind = terrain.valid_mask, boundary.kind
    if np.any((~valid) & (kind != "unknown_boundary")):
        raise ValueError("invalid terrain must have unknown boundary kind")
    perimeter = np.zeros(valid.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if np.any(valid & perimeter & (kind == "interior")):
        raise ValueError("valid perimeter requires explicit boundary kind")
    if terrain.source_path is not None:
        source_path = Path(terrain.source_path).resolve()
        if file_sha256(source_path) != terrain.source_sha256:
            raise ValueError("source path bytes differ from declared SHA256")
    evidence = _validate_evidence(terrain, boundary, source_metadata)
    metadata = {"schema": SCHEMA, "terrain": terrain.metadata(),
                "terrain_identity_sha256": terrain.identity_sha256,
                "boundary": {"source_id": boundary.source_id,
                             "source_sha256": boundary.source_sha256},
                "boundary_identity_sha256": boundary.identity_sha256,
                "source_sha256": terrain.source_sha256,
                "source_metadata": evidence,
                "provenance_status": terrain.provenance_status,
                "coordinates": "X east, Y up, Z south; cells [z,x]; half-open tile windows",
                "cell_area_m2": terrain.cell_area_m2,
                "grid_shape_zx": list(terrain.elevation_m.shape),
                "elevation_dtype": "float64",
                "valid_elevation_range_m": [float(terrain.elevation_m[valid].min()),
                                            float(terrain.elevation_m[valid].max())],
                "nodata_fraction": float(1. - np.count_nonzero(valid) / valid.size),
                "coordinate_sample_range_m_xz": [
                    [terrain.x0_m, terrain.x0_m + (terrain.elevation_m.shape[1] - 1) * terrain.dx_m],
                    [terrain.z0_m, terrain.z0_m + (terrain.elevation_m.shape[0] - 1) * terrain.dz_m]],
                "grid_extent_m_xz": [terrain.elevation_m.shape[1] * terrain.dx_m,
                                     terrain.elevation_m.shape[0] * terrain.dz_m],
                "node_span_m_xz": [(terrain.elevation_m.shape[1] - 1) * terrain.dx_m,
                                    (terrain.elevation_m.shape[0] - 1) * terrain.dz_m],
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False}
    return {"terrain": terrain, "boundary": boundary, "metadata": metadata,
            "identity_sha256": identity({}, metadata)}


def slice_tile(terrain: TerrainGrid, boundary: BoundaryGrid, row_start, row_stop,
               col_start, col_stop, *, source_metadata=None):
    """Cut a half-open tile without duplicating cell area or opening cut edges."""
    parent = register_source(terrain, boundary, source_metadata=source_metadata)
    rows, cols = terrain.elevation_m.shape
    limits = (row_start, row_stop, col_start, col_stop)
    if (any(type(value) is not int for value in limits)
            or not (0 <= row_start < row_stop <= rows and 0 <= col_start < col_stop <= cols)):
        raise ValueError("nonempty half-open tile bounds required")
    window = np.s_[row_start:row_stop, col_start:col_stop]
    metadata = {key: getattr(terrain, key) for key in TerrainGrid.__dataclass_fields__
                if key not in ("elevation_m", "valid_mask")}
    metadata.update(x0_m=terrain.x0_m + col_start * terrain.dx_m,
                    z0_m=terrain.z0_m + row_start * terrain.dz_m)
    child_terrain = TerrainGrid(terrain.elevation_m[window], terrain.valid_mask[window],
                                **metadata)
    kind = boundary.kind[window].copy()
    cut = np.zeros(kind.shape, bool)
    if row_start > 0:
        cut[0, :] = True
    if row_stop < rows:
        cut[-1, :] = True
    if col_start > 0:
        cut[:, 0] = True
    if col_stop < cols:
        cut[:, -1] = True
    kind[cut] = "unknown_boundary"
    inflow = boundary.allow_inflow[window].copy()
    inflow[cut] = False
    kwargs = {}
    for field in ("stage_m", "discharge_m3_s"):
        values = getattr(boundary, field)
        if values is not None:
            selected = values[window].copy()
            selected[cut] = 0.
            kwargs[field] = selected
    child_boundary = BoundaryGrid(kind, inflow, boundary.source_id, boundary.source_sha256, **kwargs)
    child = register_source(child_terrain, child_boundary, source_metadata=source_metadata)
    child["metadata"].update(parent_terrain_identity_sha256=terrain.identity_sha256,
                              parent_boundary_identity_sha256=boundary.identity_sha256,
                              parent_registration_identity_sha256=parent["identity_sha256"],
                              parent_shape_zx=list(terrain.elevation_m.shape),
                              parent_origin_m_xz=[terrain.x0_m, terrain.z0_m],
                              parent_spacing_m_xz=[terrain.dx_m, terrain.dz_m],
                              window_zx=[row_start, row_stop, col_start, col_stop],
                              cut_boundary_policy="unknown_pending_no_automatic_open")
    child["identity_sha256"] = identity({}, child["metadata"])
    return child


def _arrays(registration):
    terrain, boundary = registration["terrain"], registration["boundary"]
    result = {"elevation_m": terrain.elevation_m, "valid_mask": terrain.valid_mask,
              "boundary_kind": boundary.kind, "boundary_allow_inflow": boundary.allow_inflow}
    for field in ("stage_m", "discharge_m3_s"):
        value = getattr(boundary, field)
        if value is not None:
            result["boundary_" + field] = value
    return result


def _validate_bundle(bundle):
    meta, arrays = bundle["metadata"], bundle["arrays"]
    base_keys = {"schema", "terrain", "terrain_identity_sha256", "boundary",
                 "boundary_identity_sha256", "source_sha256", "source_metadata",
                 "provenance_status", "coordinates", "cell_area_m2", "grid_shape_zx",
                 "elevation_dtype", "valid_elevation_range_m", "nodata_fraction",
                 "coordinate_sample_range_m_xz", "grid_extent_m_xz",
                 "node_span_m_xz", "hydraulic_ready", "natural_outlet_verified", "publishable"}
    tile_keys = {"parent_terrain_identity_sha256", "parent_boundary_identity_sha256",
                 "parent_registration_identity_sha256", "parent_shape_zx",
                 "parent_origin_m_xz", "parent_spacing_m_xz", "window_zx", "cut_boundary_policy"}
    if (meta.get("schema") != SCHEMA or set(meta) not in (base_keys, base_keys | tile_keys)
            or set(arrays) - set(ARRAYS + ("boundary_stage_m", "boundary_discharge_m3_s"))):
        raise ValueError("source registration bundle schema mismatch")
    if not set(ARRAYS).issubset(arrays):
        raise ValueError("source registration arrays missing")
    terrain = TerrainGrid(arrays["elevation_m"], arrays["valid_mask"], **{
        key: value for key, value in meta["terrain"].items()
        if key in TerrainGrid.__dataclass_fields__ and key not in ("elevation_m", "valid_mask")})
    boundary = BoundaryGrid(arrays["boundary_kind"], arrays["boundary_allow_inflow"],
                            meta["boundary"]["source_id"], meta["boundary"]["source_sha256"],
                            stage_m=arrays.get("boundary_stage_m"),
                            discharge_m3_s=arrays.get("boundary_discharge_m3_s"))
    expected = register_source(terrain, boundary, source_metadata=meta["source_metadata"])
    if meta.keys() == base_keys | tile_keys:
        row_start, row_stop, col_start, col_stop = meta["window_zx"]
        parent_rows, parent_cols = meta["parent_shape_zx"]
        px, pz = meta["parent_origin_m_xz"]
        dx, dz = meta["parent_spacing_m_xz"]
        if (not (0 <= row_start < row_stop <= parent_rows and 0 <= col_start < col_stop <= parent_cols)
                or terrain.elevation_m.shape != (row_stop - row_start, col_stop - col_start)
                or terrain.x0_m != px + col_start * dx or terrain.z0_m != pz + row_start * dz
                or terrain.dx_m != dx or terrain.dz_m != dz
                or meta["cut_boundary_policy"] != "unknown_pending_no_automatic_open"):
            raise ValueError("saved tile geometry differs from parent window")
        cut = np.zeros(terrain.valid_mask.shape, bool)
        if row_start > 0:
            cut[0, :] = True
        if row_stop < parent_rows:
            cut[-1, :] = True
        if col_start > 0:
            cut[:, 0] = True
        if col_stop < parent_cols:
            cut[:, -1] = True
        if np.any(boundary.kind[cut] != "unknown_boundary"):
            raise ValueError("saved tile cut boundary became a resolved outlet")
        for key in ("parent_terrain_identity_sha256", "parent_boundary_identity_sha256",
                    "parent_registration_identity_sha256"):
            _sha(meta[key])
    if (expected["metadata"] != {key: meta[key] for key in base_keys}
            or bundle["identity_sha256"] != identity({}, meta)):
        raise ValueError("source registration metadata or identity mismatch")
    return terrain, boundary


def save_source_registration(path, registration):
    bundle = {"arrays": _arrays(registration), "metadata": registration["metadata"],
              "identity_sha256": registration["identity_sha256"]}
    _validate_bundle(bundle)
    save_bundle(path, bundle, validator=lambda value: _validate_bundle(value))


def load_source_registration(path, *, expected_sha256, expected_identity=None):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=lambda value: _validate_bundle(value))
    if expected_identity is not None and bundle["identity_sha256"] != expected_identity:
        raise ValueError("source registration identity differs from external pin")
    terrain, boundary = _validate_bundle(bundle)
    return {"terrain": terrain, "boundary": boundary,
            "metadata": bundle["metadata"], "identity_sha256": bundle["identity_sha256"]}
