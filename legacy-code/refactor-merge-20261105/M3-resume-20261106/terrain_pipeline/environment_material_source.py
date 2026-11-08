"""Prepare existing G2 material properties at finite native environment anchors.

The returned original G2 bundle can be persisted inside the seasonal product.
Rock porosity remains a bedrock property, separate from regolith pore volume.
No geology, permeability, layer stack or material thickness is invented here.
"""

import math
from copy import deepcopy

import numpy as np

from terrain_pipeline.common_infra import readonly
from terrain_pipeline.geology_properties import properties_at, validate_geology_properties


MAX_CELLS = 4096
SPACING_M = 30.
REQUIRED_FIELDS = {"x_m", "z_m", "rock_index", "class_index", "bed_hardness",
                   "bank_hardness", "erodibility_index", "mohs_hardness", "solubility", "porosity"}


def _anchors(context):
    height = np.asarray(context["height_m"])
    origin = context["origin_native_xz"]
    if (height.ndim != 2 or min(height.shape) < 1 or height.size > MAX_CELLS or
            not np.isfinite(height).all() or len(origin) != 2 or
            any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) for value in origin) or
            isinstance(context["spacing_m"], bool) or context["spacing_m"] != SPACING_M or
            isinstance(context["world_seed"], (bool, np.bool_)) or context["world_seed"] != 20261020):
        raise ValueError("material source requires bounded native30m seed20261020 context")
    rows, cols = np.indices(height.shape)
    return (origin[0] + cols) * SPACING_M, (origin[1] + rows) * SPACING_M


def prepare_material_source(context):
    """Sample G2 once at the same native anchors as the existing hardness source.

    Irregular node offsets are network geometry and do not move these anchors.
    The returned shape matches context; original G2 metadata records engineering
    table provenance, rock table identity, purpose-derived seeds and field status.
    """
    x, z = _anchors(context)
    result = properties_at(x, z, world_seed=20261020)
    validate_material_source(result, context)
    return result


def validate_material_source(bundle, context=None):
    """Validate the saved G2 bundle without resampling a field or reading terrain."""
    validate_geology_properties(bundle)
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    shape = arrays["x_m"].shape
    if (len(shape) != 2 or min(shape) < 1 or math.prod(shape) > MAX_CELLS or
            metadata["world_seed"] != 20261020 or metadata["form"] != "point_set" or
            metadata["point_count"] != math.prod(shape) or set(arrays) != REQUIRED_FIELDS or
            any(value.shape != shape for value in arrays.values())):
        raise ValueError("saved material source must match a bounded native G2 point grid")
    for name in ("solubility", "porosity", "bed_hardness"):
        if metadata["fields_status"].get(name) != "computed":
            raise ValueError("material property spatial lookup status mismatch")
    for name in ("intrinsic_permeability_m2", "uniaxial_strength_mpa"):
        if metadata["fields_status"].get(name) != "pending":
            raise ValueError("material helper has no declared extended property source")
    if metadata["fields_status"].get("bedrock_thickness_m") != "unknown_no_source":
        raise ValueError("material helper has no bedrock thickness or strata source")
    if context is not None:
        x, z = _anchors(context)
        if not np.array_equal(arrays["x_m"], x) or not np.array_equal(arrays["z_m"], z):
            raise ValueError("material source does not match environment native anchors")
    return True


def material_mass_inputs(bundle, context=None):
    """Existing G9 initializer inputs only; solubility/hardness are fractions."""
    validate_material_source(bundle, context)
    return {name: readonly(bundle["arrays"][name]) for name in ("bed_hardness", "solubility")}


def bedrock_porosity(bundle, context=None):
    """Read the original G2 rock volume fraction; never assign regolith_porosity."""
    validate_material_source(bundle, context)
    return readonly(bundle["arrays"]["porosity"])


def query_material_source(bundle, row, col):
    """Read one prepared material point, retaining unknown-property status."""
    validate_material_source(bundle)
    shape = bundle["arrays"]["x_m"].shape
    if (type(row) is not int or type(col) is not int or min(row, col) < 0 or
            row >= shape[0] or col >= shape[1]):
        raise ValueError("material query outside prepared native grid")
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    fields = {name: arrays[name][row, col].item() for name in
              ("x_m", "z_m", "rock_index", "class_index", "bed_hardness", "solubility")}
    fields["bedrock_porosity"] = float(arrays["porosity"][row, col])
    fields["status"] = {name: metadata["fields_status"][name] for name in
                        ("bed_hardness", "solubility", "intrinsic_permeability_m2", "bedrock_thickness_m")}
    fields["status"]["bedrock_porosity"] = metadata["fields_status"]["porosity"]
    fields["units"] = {"x_m": "m", "z_m": "m", "bed_hardness": "1", "solubility": "1",
                       "bedrock_porosity": "volume fraction", "intrinsic_permeability_m2": "m2",
                       "bedrock_thickness_m": "m"}
    fields["source"] = deepcopy({name: metadata[name] for name in
        ("world_seed", "rock_table_identity_sha256", "lithology_subseeds", "value_status",
         "synthetic_lithology", "measured_lithology")})
    fields["source"]["identity_sha256"] = bundle["identity_sha256"]
    fields["source"]["coordinate_semantics"] = "native30m anchors; irregular network node offsets not applied"
    return fields
