"""Consolidated prepare_channel_vdm implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i40_argparse
from datetime import datetime as _i40_datetime
from datetime import timezone as _i40_timezone
import json as _i40_json
from pathlib import Path as _i40_Path
import sys as _i40_sys
import numpy as _i40_np
from terrain_pipeline.vdm_cuts import CliffRecipe as _i40_CliffRecipe
from terrain_pipeline.vdm_cuts import load_vdm as _i40_load_vdm
from terrain_pipeline.vdm_cuts import save_vdm as _i40_save_vdm
from terrain_pipeline.common_infra import file_sha256 as _i40_file_sha256
from terrain_pipeline.common_infra import publish_bytes as _i40_publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as _i40_load_basin_hierarchy
from terrain_pipeline.vdm_cuts import build_channel_vdm as _i40_build_channel_vdm
from terrain_pipeline.td_native_channel_surface import load_channel_surface as _i40_load_channel_surface
CATEGORY = 'C'
ROOT = _i40_Path(__file__).resolve().parents[1]
_i40_sys.path.insert(0, str(ROOT))

def prepare(configuration, expected_sha256, output):
    configuration = _i40_Path(configuration).resolve(strict=True)
    if _i40_file_sha256(configuration) != expected_sha256:
        raise ValueError('VDM configuration pin mismatch')
    config = _i40_json.loads(configuration.read_text(encoding='utf-8'))
    if set(config) not in ({'surface', 'hierarchy', 'recipe'}, {'surface', 'hierarchy', 'recipe', 'form'}):
        raise ValueError('VDM configuration fields mismatch')
    surface = _i40_load_channel_surface(**config['surface'])
    hierarchy = _i40_load_basin_hierarchy(**config['hierarchy'])
    settings = dict(config['recipe'])
    settings['center_xz_m'] = tuple(settings['center_xz_m'])
    settings['outward_xz'] = tuple(settings['outward_xz'])
    form = None
    save, load = (_i40_save_vdm, _i40_load_vdm)
    if 'form' in config:
        from terrain_pipeline.vdm_cuts import FormRecipe
        from terrain_pipeline.vdm_cuts import save_formed_vdm
        from terrain_pipeline.vdm_cuts import load_formed_vdm
        form = FormRecipe(**config['form'])
        save, load = (save_formed_vdm, load_formed_vdm)
    result = _i40_build_channel_vdm(surface, hierarchy, recipe=_i40_CliffRecipe(**settings), form=form)
    arrays = result['arrays']
    displaced = arrays['vertices_xyz_m']
    reference = arrays['reference_xyz_m'].reshape(-1, 3)
    triangles = arrays['triangles']
    normals = _i40_np.cross(displaced[triangles[:, 1]] - displaced[triangles[:, 0]], displaced[triangles[:, 2]] - displaced[triangles[:, 0]])
    changed = _i40_np.any(displaced != reference, axis=1)
    output = _i40_Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    bundle_path = output / 'vdm.npz'
    save(bundle_path, result)
    pin = dict(path=str(bundle_path), expected_sha256=_i40_file_sha256(bundle_path), expected_identity=result['identity_sha256'])
    loaded = load(**pin)
    if not _i40_np.array_equal(loaded['arrays']['vertices_xyz_m'], displaced):
        raise ValueError('VDM saved XYZ changed')
    for name, vertices in (('reference', reference), ('derived', displaced)):
        lines = ['# physical metres XYZ; source parameter topology preserved; not a closed solid']
        lines.extend(('v ' + ' '.join((format(float(value), '.17g') for value in vertex)) for vertex in vertices))
        lines.extend(('f ' + ' '.join((str(int(value) + 1) for value in face)) for face in triangles))
        _i40_publish_bytes(output / (name + '.obj'), ('\n'.join(lines) + '\n').encode('ascii'))
    review = dict(schema='metric-vdm-review-v1', coordinates='physical metres XYZ, y up', form=result['metadata'].get('form'), effective_recipe=result['metadata']['recipe'], geometry_schema=result['metadata']['schema'], source_identity=surface['identity_sha256'], vdm_identity=result['identity_sha256'], shape=list(arrays['protected_mask'].shape), reference_xyz_m=reference.tolist(), displacement_xyz_m=arrays['displacement_xyz_m'].reshape(-1, 3).tolist(), triangles=triangles.tolist(), protected_mask=arrays['protected_mask'].ravel().tolist(), hydraulic_ready=False, publishable=False, self_intersection_verified=False)
    _i40_publish_bytes(output / 'review.json', _i40_json.dumps(review, separators=(',', ':'), allow_nan=False).encode())
    for record in (config['surface'], config['hierarchy']):
        if _i40_file_sha256(record['path']) != record['expected_sha256']:
            raise ValueError('VDM source changed during export')
    if _i40_file_sha256(configuration) != expected_sha256:
        raise ValueError('VDM configuration changed during export')
    report = dict(schema='td-channel-vdm-preparation-v1', inputs=config, configuration=dict(path=str(configuration), expected_sha256=expected_sha256), vdm=pin, vertices=len(displaced), triangles=len(triangles), changed_vertices=int(changed.sum()), downward_facing_triangles=int((normals[:, 1] < 0).sum()), protected_vertices=int(arrays['protected_mask'].sum()), max_displacement_m=float(_i40_np.linalg.norm(displaced - reference, axis=1).max()), cold_roundtrip_passed=True, source_unchanged=True, swept_protected_boxes_clear=True, river_protection_scope='saved candidate cut footprint and coarse protected/unknown stencil with collar', geometry_migration='Java CliffGeometry skeleton formula, metric configurable placement', form=result['metadata'].get('form'), effective_recipe=result['metadata']['recipe'], geometry_schema=result['metadata']['schema'], water_generated=False, solver_advanced=False, hydraulic_ready=False, publishable=False, natural_outlet_verified=False, self_intersection_verified=False, limitations=['no Voronoi or runoff/erosion solver migration in this batch', 'source 1m bed is derived from 30m TD, not measured 1m terrain', 'source hour diagnostic identity retained; not new accepted hydraulics', 'triangle normals alone do not prove a non-self-intersecting solid'], artifacts={name: _i40_file_sha256(output / name) for name in ('reference.obj', 'derived.obj', 'review.json')}, code_sha256={name: _i40_file_sha256(ROOT / name) for name in ('terrain_pipeline/vdm_cuts.py', 'terrain_pipeline/vdm_cuts.py', 'tools/prepare_channel_vdm.py')})
    if form is not None:
        report['code_sha256']['terrain_pipeline/vdm_cuts.py'] = _i40_file_sha256(ROOT / 'terrain_pipeline/vdm_cuts.py')
    _i40_publish_bytes(output / 'report.json', _i40_json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    return report
