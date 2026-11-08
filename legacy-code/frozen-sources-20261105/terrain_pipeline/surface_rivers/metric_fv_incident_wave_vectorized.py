"""Independent D4 Airy helper; no production caller is changed.

Rays advance in the original order, vectorized across parallel rays only.
Dispersion and each ray's flux recurrence retain the frozen implementation's
operations. NumPy vector/scalar arithmetic can differ by floating-point ulps.
"""
import numpy as np


def incident_wave_field(depth, geometry, config):
    """Return the frozen wave fields with parallel-ray NumPy operations."""
    config.validate()
    depth = np.asarray(depth, float)
    omega, gravity = 2. * np.pi / config.wave_period_s, 9.81
    wet = depth > config.dry_depth_m
    h = np.maximum(depth, config.dry_depth_m)
    lo = np.zeros_like(h)
    hi = omega ** 2 / gravity + omega / np.sqrt(gravity * h) + 1.
    for _ in range(50):
        middle = .5 * (lo + hi)
        lower = gravity * middle * np.tanh(middle * h) < omega ** 2
        lo = np.where(lower, middle, lo)
        hi = np.where(lower, hi, middle)
    wave_number = .5 * (lo + hi)
    kh = wave_number * h
    group_speed = .5 * omega / wave_number * (1. + 2. * kh / np.sinh(np.minimum(2. * kh, 700.)))
    a = geometry["arrays"]
    open_cells = np.zeros(depth.size, bool)
    open_cells[a["boundary_cell"][a["boundary_kind"] == 2]] = True
    open_cells = open_cells.reshape(depth.shape)
    height = np.zeros_like(depth)
    dx, dz = config.wave_direction_xz

    # Views put propagation on axis 0, retaining one flux per independent ray.
    def along_rays(field):
        view = field.T if dx else field
        return view if (dx or dz) > 0 else view[::-1]

    ray_height = along_rays(height)
    ray_h = along_rays(h)
    ray_speed = along_rays(group_speed)
    ray_wet = along_rays(wet)
    active = along_rays(open_cells)[0] & ray_wet[0]
    flux = config.wave_height_m ** 2 * ray_speed[0]
    for index in range(ray_height.shape[0]):
        active &= ray_wet[index]
        if not active.any():
            break
        speed = ray_speed[index, active]
        value = np.minimum(np.sqrt(flux[active] / speed), config.breaking_height_depth_ratio * ray_h[index, active])
        ray_height[index, active] = value
        flux[active] = value ** 2 * speed
    orbital = np.pi * height / config.wave_period_s / np.sinh(np.minimum(kh, 700.))
    orbital[~wet] = 0.
    return {"wave_height_m": height, "wave_orbital_velocity_m_s": orbital,
        "wave_number_m_inverse": wave_number, "wave_group_speed_m_s": group_speed}
