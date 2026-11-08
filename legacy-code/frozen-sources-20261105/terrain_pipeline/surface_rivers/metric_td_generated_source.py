"""Register frozen raw TD outputs with unresolved finite-domain boundaries."""

import hashlib
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from .metric_contracts import BoundaryGrid, TerrainGrid
from .metric_source import register_source


def _manifest(report_path, expected_report_sha256):
    report_path = Path(report_path).resolve()
    digest = file_sha256(report_path)
    if expected_report_sha256 is not None and digest != expected_report_sha256:
        raise ValueError("generation report SHA256 differs")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "TD-noise-climate-generation-v1" or report.get("status") != "completed":
        raise ValueError("completed raw TD noise-generation report required")
    plan_path = Path(report["plan_path"]).resolve()
    if file_sha256(plan_path) != report["plan_sha256"]:
        raise ValueError("generation plan SHA256 differs")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    declared = [(job["seed"], domain["origin_xz"]) for job in plan["jobs"] for domain in job["domains"]]
    actual = [(sample["seed"], sample["native_origin"]) for sample in report["samples"]]
    if len(actual) != 6 or actual != declared:
        raise ValueError("all six samples must retain the frozen plan order")
    return report_path, digest, report, plan


def load_generated_td_source(report_path, sample_index, *, expected_report_sha256=None):
    """Load one fixed index; samples become cell-centred bed values unchanged.

    Raw nodes span 512*30m. The explicit TerrainGrid discretization assigns one
    30m square cell to each node: 513*30m footprint, half-cell exterior margins.
    This numerical convention does not assert observed cell-average elevations.
    """
    report_path, report_sha, report, plan = _manifest(report_path, expected_report_sha256)
    if type(sample_index) is not int or not 0 <= sample_index < 6:
        raise ValueError("sample index must be in the fixed six-sample manifest")
    sample = report["samples"][sample_index]
    name = sample["raw_npz"]
    if Path(name).name != name:
        raise ValueError("raw source must be a report-directory filename")
    path = report_path.parent / name
    if file_sha256(path) != sample["raw_sha256"]:
        raise ValueError("raw TD source SHA256 differs")
    job = next(job for job in plan["jobs"] if job["seed"] == sample["seed"])
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"elevation", "climate", "metadata", "generation_config"}:
            raise ValueError("raw TD elevation/climate/metadata/config archive required")
        height = archive["elevation"]
        climate = archive["climate"]
        metadata = json.loads(str(archive["metadata"].item()))
        config_text = str(archive["generation_config"].item())
        config = json.loads(config_text)
        if (height.shape != (513, 513) or height.dtype != np.float32 or not np.isfinite(height).all()
                or climate.ndim != 3 or climate.shape[0] < 4 or climate.shape[1:] != height.shape
                or not np.isfinite(climate).all()):
            raise ValueError("finite full-resolution TD source required")
        height = height.astype(np.float64)
    if (metadata.get("backend") != "TerrainDiffusion/WorldPipeline"
            or metadata.get("native_resolution_m") != 30
            or metadata.get("native_origin") != sample["native_origin"]
            or str(metadata.get("seed")) != str(sample["seed"])
            or metadata.get("identity") != job["generation_identity"]
            or sample["generation_identity"] != job["generation_identity"]
            or sample["condition_sha256"] != job["condition_sha256"]
            or config != job["generation_config"]):
        raise ValueError("raw TD metadata or full generation configuration differs")
    origin = sample["native_origin"]
    if len(origin) != 2 or any(type(value) is not int for value in origin):
        raise ValueError("integer native X/Z origin required")
    datum = metadata.get("vertical_datum") or "unknown_local_relative"
    terrain = TerrainGrid(height, np.ones(height.shape, bool), origin[0] * 30., origin[1] * 30., 30., 30.,
        "generated_terrain", sample["raw_sha256"], sample["raw_sha256"],
        crs=metadata.get("crs"), vertical_datum=datum, generation_seed=sample["seed"],
        condition_summary=sample["condition_sha256"], source_path=str(path))
    kind = np.full(height.shape, "interior", dtype="U24")
    kind[[0, -1], :] = "unknown_boundary"
    kind[:, [0, -1]] = "unknown_boundary"
    boundary_record = {"policy": "all_perimeter_unknown_pending", "source_sha256": sample["raw_sha256"],
                       "no_external_inflow_evidence": True, "natural_outlet_verified": False}
    boundary = BoundaryGrid(kind, np.zeros(height.shape, bool), "TD-unresolved-exterior", identity({}, boundary_record))
    return register_source(terrain, boundary, source_metadata={
        "generation_metadata": metadata, "generation_config": config,
        "generation_config_identity_sha256": identity({}, config),
        "generation_config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
        "model_metadata": job.get("model_metadata"), "generation_identity": job["generation_identity"],
        "source_identity_sha256": terrain.source_id, "raw_source_sha256": sample["raw_sha256"],
        "generation_report_path": str(report_path), "generation_report_sha256": report_sha,
        "generation_plan_path": report["plan_path"], "generation_plan_sha256": report["plan_sha256"],
        "sample_index": sample_index, "sample_name": name,
        "actual_origin_m_xz": [terrain.x0_m, terrain.z0_m], "no_wet_mask_declared": True,
        "selection": "all_six_frozen_manifest_order_no_output_filtering",
        "boundary_evidence_sha256": boundary.source_sha256, "boundary_policy": boundary_record,
        "vertical_datum_status": "declared_in_raw_metadata" if metadata.get("vertical_datum") else "unknown_local_relative",
        "grid_semantics": "raw_node_values_assigned_to_cell_centres_without_averaging_or_height_projection",
        "node_span_m_xz": [15360., 15360.], "cell_footprint_m_xz": [15390., 15390.],
        "lake_sea_evidence": "not_present_in_raw_archive"})


def load_generated_td_sources(report_path, *, expected_report_sha256=None):
    """Return all six registrations in immutable manifest order."""
    return [load_generated_td_source(report_path, index, expected_report_sha256=expected_report_sha256)
            for index in range(6)]
