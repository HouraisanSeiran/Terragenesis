"""Finite, explicit-area SIA flowlines with liquid/rock stores and live bed feedback.

The original short native-account glacier remains unchanged. This implementation
uses its dimensional Glen law on a bounded metric flowline, never its 900 m2
account constant. Inputs are immutable; a failed advance commits nothing.
"""

import itertools
from copy import deepcopy

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.environment_processes import GlacierParameters

ALGORITHM = "world-explicit-area-live-bed-sia-v1"
WATER_DENSITY = 1000.0
GRAVITY = 9.80665
LATENT_J_M3 = 334000000.0
SUBLIMATION_J_M3 = 2834000000.0


def _field(value, n, name, *, signed=False):
    result = np.broadcast_to(np.asarray(value, np.float64), (n,)).copy()
    if not np.isfinite(result).all() or (not signed and np.any(result < 0)):
        raise ValueError(
            "finite " + ("signed " if signed else "nonnegative ") + name + " required"
        )
    return result


def _geometry(geometry):
    bed = np.asarray(geometry["bed_m"], np.float64)
    if bed.ndim != 1 or not 32 <= bed.size <= 512 or not np.isfinite(bed).all():
        raise ValueError("finite 32..512 cell metric flowline required")
    n = bed.size
    dx = float(geometry["spacing_m"])
    width = float(geometry["width_m"])
    if not np.isfinite([dx, width]).all() or min(dx, width) <= 0:
        raise ValueError("explicit positive spacing and width required")
    area = _field(geometry["cell_area_m2"], n, "cell_area_m2")
    if not np.allclose(area, dx * width, rtol=1e-12, atol=1e-9):
        raise ValueError("flowline area must equal actual spacing times width")
    xz = np.asarray(geometry["xz_m"], np.float64)
    if xz.shape != (n, 2) or not np.isfinite(xz).all():
        raise ValueError("explicit absolute [cell,2] xz coordinates required")
    if not np.allclose(
        np.linalg.norm(np.diff(xz, axis=0), axis=1), dx, rtol=1e-8, atol=1e-7
    ):
        raise ValueError(
            "flowline centres must follow the declared uniform metric spacing"
        )
    if np.unique(xz, axis=0).shape[0] != n:
        raise ValueError("flowline cannot own the same support twice")
    metadata = {
        key: geometry[key]
        for key in (
            "source_identity",
            "terrain_identity",
            "support_id",
            "parent_terrain_revision",
        )
    }
    gid = identity(
        {"bed_m": bed, "xz_m": xz, "area_m2": area},
        dict(metadata, spacing_m=dx, width_m=width),
    )
    return bed, area, dx, width, gid


def advance_flowline(geometry, state, forcing, *, time_edges_s, config=None):
    """Advance actual water-equivalent rates on absolute canonical time edges.

    forcing accumulation_mm/ablation_mm/sublimation_mm are finite interval
    totals [interval,cell]. Accumulation is a separately debited snow transfer;
    ablation/sublimation are demands, limited by actual ice. Melt and eroded
    solid remain in output stores until an explicit parent packet consumes them.
    """
    cfg = {
        "time_quantum_s": 3600.0,
        "max_substeps_per_quantum": 4096,
        "max_substeps": 1_000_000,
        "cfl": 0.25,
        "erosion": True,
    }
    cfg.update(config or {})
    quantum = float(cfg["time_quantum_s"])
    if not np.isfinite(quantum) or quantum <= 0 or not 0 < cfg["cfl"] <= 0.25:
        raise ValueError("positive canonical time quantum and CFL <=.25 required")
    for key in ("max_substeps_per_quantum", "max_substeps"):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError("positive integer " + key + " required")
    initial_bed, area, dx, width, gid = _geometry(geometry)
    n = initial_bed.size
    parameters = GlacierParameters(**cfg.get("parameters", {}))
    edges = np.asarray(time_edges_s, np.float64)
    if (
        edges.ndim != 1
        or not 2 <= edges.size <= 513
        or not np.isfinite(edges).all()
        or np.any(np.diff(edges) <= 0)
    ):
        raise ValueError("bounded strictly increasing physical time edges required")
    if not np.allclose(edges / quantum, np.rint(edges / quantum), rtol=0, atol=1e-8):
        raise ValueError(
            "time edges must lie on the declared absolute canonical quantum"
        )
    previous = deepcopy(state or {})
    if previous and (
        previous.get("geometry_identity") != gid
        or previous["physical_time_s"] != edges[0]
    ):
        raise ValueError("glacier geometry identity or physical time differs")
    bed = _field(previous.get("bed_m", initial_bed), n, "bed_m", signed=True)
    thickness = _field(
        previous.get("ice_thickness_m", geometry.get("ice_thickness_m", 0.0)),
        n,
        "ice_thickness_m",
    )
    rock = _field(
        previous.get("remaining_bedrock_m3", geometry["bedrock_erodible_m3"]),
        n,
        "remaining_bedrock_m3",
    )
    liquid = _field(
        previous.get("pending_melt_water_m3", 0.0), n, "pending_melt_water_m3"
    )
    sediment = _field(
        previous.get("pending_sediment_solid_m3", 0.0), n, "pending_sediment_solid_m3"
    )
    if np.any(thickness > parameters.max_thickness_m):
        raise ValueError("initial ice exceeds declared maximum thickness")
    count = edges.size - 1
    demands = {}
    for name in ("accumulation_mm", "ablation_mm", "sublimation_mm"):
        value = np.asarray(forcing.get(name, np.zeros((count, n))), np.float64)
        if (
            value.shape != (count, n)
            or not np.isfinite(value).all()
            or np.any(value < 0)
        ):
            raise ValueError("finite nonnegative [interval,cell] " + name + " required")
        demands[name] = value
    start_ice = thickness * area
    start_rock, start_liquid, start_sediment, start_bed = (
        rock.copy(),
        liquid.copy(),
        sediment.copy(),
        bed.copy(),
    )
    rho = parameters.ice_density_kg_m3
    factor = WATER_DENSITY / rho
    acc = np.zeros((count, n))
    melt = np.zeros_like(acc)
    sublimation = np.zeros_like(acc)
    removed = np.zeros_like(acc)
    transport = np.zeros((count, n + 1))
    snapshots = [thickness.copy()]
    steps = 0
    prefactor = (
        2
        * parameters.creep_parameter_pa_n_s
        / (parameters.glen_exponent + 2)
        * (rho * GRAVITY) ** parameters.glen_exponent
    )
    for interval, (begin, end) in enumerate(itertools.pairwise(edges)):
        rates = {
            key: value[interval] / 1000.0 * area / (end - begin)
            for key, value in demands.items()
        }
        current = begin
        while current < end:
            stop = min(end, (round(current / quantum) + 1) * quantum)
            local_steps = 0
            while current < stop:
                surface = bed + thickness
                slope = np.diff(surface) / dx
                h = 0.5 * (thickness[:-1] + thickness[1:])
                diffusivity = (
                    prefactor
                    * h ** (parameters.glen_exponent + 2)
                    * abs(slope) ** (parameters.glen_exponent - 1)
                )
                limit = (
                    np.inf
                    if not np.any(diffusivity > 0)
                    else cfg["cfl"] * dx * dx / float(diffusivity.max())
                )
                dt = min(stop - current, limit)
                if dt <= np.finfo(float).eps * max(abs(current), 1.0):
                    raise ValueError(
                        "ice stability requires a smaller supported time scale"
                    )
                steps += 1
                local_steps += 1
                if (
                    steps > cfg["max_substeps"]
                    or local_steps > cfg["max_substeps_per_quantum"]
                ):
                    raise ValueError(
                        "glacier fixed work budget exhausted; original state unchanged"
                    )
                # Test the forced surface before committing mass. Accumulation
                # can tighten the old-surface CFL, so refine this same step.
                for _ in range(64):
                    added = rates["accumulation_mm"] * dt
                    volume = thickness * area + added * factor
                    melted = np.minimum(rates["ablation_mm"] * dt, volume / factor)
                    volume -= melted * factor
                    vapor = np.minimum(rates["sublimation_mm"] * dt, volume / factor)
                    volume -= vapor * factor
                    trial_thickness = volume / area
                    slope = np.diff(bed + trial_thickness) / dx
                    h = 0.5 * (trial_thickness[:-1] + trial_thickness[1:])
                    diffusion = (
                        prefactor
                        * h ** (parameters.glen_exponent + 2)
                        * abs(slope) ** (parameters.glen_exponent - 1)
                    )
                    if np.all(diffusion * dt <= cfg["cfl"] * dx * dx * (1 + 1e-12)):
                        break
                    dt *= 0.5
                else:
                    raise ValueError(
                        "mass forcing exceeds bounded glacier CFL refinement"
                    )
                face = np.zeros(n + 1)
                face[1:-1] = -width * diffusion * slope * dt
                outgoing = np.maximum(face[1:], 0.0) + np.maximum(-face[:-1], 0.0)
                scale = np.minimum(
                    1.0, np.divide(volume, outgoing, out=np.ones(n), where=outgoing > 0)
                )
                donor = np.where(face[1:-1] >= 0, scale[:-1], scale[1:])
                face[1:-1] *= donor
                volume += face[:-1] - face[1:]
                if np.any(volume < -1e-8):
                    raise RuntimeError("negative ice after bounded transfer")
                thickness = np.maximum(volume, 0.0) / area
                if np.any(thickness > parameters.max_thickness_m):
                    raise ValueError(
                        "ice exceeds declared maximum thickness; no silent clipping"
                    )
                erosion = np.zeros(n)
                if cfg["erosion"]:
                    work = 0.5 * (abs(face[:-1]) + abs(face[1:]))
                    erosion = np.minimum(
                        rock, parameters.erosion_proxy_coefficient * work
                    )
                    rock -= erosion
                    bed -= erosion / area
                    sediment += erosion
                liquid += melted
                acc[interval] += added
                melt[interval] += melted
                sublimation[interval] += vapor
                removed[interval] += erosion
                transport[interval] += face
                current += dt
            current = stop
        snapshots.append(thickness.copy())
    ice_end = thickness * area
    divergence = transport[:, :-1].sum(axis=0) - transport[:, 1:].sum(axis=0)
    ice_residual = (
        ice_end
        - start_ice
        - factor * (acc - melt - sublimation).sum(axis=0)
        - divergence
    )
    water_residual = (
        start_ice.sum() / factor
        + start_liquid.sum()
        + acc.sum()
        - ice_end.sum() / factor
        - liquid.sum()
        - sublimation.sum()
    )
    solid_residual = (
        start_rock.sum() + start_sediment.sum() - rock.sum() - sediment.sum()
    )
    state_out = {
        "geometry_identity": gid,
        "physical_time_s": float(edges[-1]),
        "bed_m": bed,
        "ice_thickness_m": thickness,
        "remaining_bedrock_m3": rock,
        "pending_melt_water_m3": liquid,
        "pending_sediment_solid_m3": sediment,
    }
    arrays = {
        "ice_thickness_m": np.asarray(snapshots),
        "ice_surface_m": bed + thickness,
        "bed_m": bed,
        "bed_change_m": bed - start_bed,
        "cell_area_m2": area,
        "ice_initial_volume_m3": start_ice,
        "ice_final_volume_m3": ice_end,
        "initial_bedrock_m3": start_rock,
        "final_bedrock_m3": rock,
        "initial_liquid_m3": start_liquid,
        "final_liquid_m3": liquid,
        "initial_sediment_m3": start_sediment,
        "final_sediment_m3": sediment,
        "accumulation_water_m3": acc,
        "melt_water_m3": melt,
        "sublimation_water_m3": sublimation,
        "eroded_rock_m3": removed,
        "face_ice_transfer_m3": transport,
        "cell_ice_residual_m3": ice_residual,
    }
    ledger = {
        "water_residual_m3": float(water_residual),
        "solid_residual_m3": float(solid_residual),
        "ice_max_cell_residual_m3": float(abs(ice_residual).max()),
        "accumulation_water_m3": float(acc.sum()),
        "melt_water_m3": float(melt.sum()),
        "sublimation_water_m3": float(sublimation.sum()),
        "rock_removed_m3": float(removed.sum()),
        "latent_melt_demand_j": float(melt.sum() * LATENT_J_M3),
        "latent_sublimation_demand_j": float(sublimation.sum() * SUBLIMATION_J_M3),
    }
    return {
        "state": state_out,
        "arrays": arrays,
        "ledger": ledger,
        "metadata": {
            "algorithm": ALGORITHM,
            "geometry_identity": gid,
            "parameters": parameters.identity(),
            "time_quantum_s": quantum,
            "substeps": steps,
            "physical_time_s": float(edges[-1]),
            "erosion": "finite transport-related proxy using actual donor-limited ice transfer; live bed feedback",
            "ends": "closed ice faces; liquid and sediment retained until parent packet handoff",
            "energy": "degree-day/declared ablation demand; latent demand recorded, not a solved ice enthalpy model",
            "limits": [
                "deformation only; no sliding, calving, ice thermodynamics or lateral branching"
            ],
        },
    }
