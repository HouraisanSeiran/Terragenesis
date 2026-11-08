"""Explicit local geological shelf scenario over a pinned TD regional source.

The transform changes only known ocean bathymetry. It is not a sediment ledger.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy import ndimage

from terrain_pipeline.large_delta_suite import load_source


@dataclass(frozen=True)
class ShelfScenario:
    apex_xz_m: tuple = (-140160., -27480.)
    direction_xz: tuple = (-4200., 8400.)
    ocean_seed_zx: tuple = (160, 175)
    core_forward_start_m: float = 0.
    taper_backward_length_m: float = 6000.
    core_forward_end_m: float = 112000.
    taper_forward_end_m: float = 130000.
    lateral_outer_max_m: float = 50000.
    lateral_opening: float = .6
    lateral_start_m: float = 16000.
    lateral_taper_m: float = 12000.
    target_depth_m: float = 18.
    relief_amplitude_m: float = 6.
    relief_scale_m: float = 200.
    relief_smoothing_m: float = 3000.
    source_edge_taper_m: float = 12000.


def _smoothstep(value):
    x = np.clip(value, 0., 1.)
    return x*x*(3.-2.*x)


def shelf_arrays(bed_m, valid, ocean, unknown_wet, origin_xz_m, spacing_m, scenario=ShelfScenario()):
    """Return transformed bed, weight and local coordinates; no source mutation.

    Target depth is 18 +/- 6 m according to bounded TD local relief. Cubic
    smoothsteps taper the blend to zero at the seaward and lateral boundaries.
    """
    bed = np.asarray(bed_m)
    valid, ocean, unknown = (np.asarray(v) for v in (valid, ocean, unknown_wet))
    if bed.ndim != 2 or any(a.shape != bed.shape or a.dtype.kind != 'b' for a in (valid,ocean,unknown)):
        raise ValueError('matching 2D terrain and boolean masks required')
    if not np.isfinite(bed).all() or not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError('finite terrain and positive spacing required')
    p = asdict(scenario)
    numeric = np.array([*p['apex_xz_m'], *p['direction_xz'], p['core_forward_start_m'],
        p['core_forward_end_m'], p['taper_forward_end_m'], p['taper_backward_length_m'], p['lateral_outer_max_m'],
        p['lateral_opening'], p['lateral_start_m'], p['lateral_taper_m'], p['target_depth_m'],
        p['relief_amplitude_m'], p['relief_scale_m'], p['relief_smoothing_m'], p['source_edge_taper_m']], dtype=float)
    if (not np.isfinite(numeric).all() or np.linalg.norm(numeric[2:4]) == 0
        or not 0 <= scenario.core_forward_start_m < scenario.core_forward_end_m < scenario.taper_forward_end_m
        or min(scenario.taper_backward_length_m,scenario.lateral_outer_max_m,scenario.lateral_opening,scenario.lateral_start_m,
               scenario.lateral_taper_m,scenario.relief_scale_m,scenario.relief_smoothing_m,scenario.source_edge_taper_m) <= 0
        or not 0 <= scenario.relief_amplitude_m < scenario.target_depth_m):
        raise ValueError('invalid shelf scenario')
    if len(origin_xz_m)!=2 or not np.isfinite(origin_xz_m).all():
        raise ValueError('finite origin required')
    water = valid & ocean & ~unknown
    seed = tuple(scenario.ocean_seed_zx)
    if len(seed)!=2 or any(i<0 or i>=n for i,n in zip(seed,bed.shape)) or not water[seed]:
        raise ValueError('known ocean seed required')
    if np.any(bed[water] >= 0):
        raise ValueError('source ocean must be submerged')
    labels,_ = ndimage.label(water, structure=np.ones((3,3)))
    connected = labels == labels[seed]
    zz,xx = np.indices(bed.shape, dtype=np.float64)
    x = origin_xz_m[0] + xx*spacing_m - scenario.apex_xz_m[0]
    z = origin_xz_m[1] + zz*spacing_m - scenario.apex_xz_m[1]
    direction = np.asarray(scenario.direction_xz,dtype=float); direction /= np.linalg.norm(direction)
    forward = x*direction[0]+z*direction[1]
    lateral = -x*direction[1]+z*direction[0]
    edge = np.minimum(scenario.lateral_outer_max_m,
                      scenario.lateral_start_m+scenario.lateral_opening*np.maximum(forward,0.))
    weight = (_smoothstep((forward-scenario.core_forward_start_m+scenario.taper_backward_length_m)/scenario.taper_backward_length_m)
              * _smoothstep((scenario.taper_forward_end_m-forward)/
                            (scenario.taper_forward_end_m-scenario.core_forward_end_m))
              * _smoothstep((edge-np.abs(lateral))/scenario.lateral_taper_m))
    edge_distance = np.minimum.reduce((xx, zz, bed.shape[1]-1-xx, bed.shape[0]-1-zz))*spacing_m
    weight *= _smoothstep(edge_distance/scenario.source_edge_taper_m)
    weight *= connected
    # Isolate bounded local source relief by subtracting an ocean-only Gaussian
    # background; this adds no noise and prevents land elevations contaminating it.
    sigma = scenario.relief_smoothing_m/spacing_m
    denominator = ndimage.gaussian_filter(connected.astype(float),sigma,mode='nearest')
    numerator = ndimage.gaussian_filter(np.where(connected,bed,0.).astype(float),sigma,mode='nearest')
    local_mean = np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator>1e-12)
    target = -scenario.target_depth_m + scenario.relief_amplitude_m*np.tanh((bed-local_mean)/scenario.relief_scale_m)
    transformed = bed.astype(np.float64,copy=True)
    active = connected & (weight > 0.)
    # Never deepen already shallower terrain and never manufacture emerged land.
    transformed[active] = bed[active] + weight[active]*np.maximum(target[active]-bed[active],0.)
    return {'bed_m':transformed,'shelf_weight':weight,'forward_m':forward,'lateral_m':lateral,
            'target_bed_m':target,'eligible':connected}


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def publish_shelf_source(source_path, output_path, scenario=ShelfScenario()):
    """Hash-check source, create a new load_source-compatible directory atomically."""
    source_path, output_path = Path(source_path), Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    source,(bed,valid,ocean)=load_source(source_path)
    unknown_path=source_path/'unknown_wet.npy'
    if _sha(unknown_path)!=source['files_sha256']['unknown_wet']:
        raise ValueError('unknown wet source hash mismatch')
    unknown=np.load(unknown_path,allow_pickle=False)
    result=shelf_arrays(bed,valid,ocean,unknown,source['origin_xz_m'],source['spacing_m'],scenario)
    height=result['bed_m']-bed
    active=height>0
    if not np.array_equal(result['bed_m'][~(valid&ocean&~unknown)],bed[~(valid&ocean&~unknown)]):
        raise ValueError('non-ocean cells changed')
    output_path.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix=output_path.name+'-pending-',dir=output_path.parent))
    try:
        for name in ('valid','ocean','unknown_wet'):
            shutil.copyfile(source_path/(name+'.npy'),temp/(name+'.npy'))
        shutil.copyfile(source_path/'bed_m.npy',temp/'original_bed_m.npy')
        np.save(temp/'bed_m.npy',result['bed_m'])
        np.save(temp/'shelf_weight.npy',result['shelf_weight'].astype(np.float32))
        hashes={name:_sha(temp/(name+'.npy')) for name in ('bed_m','valid','ocean','unknown_wet','original_bed_m','shelf_weight')}
        scenario_meta={'algorithm':'local-ocean-shelf-smoothstep-relief-v1', 'parameters':asdict(scenario),
            'parent_source_identity':source['source_identity'],'parent_manifest_sha256':_sha(source_path/'manifest.json'),
            'parent_files_sha256':source['files_sha256'],'file_sha256':hashes,
            'formula':'target=-target_depth+amplitude*tanh((original-ocean_gaussian_mean)/relief_scale); bed=original+weight*max(target-original,0); weight=forward_smoothstep*end_smoothstep*lateral_smoothstep*source_edge_smoothstep*known_seed_connected_ocean',
            'classification':'explicit geological bathymetry change; not sediment, not measured paleogeography',
            'altered_area_m2':float(active.sum()*source['spacing_m']**2),
            'bathymetry_uplift_bulk_m3':float(height.sum(dtype=np.float64)*source['spacing_m']**2),
            'maximum_uplift_m':float(height.max()),
            'no_randomness':'deterministic spatial transform; no random subseed'}
        derived_id=hashlib.sha256(json.dumps(scenario_meta,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        manifest=dict(source);manifest['source_identity']=derived_id
        manifest['files_sha256']={k:hashes[k] for k in ('bed_m','valid','ocean','unknown_wet')}
        manifest['shelf_scenario']=scenario_meta
        (temp/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        os.rename(temp,output_path)
    except BaseException:
        shutil.rmtree(temp)
        raise
    return manifest
