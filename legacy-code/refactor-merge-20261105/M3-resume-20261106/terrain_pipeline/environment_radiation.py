"""Declared fictional sun, terrain illumination and shortwave energy accounting."""
import numpy as np
from terrain_pipeline.environment_process_contract import _field, _grid, _parameters

ALGORITHM = "environment-fictional-sun-shortwave-v1"


def initialize(context):
    height, _, _ = _grid(context, 1.)
    return {"absorbed_energy_j_m2": np.zeros(height.shape)}


def step(state, forcing, context, dt_s, parameters=None):
    """Integrate midpoint shortwave; X east and Z north are fictional axes.

    Latitude/longitude are caller-declared fictional degrees, never inferred from
    TD coordinates. Large time intervals need caller substeps for diurnal accuracy.
    """
    height, spacing, active = _grid(context, dt_s)
    p = _parameters(parameters, {"day_seconds": 86400., "year_days": 365.,
        "solar_constant_w_m2": 1000., "atmospheric_transmission": .7,
        "evaporation_energy_fraction": .3})
    latitude = float(forcing.get("latitude_deg", 35.))
    longitude = float(forcing.get("longitude_deg", 0.))
    time = float(forcing.get("time_s", 0.)) + dt_s / 2
    if not np.isfinite([latitude, longitude, time]).all() or abs(latitude) > 90 or abs(longitude) > 180:
        raise ValueError("finite declared fictional latitude/longitude/time required")
    if p["atmospheric_transmission"] > 1 or p["evaporation_energy_fraction"] > 1:
        raise ValueError("energy fractions must not exceed one")
    declination = np.deg2rad(23.44) * np.sin(2 * np.pi * time / (p["day_seconds"] * p["year_days"]))
    hour = 2 * np.pi * (time / p["day_seconds"] % 1 - .5) + np.deg2rad(longitude)
    lat = np.deg2rad(latitude)
    sun = np.array([-np.cos(declination) * np.sin(hour),
        np.sin(lat) * np.sin(declination) + np.cos(lat) * np.cos(declination) * np.cos(hour),
        np.cos(lat) * np.sin(declination) - np.sin(lat) * np.cos(declination) * np.cos(hour)])
    dz = np.gradient(height, spacing, axis=0) if height.shape[0] > 1 else np.zeros_like(height)
    dx = np.gradient(height, spacing, axis=1) if height.shape[1] > 1 else np.zeros_like(height)
    cosine = np.maximum(0., (-dx * sun[0] + sun[1] - dz * sun[2]) / np.sqrt(1 + dx * dx + dz * dz))
    shadow = np.zeros(height.shape, bool)
    if sun[1] > 0:
        horizontal = np.hypot(sun[0], sun[2])
        if horizontal > 1e-10:
            rows, cols = np.indices(height.shape)
            for distance in range(1, int(np.ceil(np.hypot(*height.shape))) + 1):
                rr = np.rint(rows + distance * sun[2] / horizontal).astype(int)
                cc = np.rint(cols + distance * sun[0] / horizontal).astype(int)
                inside = (rr >= 0) & (cc >= 0) & (rr < height.shape[0]) & (cc < height.shape[1])
                r, c = np.clip(rr, 0, height.shape[0] - 1), np.clip(cc, 0, height.shape[1] - 1)
                shadow |= inside & (height[r, c] > height + distance * spacing * sun[1] / horizontal + 1e-9)
    else:
        shadow[:] = True
    albedo = _field(forcing.get("albedo", .2), height.shape, "albedo", 0., 1.)
    incident = np.where(active & ~shadow, p["solar_constant_w_m2"] * p["atmospheric_transmission"] * cosine, 0.)
    absorbed = incident * (1 - albedo)
    previous = _field(state["absorbed_energy_j_m2"], height.shape, "absorbed energy", 0.)
    evaporation_energy = absorbed * p["evaporation_energy_fraction"]
    return {"state": {"absorbed_energy_j_m2": previous + absorbed * dt_s},
        "fluxes": {"absorbed_shortwave_w_m2": absorbed,
            "net_ground_heat_w_m2": absorbed - evaporation_energy,
            "potential_evaporation_m": evaporation_energy * dt_s / 2.45e9,
            "terrain_shadow_mask": shadow, "sun_direction_xyz": sun},
        "ledger": {"incident_j": float(incident.sum() * spacing ** 2 * dt_s),
            "reflected_j": float((incident * albedo).sum() * spacing ** 2 * dt_s),
            "absorbed_j": float(absorbed.sum() * spacing ** 2 * dt_s)},
        "metadata": {"algorithm": ALGORITHM, "parameters": p, "latitude_deg": latitude,
            "longitude_deg": longitude, "sun_axes": "fictional X east Y up Z north",
            "source": "declared fictional solar calendar; uncalibrated",
            "units": "state J/m2; flux W/m2; potential evaporation water metres per step; ledger J; dt seconds",
            "limitation": "shortwave only; no longwave/cloud diffusion; shadow beyond window unknown",
            "energy_partition": "ground plus potential ET; actual ET must cap by water inventory"}}
