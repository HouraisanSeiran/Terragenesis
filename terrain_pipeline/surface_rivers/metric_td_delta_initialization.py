"""Pure TD river-aligned initialization; no downstream landform construction."""
import numpy as np
from scipy.ndimage import map_coordinates


def prepare_td_initialization(base_bed, macro_bed, raw_td, residual, *, source_origin_xz,
                              source_spacing_m, mouth_xz, direction_xz,
                              shape=(160, 120), spacing_m=5., stub_length_m=60.,
                              stub_width_m=80., inlet_depth_m=1.5, cover_m=.3):
    direction = np.asarray(direction_xz, float)
    direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    rows, cols = np.indices(shape)
    along = rows*spacing_m-stub_length_m
    cross = (cols-shape[1]//2)*spacing_m
    world = np.asarray(mouth_xz)+along[..., None]*direction+cross[..., None]*normal
    coordinates = (world-np.asarray(source_origin_xz))/source_spacing_m
    if (np.any(coordinates < 0.) or np.any(coordinates[..., 0] > base_bed.shape[1]-1)
            or np.any(coordinates[..., 1] > base_bed.shape[0]-1)):
        raise ValueError("TD initialization footprint exceeds frozen source")
    arrays = {}
    for name, field in (("source_base_bed_m", base_bed), ("source_macro_bed_m", macro_bed),
                        ("raw_td_sample_m", raw_td), ("source_td_residual_m", residual)):
        arrays[name] = map_coordinates(field, [coordinates[..., 1], coordinates[..., 0]], order=1)
    initial = arrays["source_base_bed_m"].copy()
    length = int(round(stub_length_m/spacing_m))
    width = int(round(stub_width_m/spacing_m))
    first = shape[1]//2-width//2
    inlet = np.arange(first, first+width)
    stub = np.zeros(shape, bool)
    stub[:length, inlet] = True
    # Only the imported upstream boundary stub is constructed. Native interior
    # land remains routable cell_type=0, so deposition and bank change are free.
    initial[stub] = -inlet_depth_m
    cell_type = np.zeros(shape, np.int64)
    edge = np.zeros(shape, bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    cell_type[edge & (initial >= 0.)] = -2
    cell_type[edge & (initial < 0.)] = -1
    cell_type[stub] = 1
    stage = np.maximum(initial, 0.)
    depth = np.maximum(stage-initial, 0.)
    floor = initial-cover_m
    floor[edge] = initial[edge]
    construction = initial-arrays["source_base_bed_m"]
    arrays.update(initial_bed_m=initial, initial_stage_m=stage, initial_depth_m=depth,
        cell_type=cell_type, inlet_columns=inlet, inlet_stub_mask=stub,
        fixed_boundary_mask=edge, source_floor_m=floor,
        construction_height_delta_m=construction, local_world_xz_m=world,
        original_land_mask=arrays["source_base_bed_m"] >= 0.,
        initial_erodible_solid_m3=(initial-floor)*spacing_m**2*.65)
    report = {"schema": "td-natural-delta-initialization-v1", "spacing_m": spacing_m,
        "shape": list(shape), "sea_level_m": 0., "porosity": .35,
        "source_role": "frozen base_bed, macro+0.35*TD residual; no constructed fan/branch bed",
        "frame": {"downstream_direction_xz": direction.tolist(), "cross_direction_xz": normal.tolist(),
            "mouth_world_xz_m": np.asarray(mouth_xz).tolist(), "mouth_local_zx_cell": [length, shape[1]//2],
            "origin_world_xz_m": world[0, 0].tolist()},
        "construction": {"role": "single upstream inlet stub only; explicit geometric cut/fill, no sediment input",
            "cut_bulk_m3": float(np.maximum(-construction, 0.).sum()*spacing_m**2),
            "fill_bulk_m3": float(np.maximum(construction, 0.).sum()*spacing_m**2)},
        "marine_boundary_cells": {"upstream": int(np.count_nonzero(cell_type[0] == -1)),
            "left": int(np.count_nonzero(cell_type[:, 0] == -1)),
            "right": int(np.count_nonzero(cell_type[:, -1] == -1)),
            "downstream": int(np.count_nonzero(cell_type[-1] == -1))},
        "interior_land_routable_cells": int(np.count_nonzero((initial >= 0.) & ~edge)),
        "status": "prepare only; native integration not yet run; inherited 1.35% offshore slope unchanged"}
    return arrays, report
