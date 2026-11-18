"""Bounded static volcanic game landforms in normalized island coordinates.

No ages, eruptions or material state are simulated. Profiles give absolute
height divided by the existing target peak; negative skirts join the seabed.
"""

import hashlib

import numpy as np


VOLCANO_STAGES = ("young", "mature", "caldera", "eroded")


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3 - 2 * value)


def volcano_authority(radius_local):
    """C1 local summit authority; one through .18, zero beyond .30 radius."""
    return _smooth((.30 - np.asarray(radius_local)) / .12)


def volcano_profile(feature, radius_local, angle_rad):
    """Return normalized absolute height for a selected feature's morphology.

    ``radius_local`` is distance/support_radius_m; ``angle_rad`` is measured
    relative to feature.orientation_rad, exactly as in ocean_islands._shape.
    This helper also supports explicit same-location stage comparisons.
    """
    radius, angle = np.broadcast_arrays(np.asarray(radius_local, dtype=float),
                                        np.asarray(angle_rad, dtype=float))
    stage = feature.volcano_stage
    if stage == "young":
        return .98 - (radius / .235)**1.25 - .23 * np.exp(-(radius / .019)**2)
    if stage == "mature":
        along, across = radius*np.cos(angle), radius*np.sin(angle)
        main = 1.12 - (radius / .26)**1.32 - .13*np.exp(-(radius/.024)**2)
        side = .82 - (np.hypot(along-.14, across+.055)/.105)**1.4
        return np.maximum(main, side) + .025*np.sin(7*angle)*_smooth(radius/.05)*np.exp(-(radius/.18)**2)
    if stage == "caldera":
        rim_radius = .105*(1 + .055*np.sin(3*angle))
        rim = .79 - (radius/.29)**1.7
        depression = .66 * (1-_smooth(radius/rim_radius))
        return rim - depression
    if stage == "eroded":
        angular = .14*np.sin(angle+.8) + .035*np.sin(2*angle-1.1)
        # One fixed purpose digest supplies a few local, unequal drainage cuts.
        # Positive irregular gaps avoid coincident paths without equal sectors;
        # independent bends prevent their coastline intersections forming a star.
        digest = hashlib.sha256(f"ocean-island-eroded-grooves-v4:{feature.subseed}".encode()).digest()
        count = 3 + digest[0] % 3
        gaps = .55 + 1.15*np.asarray(list(digest[2:2+count]))/255.
        angles = digest[1]/255.*2*np.pi + 2*np.pi*np.cumsum(gaps)/np.sum(gaps)
        grooves = np.zeros_like(radius)
        for slot, centre in enumerate(angles):
            bend, width, depth = np.asarray(list(digest[7+3*slot:10+3*slot]))/255.
            centre = centre + .34*(bend-.5)*_smooth(radius/.20)
            distance = np.abs(np.arctan2(np.sin(angle-centre), np.cos(angle-centre)))
            cut = (.09+.09*depth)*_smooth(1-distance/(.13+.14*width))
            grooves = np.maximum(grooves, cut)
        grooves *= _smooth(radius/.045)*np.exp(-(radius/.28)**2)
        breach = .22*np.exp(-(np.sin((angle-.5)/2)/.23)**2)*np.exp(-((radius-.07)/.065)**2)*_smooth(radius/.03)
        return .49 - (radius/.23)**1.22 + angular*_smooth(radius/.045) - grooves - breach - .10*np.exp(-(radius/.035)**2)
    raise ValueError("volcano_profile requires a special volcanic stage")
