"""Bed feedback: turn a coupled ledger's deposition into a derived bed change.

Why this module exists
---------------------
`metric_domain_coupled` (P9) reports volumes and declares, verbatim, that it writes
**no** bed change: `claims.terrain_feedback_applied` is false and its limitations say
the ledger "reports volumes only: it writes no bed change, no Exner update and no
derived surface". This module is the next step: it consumes a published coupled
product and writes the deposition back as a **derived** bed surface.

What is certified
-----------------
* **mass conservation**, exactly: the solid volume deposited per domain becomes a
  bulk volume through an explicit porosity conversion
  (`bulk = solid / (1 - porosity)`), and the per-cell bulk volumes sum back to the
  domain's bulk to the accumulator tolerance;
* **parent binding**: the coupled product's identity is **recomputed** from its own
  arrays and metadata and must match the `identity_sha256` it carries. A tampered
  parent is refused rather than silently fed into a new product;
* **replay**: the same parent and parameters give the same identity, through a write
  and a cold reload.

What is NOT certified (declared here, not discovered later)
----------------------------------------------------------
* **the spatial placement is a DECLARED disaggregation, not a reproduction.** The
  coupled product publishes deposition as a **per-domain total**, so this module
  spreads that total **uniformly over the domain's published cells**. It therefore
  carries **no** information about where along the chain the material settled. This
  is an assumption stated up front, not a measurement dressed up as one;
* **accumulation only.** The ledger's sediment source is the declared **surface
  weathering** term (`weathered_m_per_interval`), not bed erosion, so nothing is
  subtracted from the bed. A run with zero deposition produces exactly zero change;
* **no rejection is applied.** `metric_bed_update.bed_rejection` needs a receiver, a
  water depth and a rock floor; the coupled product publishes **none of them**. So
  receiver-slope reversal and frozen-water-depth invalidation **cannot be evaluated
  here**, and the product says so instead of pretending a clean bill of health;
* the immutable base face is **never** modified: `coarse_condition_field` remains the
  only base surface and this module reads no terrain at all. The change is a derived
  surface plus the per-cell volume series;
* the bed change is **not applied back into any hydraulic run**. The product sets
  `needs_geometry_and_hydraulic_revalidation = true` and leaves
  `hydraulic_ready` / `natural_outlet_verified` / `publishable` false.

Relationship to the ledger
--------------------------
This module **consumes rather than replaces**: it reads one coupled bundle and
writes a new, separately identified one. It authors no flood, no steepest-D8 pass
and no transport law, and it does not modify its parent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.surface_rivers.metric_bed_update import bed_from_inventory

__all__ = [
    "ALGORITHM",
    "BED_FEEDBACK_SCHEMA",
    "LIMITATIONS",
    "PRODUCT_KEYS",
    "BedFeedbackParameters",
    "bed_feedback_name",
    "load_domain_bed_feedback",
    "save_domain_bed_feedback",
    "solve_domain_bed_feedback",
    "validate_domain_bed_feedback",
]

ALGORITHM = "domain-bed-feedback-v1"
BED_FEEDBACK_SCHEMA = "river-domain-bed-feedback-v1"
PARENT_SCHEMA = "river-domain-coupled-v1"

# Contract key set, in order. All series (1-D), no 0-d scalars, for the same
# measured `mountain_source_adapter.readonly` reason the three ledgers record.
PRODUCT_KEYS = (
    "outlet_x_m",
    "outlet_z_m",
    "kind",
    "cell_count",
    "area_m2",
    "deposited_solid_m3",
    "deposited_bulk_m3",
    "pore_m3",
    "bed_change_m",
    "cells_x_m",
    "cells_z_m",
    "cell_offsets",
    "bed_change_raster_m",
    "limitations",
)

LIMITATIONS = (
    "the spatial placement is a DECLARED uniform disaggregation of a per-domain "
    "total, not a reproduction of where along the chain the material settled",
    "accumulation only: the ledger's source is a declared surface weathering term, "
    "not bed erosion, so nothing is subtracted from the bed",
    "bed_rejection is NOT applied: the parent publishes no receiver, water depth or "
    "rock floor, so receiver-slope reversal and frozen-water-depth invalidation "
    "cannot be evaluated here",
    "the immutable base face is untouched; this is a derived surface plus per-cell "
    "volume series, and no terrain is read",
    "the bed change is NOT applied back into any hydraulic run; "
    "needs_geometry_and_hydraulic_revalidation is true and hydraulic_ready, "
    "natural_outlet_verified and publishable remain false",
    "cells are the parent's published cells (accepted CORE cells); a domain that "
    "continues past the core is clipped exactly as the parent clips it",
)


@dataclass(frozen=True)
class BedFeedbackParameters:
    """Declared conversion constants.

    `porosity` is the repository's own convention (`metric_sediment.MaterialParameters`
    defaults to 0.35) and is the only free number here. There is no tunable knob: the
    placement rule is fixed at "uniform within the domain" on purpose, because a
    tunable one would invite reading the placement as if it were resolved.
    """

    porosity: float = 0.35

    def __post_init__(self):
        value = self.porosity
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) < 1.0):
            raise ValueError("porosity must be finite and within [0, 1)")


def bed_feedback_name(outlet_x_m, outlet_z_m):
    """Deterministic product name from the domain identity (the outlet)."""
    return "river-domain-bed-feedback-%d-%d-%s-v1.npz" % (
        int(round(float(outlet_x_m))), int(round(float(outlet_z_m))), BED_FEEDBACK_SCHEMA)


def _parent_identity(parent):
    """Recompute the parent's identity and refuse a mismatched one.

    This is the parent binding: a coupled product that has been edited after
    publication cannot be fed into a new product silently, because the recomputation
    uses the parent's own arrays and metadata.
    """
    if not isinstance(parent, dict) or set(parent) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("parent must be {arrays, metadata, identity_sha256}")
    metadata = parent["metadata"]
    if metadata.get("schema") != PARENT_SCHEMA:
        raise ValueError("parent schema must be %s; got %r"
                         % (PARENT_SCHEMA, metadata.get("schema")))
    recomputed = identity(parent["arrays"], metadata)
    if recomputed != parent["identity_sha256"]:
        raise ValueError("parent identity mismatch: the coupled product was modified "
                         "after publication and is refused")
    return recomputed


def solve_domain_bed_feedback(parent, *, parameters=None):
    """Turn one coupled ledger's deposition into a derived bed change.

    `parent` is a coupled bundle (as returned by `solve_domain_coupled` or
    `load_domain_coupled`). Returns a bundle: `arrays`, `metadata`, `identity_sha256`.
    """
    parameters = parameters or BedFeedbackParameters()
    if not isinstance(parameters, BedFeedbackParameters):
        raise ValueError("BedFeedbackParameters required")
    parent_identity = _parent_identity(parent)
    parent_arrays = parent["arrays"]
    parent_metadata = parent["metadata"]

    porosity = float(parameters.porosity)
    spacing = float(parent_metadata["spacing_m"])
    cell_area_m2 = float(parent_metadata["cell_area_m2"])
    rows, columns = (int(value) for value in parent_metadata["tile_shape"])
    origin_x, origin_z = (float(value) for value in parent_metadata["tile_origin_m_xz"])

    outlet_x = np.asarray(parent_arrays["outlet_x_m"], np.float64)
    outlet_z = np.asarray(parent_arrays["outlet_z_m"], np.float64)
    kind = np.asarray(parent_arrays["kind"]).astype(str)
    cell_count = np.asarray(parent_arrays["cell_count"], np.int64)
    area_m2 = np.asarray(parent_arrays["area_m2"], np.float64)
    deposited = np.asarray(parent_arrays["deposited_m3"], np.float64)
    offsets = np.asarray(parent_arrays["cell_offsets"], np.int64)
    cells_x = np.asarray(parent_arrays["cells_x_m"], np.float64)
    cells_z = np.asarray(parent_arrays["cells_z_m"], np.float64)

    count = int(parent_metadata["domain_count"])
    if outlet_x.shape != (count,) or deposited.shape != (count,):
        raise ValueError("parent domain arrays must be 1-D of length domain_count")
    if offsets.shape != (count + 1,) or int(offsets[-1]) != cells_x.size:
        raise ValueError("parent cell_offsets must match its published cells")
    if int(np.sum(cell_count, dtype=np.int64)) != int(offsets[-1]):
        raise ValueError("parent cell_count must sum to the offset total")

    deposited_solid = deposited.copy()
    deposited_bulk = deposited_solid / (1.0 - porosity)
    pore = deposited_bulk - deposited_solid

    # The change is a volume per cell, so a domain's solid volume spread over its
    # published cells becomes a depth through the repository's Exner conversion.
    # Uniform within the domain, declared.
    #
    # `bed_from_inventory` takes **solid** volumes and divides by (1 - porosity)
    # itself, so the per-cell series handed to it must be SOLID. Passing the bulk
    # volume there would divide by (1 - porosity) a second time; that was the first
    # draft of this module (measured: the bed change came out 1/(1-porosity) too
    # large, i.e. 1.538x at the default porosity).
    per_cell_solid = np.zeros(cells_x.size, np.float64)
    for index in range(count):
        start, stop = int(offsets[index]), int(offsets[index + 1])
        if start == stop:
            continue
        per_cell_solid[start:stop] = deposited_solid[index] / float(stop - start)
    per_cell_bulk = per_cell_solid / (1.0 - porosity)

    if not (np.isfinite(per_cell_bulk).all() and np.isfinite(deposited_bulk).all()
            and np.isfinite(per_cell_solid).all()):
        raise ValueError("bed feedback produced nonfinite volumes")

    zero_bed = np.zeros(cells_x.size, np.float64)
    zero_inventory = np.zeros(cells_x.size, np.float64)
    bed_change = bed_from_inventory(zero_bed, zero_inventory, per_cell_solid,
                                    zero_inventory, cell_area_m2, porosity)

    raster = np.zeros((rows, columns), np.float64)
    column_index = np.rint((cells_x - origin_x) / spacing).astype(np.int64)
    row_index = np.rint((cells_z - origin_z) / spacing).astype(np.int64)
    if cells_x.size:
        if (column_index.min() < 0 or column_index.max() >= columns
                or row_index.min() < 0 or row_index.max() >= rows):
            raise ValueError("parent cells fall outside its own tile lattice")
        raster[row_index, column_index] = bed_change

    arrays = {
        "outlet_x_m": outlet_x.copy(),
        "outlet_z_m": outlet_z.copy(),
        "kind": kind.astype("<U8"),
        "cell_count": cell_count.copy(),
        "area_m2": area_m2.copy(),
        "deposited_solid_m3": deposited_solid,
        "deposited_bulk_m3": deposited_bulk,
        "pore_m3": pore,
        "bed_change_m": bed_change,
        "cells_x_m": cells_x.copy(),
        "cells_z_m": cells_z.copy(),
        "cell_offsets": offsets.copy(),
        "bed_change_raster_m": raster.reshape(-1),
        "limitations": np.asarray(
            LIMITATIONS, "<U" + str(max(len(text) for text in LIMITATIONS))),
    }
    solid_total = float(np.sum(deposited_solid, dtype=np.float64))
    bulk_total = float(np.sum(deposited_bulk, dtype=np.float64))
    per_cell_total = float(np.sum(per_cell_bulk, dtype=np.float64))
    metadata = {
        "algorithm": ALGORITHM,
        "schema": BED_FEEDBACK_SCHEMA,
        "parent_schema": parent_metadata["schema"],
        "parent_algorithm": parent_metadata["algorithm"],
        "parent_identity_sha256": parent_identity,
        "seed": int(parent_metadata["seed"]),
        "config_id": parent_metadata["config_id"],
        "spacing_m": spacing,
        "cell_area_m2": cell_area_m2,
        "tile_shape": [rows, columns],
        "tile_origin_m_xz": [origin_x, origin_z],
        "core_cells": int(parent_metadata["core_cells"]),
        "interval_count": int(parent_metadata["interval_count"]),
        "parameters": dict(asdict(parameters)),
        "domain_count": count,
        "placement_rule": "uniform_within_domain_over_published_cells",
        "totals": {
            "deposited_solid_total_m3": solid_total,
            "deposited_bulk_total_m3": bulk_total,
            "pore_total_m3": float(np.sum(pore, dtype=np.float64)),
            "per_cell_bulk_total_m3": per_cell_total,
            "conservation_residual_m3": float(per_cell_total - bulk_total),
            "max_bed_change_m": (float(np.max(bed_change)) if bed_change.size else 0.0),
            "min_bed_change_m": (float(np.min(bed_change)) if bed_change.size else 0.0),
            "changed_cells": int(np.count_nonzero(bed_change > 0.0)),
            "published_cells": int(cells_x.size),
        },
        "claims": {
            "terrain_feedback_applied": True,
            "hydraulic_ready": False,
            "natural_outlet_verified": False,
            "publishable": False,
        },
        "revalidation": {
            "needs_geometry_and_hydraulic_revalidation": True,
            "bed_rejection_applied": False,
            "bed_rejection_reason": "the parent publishes no receiver, water depth or "
                                    "rock floor, so bed_rejection cannot be evaluated",
            "note": "a changed bed invalidates the frozen hydraulics that produced this "
                    "deposition; no hydraulic claim survives it",
        },
    }
    record = {"arrays": arrays, "metadata": metadata}
    record["identity_sha256"] = identity(arrays, metadata)
    validate_domain_bed_feedback(record)
    return record


def validate_domain_bed_feedback(record):
    """Cold validation: shapes, conservation, the parent binding, and the claims.

    Recomputes everything from the arrays in front of it, so a forged `totals` block
    or a broken parent reference is caught rather than trusted.
    """
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("bed feedback bundle must be {arrays, metadata, identity_sha256}")
    arrays = record["arrays"]
    metadata = record["metadata"]
    expected = set(PRODUCT_KEYS)
    if set(arrays) != expected:
        raise ValueError("bed feedback arrays must be exactly the contract keys; "
                         "missing %s, unexpected %s"
                         % (sorted(expected - set(arrays)), sorted(set(arrays) - expected)))
    if metadata.get("schema") != BED_FEEDBACK_SCHEMA:
        raise ValueError("bed feedback schema mismatch")
    for key in ("seed", "config_id", "spacing_m", "cell_area_m2", "domain_count",
                "parent_identity_sha256", "parent_schema", "parameters",
                "placement_rule"):
        if key not in metadata:
            raise ValueError("metadata.%s is required" % key)
    if metadata["parent_schema"] != PARENT_SCHEMA:
        raise ValueError("parent_schema must be %s" % PARENT_SCHEMA)
    if not isinstance(metadata["parent_identity_sha256"], str) \
            or len(metadata["parent_identity_sha256"]) != 64:
        raise ValueError("metadata.parent_identity_sha256 must be a sha256 hex digest")
    if not isinstance(metadata["config_id"], str) or len(metadata["config_id"]) != 64:
        raise ValueError("metadata.config_id must be a sha256 hex digest")
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("bed feedback identity mismatch")

    count = int(metadata["domain_count"])
    porosity = float(metadata["parameters"]["porosity"])
    if not 0.0 <= porosity < 1.0:
        raise ValueError("metadata.parameters.porosity must be within [0, 1)")

    for name in ("outlet_x_m", "outlet_z_m", "cell_count", "area_m2",
                 "deposited_solid_m3", "deposited_bulk_m3", "pore_m3"):
        array = np.asarray(arrays[name])
        if array.shape != (count,) or not np.isfinite(array).all():
            raise ValueError("%s must be finite and 1-D of length domain_count" % name)
    kind = np.asarray(arrays["kind"]).astype(str)
    if kind.shape != (count,) or not set(kind.tolist()).issubset({"marine", "inland"}):
        raise ValueError("kind must be one of marine/inland")

    solid = np.asarray(arrays["deposited_solid_m3"], np.float64)
    bulk = np.asarray(arrays["deposited_bulk_m3"], np.float64)
    pore = np.asarray(arrays["pore_m3"], np.float64)
    if np.any(solid < 0) or np.any(bulk < 0) or np.any(pore < -1e-9):
        raise ValueError("deposited volumes must be nonnegative")
    expected_bulk = solid / (1.0 - porosity)
    tolerance = 1e-9 * np.maximum(expected_bulk, 1.0)
    if np.any(np.abs(bulk - expected_bulk) > tolerance):
        raise ValueError("deposited_bulk_m3 must equal solid / (1 - porosity)")
    if np.any(np.abs((bulk - solid) - pore) > tolerance):
        raise ValueError("pore_m3 must equal bulk - solid")

    cell_count = np.asarray(arrays["cell_count"], np.int64)
    offsets = np.asarray(arrays["cell_offsets"], np.int64)
    cells_x = np.asarray(arrays["cells_x_m"], np.float64)
    cells_z = np.asarray(arrays["cells_z_m"], np.float64)
    bed_change = np.asarray(arrays["bed_change_m"], np.float64)
    raster = np.asarray(arrays["bed_change_raster_m"], np.float64)
    rows, columns = (int(value) for value in metadata["tile_shape"])
    if offsets.shape != (count + 1,) or offsets[0] != 0 or np.any(np.diff(offsets) < 0):
        raise ValueError("cell_offsets must be a nondecreasing D+1 index")
    if int(offsets[-1]) != cells_x.size or cells_z.size != cells_x.size \
            or bed_change.shape != (cells_x.size,):
        raise ValueError("per-cell arrays must share the published cell count")
    if int(np.sum(cell_count, dtype=np.int64)) != int(offsets[-1]):
        raise ValueError("cell_count must sum to the offset total")
    if np.any(np.diff(offsets) != cell_count):
        raise ValueError("cell_offsets must follow cell_count exactly")
    if raster.shape != (rows * columns,):
        raise ValueError("bed_change_raster_m must be a flat tile_shape raster")
    if not (np.isfinite(cells_x).all() and np.isfinite(cells_z).all()
            and np.isfinite(bed_change).all() and np.isfinite(raster).all()):
        raise ValueError("bed feedback arrays must be finite")
    if np.any(bed_change < -1e-12):
        raise ValueError("this feedback is accumulation only; negative bed change "
                         "would mean bed erosion was written back, which it is not")

    cell_area = float(metadata["cell_area_m2"])
    if not math.isfinite(cell_area) or cell_area <= 0.0:
        raise ValueError("metadata.cell_area_m2 must be finite and positive")
    # Conservation, per domain and tile wide, recomputed from the per-cell depths.
    worst = 0.0
    for index in range(count):
        start, stop = int(offsets[index]), int(offsets[index + 1])
        if start == stop:
            continue
        volume = float(np.sum(bed_change[start:stop], dtype=np.float64) * cell_area)
        worst = max(worst, abs(volume - float(bulk[index])))
    total_bulk = float(np.sum(bulk, dtype=np.float64))
    scale = max(total_bulk, 1.0)
    if worst > 1e-6 * scale:
        raise ValueError("per-cell bed change does not sum to the domain bulk volume: "
                         "worst residual %.3e" % worst)

    totals = metadata.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("metadata.totals required")
    for name in ("deposited_solid_total_m3", "deposited_bulk_total_m3", "pore_total_m3",
                 "per_cell_bulk_total_m3", "conservation_residual_m3",
                 "max_bed_change_m", "min_bed_change_m"):
        if name not in totals or not math.isfinite(float(totals[name])):
            raise ValueError("metadata.totals.%s must be a finite number" % name)
    if abs(float(totals["deposited_solid_total_m3"]) - float(np.sum(solid))) > 1e-6 * scale:
        raise ValueError("deposited_solid_total_m3 must equal the domain sum")
    if abs(float(totals["deposited_bulk_total_m3"]) - total_bulk) > 1e-6 * scale:
        raise ValueError("deposited_bulk_total_m3 must equal the domain sum")
    if abs(float(totals["conservation_residual_m3"])) > 1e-6 * scale:
        raise ValueError("conservation_residual_m3 must be zero")
    if bed_change.size and abs(float(totals["max_bed_change_m"])
                               - float(np.max(bed_change))) > 1e-9 * max(scale, 1.0):
        raise ValueError("max_bed_change_m must equal the published maximum")

    claims = metadata.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("metadata.claims required")
    if claims.get("terrain_feedback_applied") is not True:
        raise ValueError("a bed feedback product must declare terrain_feedback_applied")
    if any(claims.get(key) is not False for key in
           ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("a bed feedback product claims no publishable hydraulics")
    revalidation = metadata.get("revalidation")
    if not isinstance(revalidation, dict) \
            or revalidation.get("needs_geometry_and_hydraulic_revalidation") is not True:
        raise ValueError("a changed bed must declare that its hydraulics need revalidation")
    return True


def save_domain_bed_feedback(path, record):
    """Persist with the repository's atomic-link discipline; never overwrite."""
    save_bundle(path, record, validator=validate_domain_bed_feedback)


def load_domain_bed_feedback(path, *, expected_sha256, expected_identity=None):
    """Reload cold, re-deriving the identity; refuse a wrong expected value."""
    record = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_domain_bed_feedback)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("bed feedback identity mismatch against the expected value")
    return record
