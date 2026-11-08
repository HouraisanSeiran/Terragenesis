"""Closed, unforced, frictionless research executor for independent nine moments."""

import numpy as np

from terrain_pipeline.surface_moment_hydraulics import (
    MODEL, limit_realizable_moments, moments_from_profile, nine_moment_rhs,
)


def advance_nine_moments(positional_bed, initial_eta, initial_velocity, *, spacing,
                         duration_s, max_dt_s=.01, gravity=9.81, max_substeps=1000):
    bed = np.asarray(positional_bed, np.float64)
    if (bed.ndim != 4 or bed.shape[2] != bed.shape[3] or not np.isfinite(bed).all() or
            spacing <= 0 or duration_s <= 0 or max_dt_s <= 0):
        raise ValueError("finite bed and positive execution dimensions required")
    rows, columns, factor, _ = bed.shape
    count = rows*columns
    flat_bed = bed.reshape(count, factor, factor)
    eta = np.asarray(initial_eta, np.float64).copy()
    velocity = np.asarray(initial_velocity, np.float64).copy()
    if eta.shape != (count, 3) or velocity.shape != (count, 3, 2):
        raise ValueError("initial affine profile shape invalid")
    state = np.asarray([moments_from_profile(eta[cell], velocity[cell], flat_bed[cell]) for cell in range(count)])
    initial = state.copy()
    initial_volume = float(state[:, 0, 0].sum()*spacing**2)
    time, steps, limited, refused = 0., 0, 0, 0
    minimum_factor = 1.
    packets = []

    def realize(candidate, guesses):
        nonlocal limited, minimum_factor
        result, next_eta, next_velocity = [], [], []
        for cell in range(count):
            limited_state, profile_eta, profile_velocity, factor = limit_realizable_moments(candidate[cell], flat_bed[cell], guesses[cell])
            result.append(limited_state)
            next_eta.append(profile_eta)
            next_velocity.append(profile_velocity)
            limited += factor < 1.
            minimum_factor = min(minimum_factor, factor)
        return np.asarray(result), np.asarray(next_eta), np.asarray(next_velocity)

    while time < duration_s-1e-14:
        if steps >= max_substeps:
            raise RuntimeError("nine-moment reference substep budget exceeded")
        # Affine corner extrema bound all face quadrature values, independently
        # of wet clipping or canonical tile heights.
        maximum_h = np.maximum(eta[:, 0]+.5*(abs(eta[:, 1])+abs(eta[:, 2]))-flat_bed.min(axis=(1, 2)), 0.)
        velocity_bound = abs(velocity[:, 0]).sum(axis=1)+.5*abs(velocity[:, 1:]).sum(axis=(1, 2))
        speed = float((velocity_bound+2*np.sqrt(gravity*maximum_h)).max(initial=0))
        dt = min(max_dt_s, .15*spacing/max(speed, 1e-12), duration_s-time)
        rhs1, witness1 = nine_moment_rhs(state, eta, velocity, bed, spacing=spacing, gravity=gravity)
        for _ in range(30):
            candidate = state+dt*rhs1
            if np.any(candidate[:, 0, 0] < 0):
                dt *= .5
                refused += 1
                continue
            predictor, eta_trial, velocity_trial = realize(candidate, eta)
            rhs2, witness2 = nine_moment_rhs(predictor, eta_trial, velocity_trial, bed, spacing=spacing, gravity=gravity)
            updated = .5*state+.5*(predictor+dt*rhs2)
            if np.any(updated[:, 0, 0] < 0):
                dt *= .5
                refused += 1
                continue
            next_state, next_eta, next_velocity = realize(updated, eta_trial)
            break
        else:
            raise RuntimeError("nine-moment positivity time-step refusal")
        packets.append(dict(time_start_s=time, dt_s=dt, state_before=state.copy(), state_predictor=predictor.copy(),
            state_after=next_state.copy(), rhs1=rhs1, rhs2=rhs2,
            predictor_moment_limiter_change=predictor-candidate,
            final_moment_limiter_change=next_state-updated,
            rk1_geometric_source=witness1["geometric_source"], rk2_geometric_source=witness2["geometric_source"]))
        state, eta, velocity = next_state, next_eta, next_velocity
        time += dt
        steps += 1
    final_volume = float(state[:, 0, 0].sum()*spacing**2)
    return dict(arrays=dict(initial_moments=initial, final_moments=state, final_stage_coefficients=eta,
        final_velocity_coefficients=velocity), packets=packets,
        metadata=dict(model=MODEL, duration_s=duration_s, substeps=steps, limited_profile_count=limited,
            minimum_profile_limiter_factor=minimum_factor, rejected_dt_count=refused,
            initial_volume_m3=initial_volume, final_volume_m3=final_volume,
            volume_residual_m3=final_volume-initial_volume,
            scope="closed unforced frictionless nine independent moment reference; not Stage 1 accepted"))
