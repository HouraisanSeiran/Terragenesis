"""Event-independent identity for one validated natural channel bed shape."""

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.channel_geometry import validate_natural_channel_geometry
from terrain_pipeline.td_natural_river_network import validate_natural_river_network


SCHEMA = "td-natural-bed-shape-identity-v1"


def natural_bed_shape_identity(network, geometry):
    """Hash permanent bed shape independently of strong-event forcing.

    The stored geometry identity remains the complete composite provenance,
    including its full network identity. It is not the permanent bed identity.
    """
    validate_natural_river_network(network)
    validate_natural_channel_geometry(geometry)
    network_arrays = network["arrays"]
    geometry_arrays = geometry["arrays"]
    network_metadata = network["metadata"]
    geometry_metadata = geometry["metadata"]
    if geometry_metadata["network_identity_sha256"] != network["identity_sha256"]:
        raise ValueError("geometry belongs to another complete network bundle")
    for name in ("grid_shape", "spacing_m", "origin_m_xz"):
        if geometry_metadata[name] != network_metadata[name]:
            raise ValueError(f"natural bed {name} differs from network")
    for name in ("source_height_m", "valid_mask", "protected_mask", "open_boundary_mask",
                 "node_cell_ids", "edge_cell_ids", "node_width_m", "node_depth_m",
                 "node_representative_q_m3_s", "edge_requires_refinement"):
        if not np.array_equal(geometry_arrays[name], network_arrays[name]):
            raise ValueError(f"natural bed {name} differs from network")
    native_xz = network_arrays["node_native_xyz_m"][:, (0, 2)]
    if not np.array_equal(geometry_arrays["node_native_xz_m"], native_xz):
        raise ValueError("natural bed native nodes differ from network")
    arrays = {name: {"dtype": value.dtype.str, "shape": list(value.shape),
                     "sha256": array_hash(np.ascontiguousarray(value))}
              for name, value in sorted(geometry_arrays.items())}
    return digest({"schema": SCHEMA, "algorithm": SCHEMA,
                   "network_schema": network_metadata["schema"],
                   "geometry_schema": geometry_metadata["schema"],
                   "stable_network_identity_sha256": network_metadata["stable_identity_sha256"],
                   "grid_shape": network_metadata["grid_shape"],
                   "spacing_m": network_metadata["spacing_m"],
                   "origin_m_xz": network_metadata["origin_m_xz"],
                   "bed_shape_recipe": geometry_metadata["recipe"],
                   "geometry_arrays": arrays})
