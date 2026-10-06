"""Joined candidate bed mesh from four saved 1m tiles; never generates water."""

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, publish_bytes, readonly, save_bundle
from terrain_pipeline.td_native_channel_tiles import load_channel_tile, validate_channel_tile


MAX_VERTICES = 512 * 512
MAX_TRIANGLES = 2 * 511 * 511
MAX_BYTES = 1024 ** 3
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")


def _limits(rows, columns):
    vertices = rows * columns
    triangles = 2 * (rows - 1) * (columns - 1)
    estimated_bytes = vertices * 128 + triangles * 192
    if min(rows, columns) < 2 or vertices > MAX_VERTICES or triangles > MAX_TRIANGLES or estimated_bytes > MAX_BYTES:
        raise ValueError("surface preflight vertex/triangle/byte budget exceeded")
    return vertices, triangles, estimated_bytes


def _triangles(rows, columns):
    southwest = (np.arange(rows - 1)[:, None] * columns + np.arange(columns - 1)).ravel()
    southeast = southwest + 1
    northwest = southwest + columns
    northeast = northwest + 1
    return np.stack((np.column_stack((southwest, northwest, northeast)),
                     np.column_stack((southwest, northeast, southeast))), axis=1).reshape(-1, 3).astype(np.int64)


def _normals(vertices, triangles):
    triangle_normals = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]],
                                vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
    lengths = np.linalg.norm(triangle_normals, axis=1)
    if np.any(lengths <= 0) or not np.isfinite(lengths).all() or np.any(triangle_normals[:, 1] <= 0):
        raise ValueError("degenerate or downward triangle")
    vertex_normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(vertex_normals, triangles[:, corner], triangle_normals)
    vertex_normals /= np.linalg.norm(vertex_normals, axis=1)[:, None]
    triangle_normals /= lengths[:, None]
    return triangle_normals, vertex_normals


def build_channel_surface(tiles, *, geometry):
    """Explicit join operation; input validity means every saved lattice point exists."""
    from terrain_pipeline.td_native_channel_geometry import validate_channel_geometry
    validate_channel_geometry(geometry)
    if len(tiles) != 4:
        raise ValueError("exactly four 1m tiles required")
    for tile in tiles:
        validate_channel_tile(tile)
        metadata = tile["metadata"]
        if metadata["recipe"]["sample_spacing_m"] != 1.:
            raise ValueError("mixed LOD requires explicit resampling; only 1m accepted")
        if (metadata["geometry_identity"] != geometry["identity_sha256"] or
                metadata["origin_m_xz"] != geometry["metadata"]["origin_m_xz"] or
                metadata["coarse_spacing_m"] != geometry["metadata"]["spacing_m"] or
                metadata["recipe"] != tiles[0]["metadata"]["recipe"]):
            raise ValueError("tile geometry/source/recipe link mismatch")
    if len({tile["identity_sha256"] for tile in tiles}) != 4:
        raise ValueError("duplicate tile")
    windows = [tile["metadata"]["window"] for tile in tiles]
    first_x, last_x = min(window[0] for window in windows), max(window[1] for window in windows)
    first_z, last_z = min(window[2] for window in windows), max(window[3] for window in windows)
    rows, columns = last_z - first_z + 1, last_x - first_x + 1
    vertices_count, triangles_count, estimated_bytes = _limits(rows, columns)
    native = np.zeros((rows, columns))
    candidate = np.zeros((rows, columns))
    cut = np.zeros((rows, columns))
    covered = np.zeros((rows, columns), bool)
    for tile in tiles:
        window = tile["metadata"]["window"]
        selection = np.s_[window[2]-first_z:window[3]-first_z+1, window[0]-first_x:window[1]-first_x+1]
        overlap = covered[selection]
        for joined, name in ((native, "native_bilinear_bed_m"), (candidate, "candidate_bed_m"), (cut, "candidate_cut_m")):
            values = tile["arrays"][name]
            if not np.array_equal(joined[selection][overlap], values[overlap]):
                raise ValueError("overlapping tile values conflict")
            joined[selection] = values
        covered[selection] = True
    if not covered.all():
        raise ValueError("surface hole or unknown validity")
    lattice_x, lattice_z = np.meshgrid(np.arange(first_x, last_x + 1, dtype=np.int64),
                                      np.arange(first_z, last_z + 1, dtype=np.int64))
    origin = geometry["metadata"]["origin_m_xz"]
    vertices = np.column_stack((origin[0] + lattice_x.ravel(), candidate.ravel(), origin[1] + lattice_z.ravel()))
    triangles = _triangles(rows, columns)
    face_normals, vertex_normals = _normals(vertices, triangles)
    arrays = dict(vertex_lattice_xz=np.column_stack((lattice_x.ravel(), lattice_z.ravel())),
                  vertices_xyz_m=vertices, triangles=triangles, face_normals_xyz=face_normals,
                  vertex_normals_xyz=vertex_normals, native_bilinear_bed_m=native.ravel(),
                  candidate_cut_m=cut.ravel(), valid_vertex_mask=covered.ravel())
    metadata = dict(schema="td-native-channel-surface-v1", algorithm="global-lattice-fixed-diagonal-bed-v1",
                    window=[first_x, last_x, first_z, last_z], origin_m_xz=list(origin), sample_spacing_m=1.,
                    coordinates="physical metres world [x,y,z]; x east, y up, z south",
                    triangle_convention="each cell diagonal (x,z) to (x+1,z+1); upward right-hand winding",
                    validity="all vertices explicitly covered by finite saved tiles; unknown validity rejected",
                    geometry_identity=geometry["identity_sha256"],
                    hierarchy_identity=geometry["metadata"]["hierarchy_identity"],
                    hour_page_identity=geometry["metadata"]["hour_page_identity"],
                    forcing_identity=geometry["metadata"]["forcing_identity"],
                    candidate_tile_identities=sorted(tile["identity_sha256"] for tile in tiles),
                    source_representation="native coarse bed bilinear samples; no new TD landform information",
                    candidate_representation="cosine sampled cut union mesh; distinct from three-point V schematic",
                    water_generated=False, scope="diagnostic joined candidate bed only; no water or hydraulics",
                    max_vertices=MAX_VERTICES, max_triangles=MAX_TRIANGLES, task_max_bytes=MAX_BYTES,
                    vertices=vertices_count, triangle_count=triangles_count, preflight_estimated_bytes=estimated_bytes,
                    **{name: False for name in FLAGS})
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_channel_surface(result)
    result["arrays"] = {name: readonly(values) for name, values in arrays.items()}
    return result


def validate_channel_surface(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata.get("schema") != "td-native-channel-surface-v1" or metadata.get("sample_spacing_m") != 1. or
            metadata.get("water_generated") is not False or any(metadata.get(name) is not False for name in FLAGS)):
        raise ValueError("surface schema/LOD/no-water flags invalid")
    if identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("surface identity mismatch")
    window = metadata["window"]
    if len(window) != 4 or any(type(value) is not int or value < 0 for value in window):
        raise ValueError("surface window invalid")
    first_x, last_x, first_z, last_z = window
    rows, columns = last_z-first_z+1, last_x-first_x+1
    vertices_count, triangle_count, estimated_bytes = _limits(rows, columns)
    if metadata["vertices"] != vertices_count or metadata["triangle_count"] != triangle_count or metadata["preflight_estimated_bytes"] != estimated_bytes:
        raise ValueError("surface counts invalid")
    if set(arrays) != {"vertex_lattice_xz", "vertices_xyz_m", "triangles", "face_normals_xyz", "vertex_normals_xyz", "native_bilinear_bed_m", "candidate_cut_m", "valid_vertex_mask"}:
        raise ValueError("surface fields invalid")
    if sum(values.nbytes for values in arrays.values()) > MAX_BYTES or any(not np.isfinite(values).all() for values in arrays.values()):
        raise ValueError("surface nonfinite/resource invalid")
    lattice_x, lattice_z = np.meshgrid(np.arange(first_x, last_x+1, dtype=np.int64), np.arange(first_z, last_z+1, dtype=np.int64))
    expected_lattice = np.column_stack((lattice_x.ravel(), lattice_z.ravel()))
    if arrays["vertex_lattice_xz"].dtype != np.int64 or not np.array_equal(arrays["vertex_lattice_xz"], expected_lattice):
        raise ValueError("surface lattice duplicate/hole/order invalid")
    for name in ("native_bilinear_bed_m", "candidate_cut_m"):
        if arrays[name].dtype != np.float64 or arrays[name].shape != (vertices_count,):
            raise ValueError("surface sample shape invalid")
    mask = arrays["valid_vertex_mask"]
    if mask.dtype != bool or mask.shape != (vertices_count,) or not mask.all():
        raise ValueError("surface unknown validity")
    origin = metadata["origin_m_xz"]
    if len(origin) != 2 or not np.isfinite(origin).all():
        raise ValueError("surface origin invalid")
    expected_vertices = np.column_stack((origin[0]+expected_lattice[:, 0], arrays["native_bilinear_bed_m"]-arrays["candidate_cut_m"], origin[1]+expected_lattice[:, 1]))
    if np.any(arrays["candidate_cut_m"] < 0) or arrays["vertices_xyz_m"].dtype != np.float64 or not np.array_equal(arrays["vertices_xyz_m"], expected_vertices):
        raise ValueError("surface world/no-fill relation invalid")
    if arrays["triangles"].dtype != np.int64 or not np.array_equal(arrays["triangles"], _triangles(rows, columns)):
        raise ValueError("surface diagonal/winding/topology invalid")
    for name, expected in zip(("face_normals_xyz", "vertex_normals_xyz"), _normals(expected_vertices, arrays["triangles"])):
        if not np.array_equal(arrays[name], expected):
            raise ValueError("surface normals invalid")
    ids = [metadata[name] for name in ("geometry_identity", "hierarchy_identity", "hour_page_identity", "forcing_identity")]
    tile_ids = metadata["candidate_tile_identities"]
    if len(tile_ids) != 4 or tile_ids != sorted(set(tile_ids)):
        raise ValueError("surface tile source identities invalid")
    for value in ids + tile_ids:
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("surface source identity invalid")
    return True


def save_channel_surface(path, result):
    save_bundle(path, result, validator=validate_channel_surface)


def load_channel_surface(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_channel_surface, max_bytes=128 * 1024 ** 2)
    if result["identity_sha256"] != expected_identity or file_sha256(path) != expected_sha256:
        raise ValueError("surface external pin changed/mismatched")
    return result


def load_surface_tiles(records):
    if len(records) != 4:
        raise ValueError("four externally pinned tiles required")
    for record in records:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("tile source pin mismatch")
    tiles = [load_channel_tile(**record) for record in records]
    for record in records:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("tile source changed while reading")
    return tiles


def export_surface_obj(path, result):
    validate_channel_surface(result)
    arrays, metadata = result["arrays"], result["metadata"]
    lines = ["# physical metres XYZ; x east, y up, z south; candidate bed only; no water",
             "# surface_identity " + result["identity_sha256"], "# geometry_identity " + metadata["geometry_identity"]]
    for vertex in arrays["vertices_xyz_m"]:
        lines.append("v " + " ".join(format(float(value), ".17g") for value in vertex))
    for normal in arrays["vertex_normals_xyz"]:
        lines.append("vn " + " ".join(format(float(value), ".17g") for value in normal))
    for triangle in arrays["triangles"]:
        lines.append("f " + " ".join(str(int(index)+1) + "//" + str(int(index)+1) for index in triangle))
    encoded = ("\n".join(lines) + "\n").encode("ascii")
    if len(encoded) > MAX_BYTES:
        raise ValueError("OBJ byte budget exceeded")
    publish_bytes(path, encoded)
