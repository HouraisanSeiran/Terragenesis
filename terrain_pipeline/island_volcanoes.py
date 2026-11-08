"""Bounded volcanic edifices, separate from frozen v4 radial profiles.

Static game geometry in normalized island coordinates, with no process state.
"""

import hashlib

import numpy as np


VOLCANO_STAGES = ("young", "mature", "caldera", "eroded")


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3 - 2 * value)


def volcano_authority(radius_local):
    """Own edifice and apron, fading C1 into the existing submarine base."""
    return _smooth((.55 - np.asarray(radius_local)) / .19)


def _geometry(feature):
    """Fixed purpose-separated parameters, independent of samples and stage."""
    digest = hashlib.sha256(f"ocean-island-volcanic-edifices-v5:{feature.subseed}".encode()).digest()
    return np.frombuffer(digest, dtype=np.uint8).astype(float)/255.


def _cone(distance, radius):
    return np.maximum(0., 1 - (distance/radius)**1.15)**1.45


def _cell_hash(ix, iz, seed, purpose):
    salt = int.from_bytes(hashlib.sha256(f"volcanic-lava-v5:{seed}:{purpose}".encode()).digest()[:8], "little")
    with np.errstate(over="ignore"):
        value = np.asarray(ix, dtype=np.int64).astype(np.uint64)*np.uint64(0x9E3779B185EBCA87)
        value = value ^ (np.asarray(iz, dtype=np.int64).astype(np.uint64)*np.uint64(0xC2B2AE3D27D4EB4F)) ^ np.uint64(salt)
        value ^= value >> np.uint64(30)
        value *= np.uint64(0xBF58476D1CE4E5B9)
        value ^= value >> np.uint64(27)
        value *= np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    return (value >> np.uint64(11)).astype(float)/2**53


def _lattice_value(x, z, seed, purpose):
    ix, iz = np.floor(x).astype(np.int64), np.floor(z).astype(np.int64)
    fx, fz = x-ix, z-iz
    fx = fx**3*(fx*(fx*6-15)+10)
    fz = fz**3*(fz*(fz*6-15)+10)
    return ((1-fz)*((1-fx)*_cell_hash(ix, iz, seed, purpose)+fx*_cell_hash(ix+1, iz, seed, purpose))
            + fz*((1-fx)*_cell_hash(ix, iz+1, seed, purpose)+fx*_cell_hash(ix+1, iz+1, seed, purpose)))*2-1


def _lava_cells(x_m, z_m, spacing_m, seed):
    """C2 compact soft Voronoi value field with a fixed 3x3 site stencil.

    Sites stay .26..74 inside their cells. The 1.25-cell compact radius is
    smaller than the 1.26 minimum distance to every omitted site, so a stencil
    replacement never introduces a nonzero weight at either side of a seam.
    """
    x, z = np.broadcast_arrays(np.asarray(x_m, float)/spacing_m, np.asarray(z_m, float)/spacing_m)
    warped_x = x + .48*_lattice_value(x/1.7, z/1.7, seed, "warp-x")
    warped_z = z + .48*_lattice_value(x/1.7, z/1.7, seed, "warp-z")
    ix, iz = np.floor(warped_x).astype(np.int64), np.floor(warped_z).astype(np.int64)
    weighted, total = np.zeros(x.shape), np.zeros(x.shape)
    for dz in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sx, sz = ix+dx, iz+dz
            site_x = sx+.26+.48*_cell_hash(sx, sz, seed, "site-x")
            site_z = sz+.26+.48*_cell_hash(sx, sz, seed, "site-z")
            distance2 = (warped_x-site_x)**2+(warped_z-site_z)**2
            weight = np.maximum(0., 1-distance2/1.25**2)**4*np.exp(-distance2/.19)
            weighted += weight*(2*_cell_hash(sx, sz, seed, "thickness")-1)
            total += weight
    return weighted/total


def volcano_profile(feature, radius_local, angle_rad, *, lava_strength=1.):
    """Edifice height with bounded domain-warped lava accumulation geometry.

    Voronoi cells represent unequal overlapping accumulation thickness, never
    F2-F1 cracks. Coarse and medium flow units are distinct from generic noise.
    Zero strength is the exact pre-lava v5 profile. Summit interiors and the
    near-sea/submarine surface are masked; the eroded remnant is less affected.
    """
    profile = _edifice_profile(feature, radius_local, angle_rad)
    if lava_strength == 0:
        return profile
    radius, angle = np.broadcast_arrays(np.asarray(radius_local, float), np.asarray(angle_rad, float))
    x_m = radius*np.cos(angle)*feature.support_radius_m
    z_m = radius*np.sin(angle)*feature.support_radius_m
    # Coarse nonradial deformation changes the cone/rim outline itself, rather
    # than putting tiny stones on an otherwise exact surface of revolution.
    broad = _lava_cells(x_m, z_m, 6200., feature.subseed+2)
    broad_z = _lava_cells(x_m, z_m, 6200., feature.subseed+3)
    deformation_mask = _smooth((.42-radius)/.10)*_smooth(profile/.10)
    warp_m = lava_strength*deformation_mask*feature.support_radius_m*.008
    warped_x, warped_z = x_m+warp_m*broad, z_m+warp_m*broad_z
    warped_radius = np.hypot(warped_x, warped_z)/feature.support_radius_m
    warped_angle = np.arctan2(warped_z, warped_x)
    apron_expansion = .14*lava_strength*(.5+.5*broad)
    expanded = _edifice_profile(feature, radius, angle, apron_expansion=apron_expansion)
    deformed = _edifice_profile(feature, warped_radius, warped_angle, apron_expansion=apron_expansion)
    profile = expanded+deformation_mask*(deformed-expanded)
    coarse = .65*broad+.35*_lava_cells(x_m, z_m, 2100., feature.subseed)
    medium = _lava_cells(x_m, z_m, 720., feature.subseed+1)
    values = _geometry(feature)
    direction = 2*np.pi*values[0]
    lava_x = x_m/feature.support_radius_m*np.cos(direction)+z_m/feature.support_radius_m*np.sin(direction)
    lava_z = -x_m/feature.support_radius_m*np.sin(direction)+z_m/feature.support_radius_m*np.cos(direction)
    cone_x, cone_z = lava_x-.035*(values[4]-.5), lava_z-.035*(values[5]-.5)
    summit_distance = np.hypot(cone_x, cone_z)
    inner = {"young": .008, "mature": .065, "caldera": .030, "eroded": .065}[feature.volcano_stage]
    if feature.volcano_stage == "mature":
        summit_distance = np.minimum(summit_distance, np.hypot(cone_x-.023, cone_z+.012)+.010)
    mask = _smooth((summit_distance-inner)/.025)*_smooth((.48-radius)/.12)*_smooth(profile/.30)
    upper_weight = {"young": 1., "mature": 1., "caldera": .85, "eroded": .35}[feature.volcano_stage]
    stage_weight = 1-(1-upper_weight)*_smooth((.20-radius)/.08)
    delta = lava_strength*stage_weight*mask*(.090*coarse+.026*medium)
    return profile+delta


def _edifice_profile(feature, radius_local, angle_rad, *, apron_expansion=0.):
    """Absolute height / target peak, including a submerged joining skirt.

    Angles are relative to feature.orientation_rad. Upper cones are eccentric
    relative to the low lava apron; spatial support stays in the same island.
    Erosional changes vanish before the apron, so they cannot cut seafloor.
    """
    radius, angle = np.broadcast_arrays(np.asarray(radius_local, dtype=float),
                                        np.asarray(angle_rad, dtype=float))
    values = _geometry(feature)
    along, across = radius*np.cos(angle), radius*np.sin(angle)
    direction = 2*np.pi*values[0]
    lava_x = along*np.cos(direction) + across*np.sin(direction)
    lava_z = -along*np.sin(direction) + across*np.cos(direction)
    # A broad low lava apron with an elongated tongue and an offset second lobe.
    stretch = 1.02 + .20*values[1]
    apron_distance = np.hypot((lava_x-.028)/stretch, lava_z/(.90+.12*values[2]))/(1+apron_expansion)
    apron = .22*(1-_smooth((apron_distance-.055)/.29))
    tongue_distance = np.hypot((lava_x-.12)/(.25+.035*values[3]), (lava_z+.025)/.15)/(1+.6*apron_expansion)
    apron += .055*np.maximum(0., 1-tongue_distance**2)**2
    apron -= 2.4*_smooth((apron_distance-.30)/.34)

    centre_x = .035*(values[4]-.5)
    centre_z = .035*(values[5]-.5)
    cone_x, cone_z = lava_x-centre_x, lava_z-centre_z
    distance = np.hypot(cone_x, cone_z/(.90+.12*values[6]))
    cone_radius = .083+.014*values[7]
    stage = feature.volcano_stage
    if stage == "young":
        upper = .88*_cone(distance, cone_radius)
        crater_radius = .012+.003*values[8]
        upper -= .32*(1-_smooth(distance/crater_radius))
        upper += .055*np.exp(-((distance-crater_radius)/.0035)**2)
        return apron + upper
    if stage == "mature":
        # An older shoulder encloses an offset younger vent with a smaller pit.
        shoulder = .91*_cone(distance, cone_radius*1.50)
        shoulder -= .31*(1-_smooth((distance-.018)/.023))
        vent_distance = np.hypot(cone_x-.023, cone_z+.012)
        active = .96*_cone(vent_distance, cone_radius*.78)
        active -= .30*(1-_smooth(vent_distance/.011))
        return apron + np.maximum(shoulder, active)
    if stage == "caldera":
        # Broad basin, steep inner wall and a continuous raised annular rim.
        rim_radius = .052+.007*values[9]
        rim_distance = np.hypot(cone_x/1.08, cone_z/.93)
        outer = .66*(1-_smooth((rim_distance-rim_radius)/.070))
        basin = .53*(1-_smooth((rim_distance-rim_radius*.70)/(rim_radius*.30)))
        rim = .075*np.exp(-((rim_distance-rim_radius)/.007)**2)
        return apron + outer - basin + rim
    if stage == "eroded":
        # One broad amphitheatre opening to the low slope. Cartesian distances
        # and the outward widening mouth avoid radial slots or enclosed pits.
        upper = .67*_cone(distance, cone_radius*1.22)
        collapse_direction = 2*np.pi*values[10]
        outward = cone_x*np.cos(collapse_direction)+cone_z*np.sin(collapse_direction)
        lateral = -cone_x*np.sin(collapse_direction)+cone_z*np.cos(collapse_direction)
        bend = .012*np.sin(np.clip(outward/.10, -1, 1)*2)
        width = .027+.27*np.maximum(0., outward)
        mouth = np.exp(-((lateral-bend)/width)**4)
        head = _smooth((outward+.022)/.038)
        collapse = .62*head*mouth*_smooth((.135-distance)/.045)
        upper *= 1-collapse
        remnant = .075*np.exp(-((cone_x+.032)/.020)**2-((cone_z-.022)/.027)**2)
        return apron + upper + remnant
    raise ValueError("volcano_profile requires a special volcanic stage")
