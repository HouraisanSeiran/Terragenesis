"""Finite, restartable reduced marine sediment transport on a common SI grid."""
from dataclasses import dataclass, asdict, replace
import json

import numpy as np
from scipy import ndimage

from .surface_rivers.metric_coastal_transport import _face_transfer
from .surface_rivers.metric_fv_coastal_sediment import BedloadConfig, incident_wave_field


@dataclass(frozen=True)
class RiverPacket:
    input_id: str
    source_id: str
    start_s: float
    end_s: float
    row: int
    col: int
    water_m3: float | None
    solid_m3: float | None
    known: bool
    direction_xz: tuple
    width_m: float
    depth_m: float


@dataclass(frozen=True)
class MarineConfig:
    sea_level_m: float = 0.0
    tide_amplitude_m: float = 0.0
    tide_period_s: float = 44712.0
    wave_height_m: float = 0.0
    wave_direction_xz: tuple = (1.0, 0.0)
    transport_rate_s: float = 0.0
    entrainment_rate_s: float = 0.0
    settling_rate_s: float = 0.0
    export_rate_s: float = 0.0
    step_s: float = 300.0
    transverse_diffusivity_m2_s: float = 10.0
    active_sediment_layer_m: float = 0.1
    same_cell_wet_dry: bool = False


@dataclass(frozen=True)
class MarineState:
    base_bed_m: np.ndarray
    bed_solid_m3: np.ndarray
    mobile_solid_m3: np.ndarray
    porosity: np.ndarray
    valid_mask: np.ndarray
    ocean_seed_mask: np.ndarray
    spacing_m: float
    origin_xz_m: tuple
    source_identity: str
    time_s: float = 0.0
    exported_solid_m3: float = 0.0
    unresolved_solid_m3: float = 0.0
    water_input_m3: float = 0.0
    consumed_packets: tuple = ()
    stranded_solid_m3: np.ndarray | None = None

    @property
    def bed_m(self):
        return self.base_bed_m + self.bed_solid_m3 / (self.spacing_m ** 2 * (1 - self.porosity))


def make_state(*, base_bed_m, bed_solid_m3, mobile_solid_m3, porosity, valid_mask,
               ocean_seed_mask, spacing_m, origin_xz_m, source_identity, time_s=0.0, stranded_solid_m3=0):
    base = np.asarray(base_bed_m, dtype=float)
    if base.ndim != 2 or not base.size:
        raise ValueError("base must be a nonempty 2D grid")
    def array(value, dtype):
        result = np.broadcast_to(np.asarray(value, dtype=dtype), base.shape).copy()
        return result
    bed = array(bed_solid_m3, float)
    mobile = array(mobile_solid_m3, float)
    stranded = array(stranded_solid_m3, float)
    por = array(porosity, float)
    valid = array(valid_mask, bool)
    seeds = array(ocean_seed_mask, bool)
    edge = np.zeros(base.shape, bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    if (not np.isfinite(base).all() or not np.isfinite(bed).all() or not np.isfinite(mobile).all()
            or not np.isfinite(por).all() or not np.isfinite(stranded).all()
            or (bed < 0).any() or (mobile < 0).any() or (stranded < 0).any()
            or (por < 0).any() or (por >= 1).any() or (seeds & ~valid).any()
            or (seeds & ~edge).any() or ((bed + mobile + stranded)[~valid] != 0).any()
            or not np.isfinite(spacing_m) or spacing_m <= 0 or len(origin_xz_m) != 2
            or not np.isfinite(origin_xz_m).all() or not source_identity
            or not np.isfinite(time_s) or time_s < 0):
        raise ValueError("invalid marine state")
    return MarineState(base.copy(), bed, mobile, por, valid, seeds, float(spacing_m),
                       tuple(map(float, origin_xz_m)), source_identity, float(time_s), stranded_solid_m3=stranded)


def classify_ocean(state, sea_level_m):
    wet = state.valid_mask & (state.bed_m < sea_level_m)
    labels, _ = ndimage.label(wet)
    ids = np.unique(labels[state.ocean_seed_mask & wet])
    ids = ids[ids != 0]
    ocean = np.isin(labels, ids) & wet
    shore = state.valid_mask & ~ocean & ndimage.binary_dilation(ocean)
    return ocean, shore


def wave_exposure(state, ocean, depth, config):
    """Reuse straight incident rays; islands and dry cells cast a wave shadow."""
    boundary = np.flatnonzero(state.ocean_seed_mask)
    geometry = {"arrays": {"boundary_cell": boundary, "boundary_kind": np.full(boundary.size, 2)}}
    wave_config = BedloadConfig(wave_height_m=config.wave_height_m,
                                wave_direction_xz=tuple(map(int, config.wave_direction_xz)))
    return incident_wave_field(depth * ocean, geometry, wave_config)["wave_height_m"]


def _wet_receiver(ocean, row, col, direction_xz=(0., 0.)):
    if ocean[row, col]:
        return row, col
    options = []
    for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        r, c = row + dr, col + dc
        if 0 <= r < ocean.shape[0] and 0 <= c < ocean.shape[1] and ocean[r, c]:
            options.append((dc * direction_xz[0] + dr * direction_xz[1], r, c))
    if options:
        _, r, c = max(options)
        return r, c
    return None


def _park_and_release(mobile, stranded, ocean):
    stranded[~ocean] += mobile[~ocean]
    mobile[~ocean] = 0.
    for row, col in np.argwhere(stranded > 0):
        receiver = _wet_receiver(ocean, row, col)
        if receiver is not None:
            mobile[receiver] += stranded[row, col]
            stranded[row, col] = 0.


def _transverse_exchange(mobile, ocean, weights_x, weights_z, scale):
    """Paired four-face diffusion, with one shared donor cap as in _face_transfer."""
    demand = np.zeros_like(mobile)
    requests = []
    for axis, weights in ((1, weights_x), (0, weights_z)):
        for sign in (-1, 1):
            donor = [slice(None), slice(None)]
            receiver = [slice(None), slice(None)]
            donor[axis] = slice(1, None) if sign < 0 else slice(None, -1)
            receiver[axis] = slice(None, -1) if sign < 0 else slice(1, None)
            donor, receiver = tuple(donor), tuple(receiver)
            conductance = np.minimum(weights[donor], weights[receiver])
            amount = mobile[donor] * scale * conductance * ocean[donor] * ocean[receiver]
            demand[donor] += amount
            requests.append((donor, receiver, amount))
    limiter = np.minimum(1., np.divide(mobile, demand, out=np.ones_like(mobile), where=demand > 0))
    delta = np.zeros_like(mobile)
    for donor, receiver, amount in requests:
        transfer = amount * limiter[donor]
        delta[donor] -= transfer
        delta[receiver] += transfer
    return mobile + delta


def advance(state, packets, duration_s, config=MarineConfig()):
    values = [config.sea_level_m, config.tide_amplitude_m, config.tide_period_s,
              config.wave_height_m, config.transport_rate_s, config.entrainment_rate_s,
              config.settling_rate_s, config.export_rate_s, config.step_s,
              config.transverse_diffusivity_m2_s, config.active_sediment_layer_m, duration_s]
    if (not np.isfinite(values).all() or duration_s <= 0 or config.step_s <= 0
            or config.tide_period_s <= 0 or min(config.tide_amplitude_m, config.wave_height_m,
            config.transport_rate_s, config.entrainment_rate_s, config.settling_rate_s,
            config.export_rate_s, config.transverse_diffusivity_m2_s, config.active_sediment_layer_m) < 0 or tuple(config.wave_direction_xz) not in
            ((1, 0), (-1, 0), (0, 1), (0, -1))):
        raise ValueError("invalid forcing")
    records = [dict(record) for record in state.consumed_packets]
    seen = {record['input_id'] for record in records}
    for p in packets:
        direction = np.asarray(p.direction_xz, dtype=float)
        if (not p.input_id or not p.source_id or p.input_id in seen or not isinstance(p.known, bool)
                or not np.isfinite([p.start_s, p.end_s, p.width_m, p.depth_m]).all()
                or p.start_s < state.time_s or p.end_s <= p.start_s or p.width_m <= 0 or p.depth_m <= 0
                or direction.shape != (2,) or not np.isfinite(direction).all() or np.linalg.norm(direction) == 0
                or not isinstance(p.row, int) or not isinstance(p.col, int)
                or not (0 <= p.row < state.base_bed_m.shape[0] and 0 <= p.col < state.base_bed_m.shape[1])
                or not state.valid_mask[p.row, p.col]):
            raise ValueError("invalid or duplicate packet")
        if p.known:
            if (p.water_m3 is None or p.solid_m3 is None or not np.isfinite([p.water_m3, p.solid_m3]).all()
                    or p.water_m3 <= 0 or p.solid_m3 < 0):
                raise ValueError("known packet requires positive water and nonnegative solid")
        elif p.water_m3 is not None or p.solid_m3 is not None:
            raise ValueError("unknown packet quantities must be None")
        record = asdict(p)
        record['pending_solid_m3'] = 0.0 if p.known else None
        record['delivered_water_m3'] = 0.0 if p.known else None
        record['delivered_solid_m3'] = 0.0 if p.known else None
        records.append(record)
        seen.add(p.input_id)
    bed = state.bed_solid_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    stranded = np.zeros_like(mobile) if state.stranded_solid_m3 is None else state.stranded_solid_m3.copy()
    water = state.water_input_m3
    exported = state.exported_solid_m3
    t = state.time_s
    end = t + duration_s
    rows, cols = np.indices(bed.shape)
    while t < end:
        next_grid = (np.floor(t / config.step_s + 1e-10) + 1) * config.step_s
        boundaries = [end, next_grid]
        for rec in records:
            boundaries.extend(x for x in (rec['start_s'], rec['end_s']) if t < x < end)
        dt = min(boundaries) - t
        phase = 2 * np.pi * (t + dt / 2) / config.tide_period_s
        level = config.sea_level_m + config.tide_amplitude_m * np.sin(phase)
        current = replace(state, bed_solid_m3=bed, mobile_solid_m3=mobile)
        ocean, _ = classify_ocean(current, level)
        if config.same_cell_wet_dry:
            stranded[~ocean] += mobile[~ocean]
            mobile[~ocean] = 0.
            mobile[ocean] += stranded[ocean]
            stranded[ocean] = 0.
        else:
            _park_and_release(mobile, stranded, ocean)
        depth = np.maximum(level - current.bed_m, 0) * ocean
        activity = ocean * np.clip(depth / (depth + 1), 0, 1)
        plume_x = np.zeros_like(bed)
        plume_z = np.zeros_like(bed)
        diffusion_x = np.zeros_like(bed)
        diffusion_z = np.zeros_like(bed)
        for rec in records:
            overlap = max(0., min(t + dt, rec['end_s']) - max(t, rec['start_s']))
            if not rec['known']:
                continue
            rec.setdefault('pending_solid_m3', 0.)
            if overlap == 0:
                receiver = _wet_receiver(ocean, rec['row'], rec['col'], rec['direction_xz'])
                if receiver is not None and rec['pending_solid_m3'] > 0:
                    mobile[receiver] += rec['pending_solid_m3']
                    rec['pending_solid_m3'] = 0.
                continue
            span = rec['end_s'] - rec['start_s']
            fraction = overlap / span
            solid = rec['solid_m3'] * fraction
            delivered_water = rec['water_m3'] * fraction
            rec['pending_solid_m3'] += solid
            receiver = _wet_receiver(ocean, rec['row'], rec['col'], rec['direction_xz'])
            if receiver is not None:
                mobile[receiver] += rec['pending_solid_m3']
                rec['pending_solid_m3'] = 0.
            water += delivered_water
            rec['delivered_solid_m3'] += solid
            rec['delivered_water_m3'] += delivered_water
            direction = np.asarray(rec['direction_xz'], float)
            direction /= np.linalg.norm(direction)
            dx = (cols - rec['col']) * state.spacing_m
            dz = (rows - rec['row']) * state.spacing_m
            along = dx * direction[0] + dz * direction[1]
            across = -dx * direction[1] + dz * direction[0]
            length = max(5 * state.spacing_m, 8 * rec['width_m'])
            width = max(2 * state.spacing_m, 3 * rec['width_m'])
            plume = np.exp(-np.maximum(along, 0) / length - (across / width) ** 2)
            plume *= (along >= -state.spacing_m) * ocean
            speed = min(rec['water_m3'] / span / (rec['width_m'] * rec['depth_m']), 2.0)
            plume_x += speed * direction[0] * plume
            plume_z += speed * direction[1] * plume
            diffusion_x += min(speed / .5, 1.) * direction[1] ** 2 * plume
            diffusion_z += min(speed / .5, 1.) * direction[0] ** 2 * plume
        if config.wave_height_m:
            wave_height = wave_exposure(state, ocean, depth, config)
        else:
            wave_height = np.zeros_like(bed)
        wave = wave_height / (depth + wave_height + 1)
        tide = config.tide_amplitude_m * np.cos(phase)
        gx = np.gradient(current.bed_m, state.spacing_m, axis=1) if bed.shape[1] > 1 else np.zeros_like(bed)
        gz = np.gradient(current.bed_m, state.spacing_m, axis=0) if bed.shape[0] > 1 else np.zeros_like(bed)
        norm = np.maximum(np.hypot(gx, gz), 1e-12)
        magnitude = abs(tide) + wave + np.hypot(plume_x, plume_z)
        # Only the exposed bulk-thickness layer participates in this step;
        # thin covers retain the original inventory-limited behaviour.
        active_solid = np.minimum(bed, config.active_sediment_layer_m * state.spacing_m**2 * (1-state.porosity))
        entrained = active_solid * (1 - np.exp(-config.entrainment_rate_s * dt * magnitude)) * activity
        bed -= entrained
        mobile += entrained
        settled = mobile * (1 - np.exp(-config.settling_rate_s * dt)) * ocean
        mobile -= settled
        bed += settled
        vx = tide * gx / norm + wave * config.wave_direction_xz[0]
        vz = tide * gz / norm + wave * config.wave_direction_xz[1]
        mobile, _, _ = _face_transfer(mobile, vx, vz, np.full_like(bed, config.transport_rate_s * dt), activity, ocean, ocean)
        mobile, _, _ = _face_transfer(mobile, plume_x, plume_z, np.full_like(bed, dt / state.spacing_m), activity, ocean, ocean)
        mobile = _transverse_exchange(mobile, ocean, np.minimum(diffusion_x, 1.),
                                      np.minimum(diffusion_z, 1.),
                                      config.transverse_diffusivity_m2_s * dt / state.spacing_m ** 2)
        out = mobile * (1 - np.exp(-config.export_rate_s * dt)) * (state.ocean_seed_mask & ocean)
        mobile -= out
        exported += float(out.sum())
        t += dt
    final = replace(state, bed_solid_m3=bed, mobile_solid_m3=mobile)
    final_level = config.sea_level_m + config.tide_amplitude_m * np.sin(2 * np.pi * end / config.tide_period_s)
    final_ocean, _ = classify_ocean(final, final_level)
    if config.same_cell_wet_dry:
        stranded[~final_ocean] += mobile[~final_ocean]
        mobile[~final_ocean] = 0.
        mobile[final_ocean] += stranded[final_ocean]
        stranded[final_ocean] = 0.
    else:
        _park_and_release(mobile, stranded, final_ocean)
    return replace(state, bed_solid_m3=bed, mobile_solid_m3=mobile, stranded_solid_m3=stranded, time_s=end,
                   exported_solid_m3=exported, water_input_m3=water, consumed_packets=tuple(records))


def save_state(path, state):
    metadata = {k: v for k, v in asdict(state).items() if k not in
                ('base_bed_m', 'bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3', 'porosity', 'valid_mask', 'ocean_seed_mask')}
    np.savez_compressed(path, base_bed_m=state.base_bed_m, bed_solid_m3=state.bed_solid_m3,
                        mobile_solid_m3=state.mobile_solid_m3, stranded_solid_m3=state.stranded_solid_m3, porosity=state.porosity,
                        valid_mask=state.valid_mask, ocean_seed_mask=state.ocean_seed_mask,
                        metadata=json.dumps(metadata, ensure_ascii=False))


def load_state(path):
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data['metadata']))
        state = make_state(**{k: data[k] for k in ('base_bed_m', 'bed_solid_m3', 'mobile_solid_m3',
                           'porosity', 'valid_mask', 'ocean_seed_mask')}, spacing_m=meta['spacing_m'],
                           origin_xz_m=meta['origin_xz_m'], source_identity=meta['source_identity'], time_s=meta['time_s'],
                           stranded_solid_m3=data['stranded_solid_m3'] if 'stranded_solid_m3' in data else 0)
    return replace(state, exported_solid_m3=meta['exported_solid_m3'], unresolved_solid_m3=meta['unresolved_solid_m3'],
                   water_input_m3=meta['water_input_m3'], consumed_packets=tuple(meta['consumed_packets']))
