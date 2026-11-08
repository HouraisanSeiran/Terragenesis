"""Conservative linear stage and velocity over spatial canonical subcell beds."""

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import prepare_subgrid_support, storage_stages
from terrain_pipeline.single_domain_shallow_water_support_v5 import _reconstruct


def prepare_support(bed):
    support, datum = prepare_subgrid_support(bed)
    canonical = bed["arrays"]["canonical_bed_center_m"]-datum
    rows, columns = bed["arrays"]["H2_m"].shape
    factor = int(bed["metadata"]["spacing_m"])
    support["subcell_bed_position_relative_m"] = canonical.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows*columns, factor, factor)
    return support, datum


def reconstruct(state, bed, support, boundary_kind, tailwater):
    stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
    velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = _reconstruct(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
    slope_x, slope_z = faces[1]-faces[0], faces[3]-faces[2]
    factor = support["subcell_bed_position_relative_m"].shape[1]
    coordinate = (np.arange(factor)+.5)/factor-.5
    x, z = np.meshgrid(coordinate, coordinate)
    eta_offset = slope_x[:, 0, None, None]*x+slope_z[:, 0, None, None]*z
    effective_bed = support["subcell_bed_position_relative_m"]-eta_offset
    sorted_effective_bed = np.sort(effective_bed.reshape(len(state), -1), axis=1)
    eta0 = storage_stages(state[:, 0], sorted_effective_bed, np.cumsum(sorted_effective_bed, axis=1))
    subdepth = np.maximum(eta0[:, None, None]-effective_bed, 0.)
    velocity_offset = slope_x[:, None, None, 1:]*x[None, :, :, None]+slope_z[:, None, None, 1:]*z[None, :, :, None]
    offset_momentum = np.mean(subdepth[:, :, :, None]*velocity_offset, axis=(1, 2))
    center_velocity = np.divide(state[:, 1:]-offset_momentum, state[:, 0, None],
        out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    return dict(center=np.column_stack((eta0, center_velocity)), slope_x=slope_x, slope_z=slope_z,
        subcell_depth=subdepth, subcell_velocity=center_velocity[:, None, None, :]+velocity_offset)


def face_fields(reconstruction, cells, axis, sign, factor):
    coordinate = (np.arange(factor)+.5)/factor-.5
    normal = reconstruction["slope_x" if axis == 0 else "slope_z"][cells]
    tangent = reconstruction["slope_z" if axis == 0 else "slope_x"][cells]
    return reconstruction["center"][cells, None, :]+sign*.5*normal[:, None, :]+coordinate[None, :, None]*tangent[:, None, :]


def internal_bed_pressure(reconstruction, support, *, spacing, gravity):
    bed = support["subcell_bed_position_relative_m"]
    factor = bed.shape[1]
    coordinate = (np.arange(factor)+.5)/factor-.5
    interfaces = (np.arange(factor-1)+1)/factor-.5
    eta0 = reconstruction["center"][:, 0, None, None]
    sx = reconstruction["slope_x"][:, 0, None, None]
    sz = reconstruction["slope_z"][:, 0, None, None]
    eta_x = eta0+sx*interfaces[None, None, :]+sz*coordinate[None, :, None]
    eta_z = eta0+sx*coordinate[None, None, :]+sz*interfaces[None, :, None]
    delta_x = np.maximum(eta_x-bed[:, :, 1:], 0.)**2-np.maximum(eta_x-bed[:, :, :-1], 0.)**2
    delta_z = np.maximum(eta_z-bed[:, 1:, :], 0.)**2-np.maximum(eta_z-bed[:, :-1, :], 0.)**2
    return .5*gravity*np.column_stack((delta_x.sum(axis=(1, 2)), delta_z.sum(axis=(1, 2))))/(spacing*factor)
