"""Statistical tidal windows for finite-source distributary formation.

Each equal-weight phase represents a fraction of equivalent geological time;
physical event time is unchanged. This is not a tidal hydrodynamic model.
"""
from dataclasses import asdict, replace
import json
import numpy as np
from . import coastal_delta_branching as branching
from .coastal_marine_longterm import LongtermConfig, advance


def _park_same_cell(mobile, stranded, wet):
    stranded[~wet] += mobile[~wet]
    mobile[~wet] = 0.
    mobile[wet] += stranded[wet]
    stranded[wet] = 0.


def advance_years(state, progress, years, forcing=LongtermConfig(), *, amplitude_m=1.,
                  phase_count=8, channel_min_depth_m=.35, step_years=.25):
    """Advance whole statistical cycles; identity is fixed across continuations."""
    if (not np.isfinite([years, amplitude_m, channel_min_depth_m, step_years]).all()
            or years <= 0 or amplitude_m < 0 or channel_min_depth_m <= 0 or step_years <= 0
            or not isinstance(phase_count, int) or phase_count < 2):
        raise ValueError('invalid tidal formation parameters')
    branching._validate(state, progress)
    if 'forcing' in progress and progress['forcing'] != asdict(forcing):
        raise ValueError('formation forcing mismatch')
    if 'channel_min_depth_m' in progress and progress['channel_min_depth_m'] != channel_min_depth_m:
        raise ValueError('formation channel depth mismatch')
    levels = [float(amplitude_m * np.sin(2*np.pi*(i+.5)/phase_count)) for i in range(phase_count)]
    identity = {'algorithm': 'tidal-plain-v1', 'amplitude_m': amplitude_m,
                'phase_offsets_m': levels, 'weights': [1./phase_count]*phase_count,
                'step_years': step_years, 'forcing': asdict(forcing),
                'channel_min_depth_m': channel_min_depth_m}
    if 'tidal_plain' in progress and progress['tidal_plain'] != identity:
        raise ValueError('tidal formation parameters mismatch')
    p = json.loads(json.dumps(progress))
    p['tidal_plain'] = identity
    p['forcing'] = asdict(forcing)
    p['channel_min_depth_m'] = channel_min_depth_m
    physical_time = state.time_s
    allowed = state.valid_mask & (state.base_bed_m < forcing.sea_level_m)
    elapsed = 0.
    while elapsed < years - 1e-12:
        step = min(step_years, years-elapsed)
        seconds = step*365.25*86400/phase_count
        active = branching._update_activity(state, p, forcing.sea_level_m, 'tidal-formation')
        source = np.zeros(state.bed_m.shape)
        for route, share in zip(p['routes'], p['actual_shares']):
            if share:
                source[tuple(route[-1])] += p['solid_rate_m3_s']*share
        if not any(active):
            p['formation_undelivered_solid_m3'] = p.get('formation_undelivered_solid_m3', 0.) + p['solid_rate_m3_s']*seconds*phase_count
            p['formation_undelivered_water_m3'] = p.get('formation_undelivered_water_m3', 0.) + p['discharge_m3_s']*seconds*phase_count
        for offset in levels:
            level = forcing.sea_level_m + offset
            ceiling = np.full(state.bed_m.shape, level)
            for route, wet in zip(p['routes'], active):
                if wet:
                    for cell in route:
                        cell = tuple(cell)
                        ceiling[cell] = max(forcing.sea_level_m-channel_min_depth_m, state.bed_m[cell])
            cfg = replace(forcing, sea_level_m=level, source_relocation_cells=0)
            state, _ = advance(state, seconds, cfg, source_rate_m3_s=source,
                               bed_ceiling_m=ceiling, allowed_mask=allowed,
                               park_and_release=_park_same_cell)
            state = branching._clean_roundoff(replace(state, time_s=physical_time))
        p['supply_solid_m3'] += p['solid_rate_m3_s']*seconds*phase_count
        p['years'] += step
        elapsed += step
        branching._update_activity(state, p, forcing.sea_level_m, 'tidal-formation')
        state = branching._record(state, p)
        try:
            state, p, _ = branching.update_shoreline_mouths(state, p, sea_level_m=forcing.sea_level_m,
                                                            channel_depth_m=channel_min_depth_m)
        except ValueError as exc:
            if str(exc) != 'no finite deposited-sediment mouth route to exterior ocean':
                raise
            # A blocked mouth remains closed and activity is recalculated.
            branching._update_activity(state, p, forcing.sea_level_m, 'tidal-formation')
            state = branching._record(state, p)
    return state, p
