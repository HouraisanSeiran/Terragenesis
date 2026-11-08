"""Terrain-constrained regional alluvial initialization, experimental v2."""
import numpy as np
from scipy.ndimage import binary_propagation, distance_transform_edt, gaussian_filter, label
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step
from terrain_pipeline.channel_geometry import derived_seed


def construct(bed, ocean, valid, inlet, spacing, solid_m3, porosity=.4):
    """Fill a connected shallow shelf with a finite, tapered alluvial cover.

    Geometric initialization: not a physical time integration.
    """
    bed=np.asarray(bed,float); ocean=np.asarray(ocean,bool); valid=np.asarray(valid,bool)
    if bed.shape!=ocean.shape or bed.shape!=valid.shape or not np.isfinite(bed).all():
        raise ValueError('invalid terrain')
    rr,cc=np.indices(bed.shape); radius=np.hypot(rr-inlet[0],cc-inlet[1])*spacing
    # Real shelf, mountains and ocean edge remain immutable.
    shelf=ocean & valid & (bed<0) & (bed>-18) & (radius<25000)
    shelf[[0,-1],:]=False; shelf[:,[0,-1]]=False
    labels,n=label(shelf,structure=np.ones((3,3),bool))
    if not n: raise ValueError('no shallow coastal shelf')
    cells=np.argwhere(shelf); nearest=tuple(cells[np.argmin(np.sum((cells-inlet)**2,axis=1))])
    shelf=labels==labels[nearest]
    # Taper only sea-facing edge, preserving a solid coast tie; no independent noise.
    shore=distance_transform_edt(ocean)*spacing
    edge=distance_transform_edt(shelf)*spacing
    taper=np.where(shore<=600,1.,np.clip(edge/300.,0.,1.))
    target=.45+np.clip((2500.-shore)/2500.,0.,1.)*.5
    # Filter the cover, not source TD; clipped against eligible shelf and floor.
    raw=np.maximum(target-bed,0.)*taper*shelf
    smoothed=raw
    desired=np.minimum(smoothed,np.maximum(target-bed,0.))*shelf
    required=float(desired.sum()*spacing**2*(1.-porosity))
    scale=min(1.,solid_m3/required) if required else 0.
    deposit=desired*scale
    result=bed+deposit
    # One conservative low-intensity pass limited by original bed.
    kinds=np.where(shelf,0,-2)
    result=conservative_diffusion_step(result,np.where(shelf,.1,0.),kinds,bed,.01,spacing)
    retained=float((result-bed).sum()*spacing**2*(1.-porosity))
    return dict(bed=result,shelf=shelf,deposit=result-bed,required_solid_m3=required,retained_solid_m3=retained,
                unplaced_solid_m3=solid_m3-retained, inlet=nearest, seed=derived_seed(20261020,'large-delta/v2'))
