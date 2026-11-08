"""Entry point for a single irregular trunk and subsequent candidate refresh."""
from .coastal_delta_routes import prepare_routes
from .coastal_delta_evolution import initialize
from .coastal_delta_avulsion import extend_mouths, propose_candidates
from .coastal_delta_branching import mouth_exterior_faces, _record, _update_activity


def start_irregular(state, source_ocean, fine, fine_metadata, *, hydraulic_config,
                    q_m3_s=150., solid_rate_m3_s=.08, sea_level_m=0.,
                    roughness=.035, world_seed=20260903, mouth_radius_m=4000.,
                    mouth_max_cut_m=.5, input_id='integrated-formation'):
    """Prepare one trunk and ensure its mouth reaches the exterior ocean.

    The supplied hydraulic boundary is never raised; an infeasible trunk raises
    ValueError. Mouth extension can move finite existing sediment to mobile stock.
    """
    state, routes, metadata = prepare_routes(state, source_ocean, fine, fine_metadata,
        q_m3_s=q_m3_s, sea_level_m=sea_level_m, roughness=roughness,
        irregular=True, world_seed=world_seed)
    state, progress = initialize(state, routes, metadata, input_id=input_id,
        discharge_m3_s=q_m3_s, solid_rate_m3_s=solid_rate_m3_s)
    _update_activity(state, progress, sea_level_m, input_id, hydraulic_config)
    solution = progress['river_hydraulics']
    report = {'extended': False, 'trigger': 'already_open'}
    if not all(mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)) or not any(q > 0 for q in solution['route_q_m3_s']):
        state, progress, report = extend_mouths(state, progress, hydraulic_config=hydraulic_config,
            sea_level_m=sea_level_m, radius_m=mouth_radius_m, max_cut_m=mouth_max_cut_m)
        _update_activity(state, progress, sea_level_m, input_id, hydraulic_config)
        solution = progress['river_hydraulics']
    if not all(mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)) or not any(q > 0 for q in solution['route_q_m3_s']):
        raise ValueError('single trunk cannot reach exterior ocean with positive discharge')
    state = _record(state, progress)
    return state, progress, {'preparation': metadata, 'mouth': report, 'hydraulics': solution}
