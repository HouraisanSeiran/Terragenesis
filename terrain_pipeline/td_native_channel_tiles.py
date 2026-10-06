"""Bounded global-lattice derived bed tiles; no new terrain or water solution."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_native_channel_geometry import validate_channel_geometry


MAX_AXIS_NODES = 512
MAX_BYTES = 1024 ** 3
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")


@dataclass(frozen=True)
class TileRecipe:
    sample_spacing_m: float = 1.
    sweep_profile: str = "bounded-capsule-cosine-max-cut-v1"

    def __post_init__(self):
        if self.sample_spacing_m not in (.5, 1., 2.) or self.sweep_profile != "bounded-capsule-cosine-max-cut-v1":
            raise ValueError("declared tile sampling/profile required")


def _window(window):
    if len(window) != 4 or any(type(value) is not int for value in window):
        raise ValueError("window requires integer global [x0,x1,z0,z1] inclusive lattice bounds")
    first_x, last_x, first_z, last_z = window
    if not (0 <= first_x <= last_x and 0 <= first_z <= last_z):
        raise ValueError("invalid global lattice window")
    shape = (last_z - first_z + 1, last_x - first_x + 1)
    if max(shape) > MAX_AXIS_NODES:
        raise ValueError("tile axis node budget exceeded")
    return shape


def _native_samples(geometry, world_x, world_z):
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    origin = metadata["origin_m_xz"]
    coarse_spacing = metadata["spacing_m"]
    rows, columns = metadata["grid_shape"]
    grid_x = (world_x - origin[0]) / coarse_spacing
    grid_z = (world_z - origin[1]) / coarse_spacing
    if (np.any(grid_x < 0) or np.any(grid_x > columns - 1) or
            np.any(grid_z < 0) or np.any(grid_z > rows - 1)):
        raise ValueError("fine window outside native sample extent")
    lower_x = np.minimum(np.floor(grid_x).astype(np.int64), columns - 1)
    lower_z = np.minimum(np.floor(grid_z).astype(np.int64), rows - 1)
    upper_x = np.minimum(lower_x + 1, columns - 1)
    upper_z = np.minimum(lower_z + 1, rows - 1)
    node_ids = arrays["node_cell_ids"]
    native_bed = arrays["node_native_bed_m"]

    def sample(sample_x, sample_z):
        cells = sample_z * columns + sample_x
        positions = np.searchsorted(node_ids, cells)
        if np.any(positions >= len(node_ids)):
            raise ValueError("native bilinear stencil contains unknown cells")
        if not np.array_equal(node_ids[positions], cells):
            raise ValueError("native bilinear stencil contains unknown cells")
        return native_bed[positions]

    fraction_x = grid_x - lower_x
    fraction_z = grid_z - lower_z
    north = sample(lower_x, lower_z) * (1. - fraction_x) + sample(upper_x, lower_z) * fraction_x
    south = sample(lower_x, upper_z) * (1. - fraction_x) + sample(upper_x, upper_z) * fraction_x
    return north * (1. - fraction_z) + south * fraction_z


def build_channel_tile(geometry, *, window, recipe=TileRecipe(), edge_order=None):
    """Sample an inclusive global lattice; overlapping windows use identical arithmetic."""
    validate_channel_geometry(geometry)
    shape = _window(window)
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    origin = metadata["origin_m_xz"]
    first_x, last_x, first_z, last_z = window
    lattice_x, lattice_z = np.meshgrid(np.arange(first_x, last_x + 1, dtype=np.int64),
                                      np.arange(first_z, last_z + 1, dtype=np.int64))
    world_x = origin[0] + lattice_x * recipe.sample_spacing_m
    world_z = origin[1] + lattice_z * recipe.sample_spacing_m
    native_bed = _native_samples(geometry, world_x, world_z)
    cut = np.zeros(shape)
    active_edges = np.flatnonzero(arrays["edge_geometry_active"])
    if edge_order is None:
        edge_order = active_edges
    else:
        edge_order = np.asarray(edge_order)
        if edge_order.dtype.kind not in "iu" or not np.array_equal(np.sort(edge_order), active_edges):
            raise ValueError("edge order must include each active edge exactly once")
    node_indices = np.searchsorted(arrays["node_cell_ids"], arrays["edge_cell_ids"])
    included = []
    for edge_index in edge_order:
        endpoints = arrays["edge_centerline_xyz_m"][edge_index][:, [0, 2]]
        endpoint_nodes = node_indices[edge_index]
        widths = arrays["node_width_m"][endpoint_nodes]
        incisions = arrays["node_candidate_incision_m"][endpoint_nodes]
        radius = float(widths.max()) / 2.
        min_x, min_z = endpoints.min(axis=0) - radius
        max_x, max_z = endpoints.max(axis=0) + radius
        x_begin = int(np.searchsorted(world_x[0], min_x, side="left"))
        x_end = int(np.searchsorted(world_x[0], max_x, side="right"))
        z_begin = int(np.searchsorted(world_z[:, 0], min_z, side="left"))
        z_end = int(np.searchsorted(world_z[:, 0], max_z, side="right"))
        if x_begin == x_end or z_begin == z_end:
            continue
        selection = np.s_[z_begin:z_end, x_begin:x_end]
        delta = endpoints[1] - endpoints[0]
        length_squared = float(np.dot(delta, delta))
        if not math.isfinite(length_squared) or length_squared <= 0:
            raise ValueError("zero-length sweep")
        fraction = np.clip(((world_x[selection] - endpoints[0, 0]) * delta[0] +
                            (world_z[selection] - endpoints[0, 1]) * delta[1]) / length_squared, 0., 1.)
        distance = np.hypot(world_x[selection] - endpoints[0, 0] - fraction * delta[0],
                            world_z[selection] - endpoints[0, 1] - fraction * delta[1])
        half_width = (widths[0] * (1. - fraction) + widths[1] * fraction) / 2.
        incision = incisions[0] * (1. - fraction) + incisions[1] * fraction
        normalized = distance / half_width
        edge_cut = np.where(normalized < 1., incision * .5 * (1. + np.cos(np.pi * np.minimum(normalized, 1.))), 0.)
        cut[selection] = np.maximum(cut[selection], edge_cut)
        included.append(int(edge_index))
    result_arrays = dict(lattice_x=lattice_x, lattice_z=lattice_z,
                         native_bilinear_bed_m=native_bed, candidate_cut_m=cut,
                         candidate_bed_m=native_bed - cut,
                         contributing_edge_ids=np.asarray(sorted(included), dtype=np.int64))
    result_metadata = dict(schema="td-native-channel-tile-v1", algorithm="global-lattice-bounded-sweep-v1",
                           geometry_identity=geometry["identity_sha256"], window=list(window), recipe=asdict(recipe),
                           origin_m_xz=list(origin), coordinates="arrays [z,x]; x east, z south; metres",
                           coarse_spacing_m=metadata["spacing_m"], max_axis_nodes=MAX_AXIS_NODES, task_max_bytes=MAX_BYTES,
                           scope="derived fine bed expression; bilinear native bed adds no TD landform information",
                           profile_semantics="node recipe width/incision linearly interpolated along active edge; cosine normal section; bounded radial endpoint caps; max cut union, no fill",
                           section_representation="cosine sampled bed display candidate; distinct from geometry three-point V schematic, not the same resolved section",
                           junction_semantics="deterministic overlapping sweep union; not unified hydraulic joint surface",
                           water_semantics="no water surface interpolation or water generation",
                           sampling_review="0.5/1/2m expression sampling only; not physical spatial convergence",
                           **{name: False for name in FLAGS})
    result = dict(arrays=result_arrays, metadata=result_metadata,
                  identity_sha256=identity(result_arrays, result_metadata))
    validate_channel_tile(result)
    result["arrays"] = {name: readonly(values) for name, values in result_arrays.items()}
    return result


def validate_channel_tile(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-native-channel-tile-v1" or any(metadata.get(name) is not False for name in FLAGS):
        raise ValueError("tile schema/certification invalid")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("tile identity mismatch")
    TileRecipe(**metadata["recipe"])
    shape = _window(metadata["window"])
    if set(arrays) != {"lattice_x", "lattice_z", "native_bilinear_bed_m", "candidate_cut_m", "candidate_bed_m", "contributing_edge_ids"}:
        raise ValueError("tile fields invalid")
    if sum(values.nbytes for values in arrays.values()) > MAX_BYTES or any(not np.isfinite(values).all() for values in arrays.values()):
        raise ValueError("tile resource/nonfinite invalid")
    first_x, last_x, first_z, last_z = metadata["window"]
    expected_x, expected_z = np.meshgrid(np.arange(first_x, last_x + 1, dtype=np.int64),
                                        np.arange(first_z, last_z + 1, dtype=np.int64))
    for name, expected in (("lattice_x", expected_x), ("lattice_z", expected_z)):
        if arrays[name].dtype != np.int64 or not np.array_equal(arrays[name], expected):
            raise ValueError("tile global lattice mismatch")
    for name in ("native_bilinear_bed_m", "candidate_cut_m", "candidate_bed_m"):
        if arrays[name].shape != shape or arrays[name].dtype != np.float64:
            raise ValueError("tile bed shape/type invalid")
    if np.any(arrays["candidate_cut_m"] < 0) or not np.array_equal(arrays["candidate_bed_m"], arrays["native_bilinear_bed_m"] - arrays["candidate_cut_m"]):
        raise ValueError("tile no-fill relation invalid")
    edges = arrays["contributing_edge_ids"]
    if edges.dtype != np.int64 or edges.ndim != 1 or np.any(edges < 0) or np.any(np.diff(edges) <= 0):
        raise ValueError("tile contributing edge IDs invalid")
    origin = metadata["origin_m_xz"]
    if len(origin) != 2 or not np.isfinite(origin).all() or not math.isfinite(metadata["coarse_spacing_m"]) or metadata["coarse_spacing_m"] <= 0:
        raise ValueError("tile coordinates invalid")
    geometry_id = metadata["geometry_identity"]
    if not isinstance(geometry_id, str) or len(geometry_id) != 64 or any(character not in "0123456789abcdef" for character in geometry_id):
        raise ValueError("tile geometry identity invalid")
    return True


def split_window_2x2(window):
    _window(window)
    first_x, last_x, first_z, last_z = window
    middle_x, middle_z = (first_x + last_x) // 2, (first_z + last_z) // 2
    if middle_x == first_x or middle_z == first_z:
        raise ValueError("window too small for four tiles")
    return [(first_x, middle_x, first_z, middle_z), (middle_x, last_x, first_z, middle_z),
            (first_x, middle_x, middle_z, last_z), (middle_x, last_x, middle_z, last_z)]


def save_channel_tile(path, result):
    save_bundle(path, result, validator=validate_channel_tile)


def load_channel_tile(path, *, expected_sha256, expected_identity, geometry=None):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_channel_tile,
                         max_bytes=64 * 1024 ** 2)
    if result["identity_sha256"] != expected_identity or file_sha256(path) != expected_sha256:
        raise ValueError("external tile pin mismatch or changed")
    if geometry is not None:
        validate_channel_geometry(geometry)
        if geometry["identity_sha256"] != result["metadata"]["geometry_identity"]:
            raise ValueError("external geometry link mismatch")
        if (geometry["metadata"]["origin_m_xz"] != result["metadata"]["origin_m_xz"] or
                geometry["metadata"]["spacing_m"] != result["metadata"]["coarse_spacing_m"]):
            raise ValueError("tile source coordinate link mismatch")
    return result


def audit_tile_geometry(result, geometry):
    """Explicit derivation audit; never invoked by the cold loader."""
    validate_channel_tile(result)
    if geometry["identity_sha256"] != result["metadata"]["geometry_identity"]:
        raise ValueError("external geometry link mismatch")
    rebuilt = build_channel_tile(geometry, window=result["metadata"]["window"],
                                 recipe=TileRecipe(**result["metadata"]["recipe"]))
    for name, values in rebuilt["arrays"].items():
        if not np.array_equal(values, result["arrays"][name]):
            raise ValueError("tile differs from geometry sweep")
    return True
