"""Finite, optional process diagnostics on a separately sampled mountain window."""
import hashlib
import numpy as np
from terrain_pipeline.procedural_mountains import MountainConfig, rasterize
from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
from terrain_pipeline.surface_rivers.metric_drainage import route_diagnostic, accumulate_local_discharge
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step
from terrain_pipeline.bounded_glacier import advance_glacier


def prepare_process_evidence(origin=(0.0, 0.0), world_seed=20260903):
    """Sample 65x65 at 30 m; model an explicit 9-cell subwindow, never mutate source."""
    cfg = MountainConfig(world_seed=world_seed)
    bed = rasterize(origin, (65, 65), 30.0, cfg)['height_m'].copy()
    sha = hashlib.sha256(bed.tobytes()).hexdigest()
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), *origin, 30., 30., 'generated_terrain',
                          'independent_procedural_mountains', sha, generation_seed=world_seed)
    kind = np.full(bed.shape, 'interior', dtype='<U24')
    kind[[0, -1], :] = 'unknown_boundary'
    kind[:, [0, -1]] = 'unknown_boundary'
    boundary = BoundaryGrid(kind, np.zeros(bed.shape, bool), 'unknown perimeter', hashlib.sha256(kind.tobytes()).hexdigest())
    graph = route_diagnostic(terrain, boundary)
    discharge = accumulate_local_discharge(graph, np.full(bed.shape, 0.001))
    floor = bed - 2.0
    after = conservative_diffusion_step(bed, np.ones(bed.shape), np.zeros(bed.shape, dtype=int), floor, .01, 30.)
    delta = after - bed
    x = np.arange(9, dtype=float) * 30.0
    line = bed[32, 28:37].copy()
    glacier = advance_glacier(thickness_start_m=np.full(9, 20.), bed_m=line,
        accumulation_mm=np.full((1, 9), 10.), ablation_mm=np.full((1, 9), 5.),
        time_edges_s=[0., 86400.], x_m=x, width_m=30., bedrock_erodible_m3=np.full(9, 900.))
    gd = glacier['arrays']['bed_delta_m'][-1]
    arrays = {'source_height_m': bed, 'routed_q_m3_s': discharge['routed_q_m3_s'],
              'terminal_q_m3_s': discharge['terminal_q_m3_s'], 'diffused_height_m': after,
              'diffusion_delta_m': delta, 'glacier_source_x_m': origin[0] + np.arange(28, 37) * 30.,
              'glacier_source_z_m': np.full(9, origin[1] + 32 * 30.), 'glacier_before_m': line,
              'glacier_final_bed_delta_m': gd, 'glacier_after_m': line + gd,
              **{'glacier_' + k: v for k, v in glacier['arrays'].items()}}
    metadata = {'world_seed': world_seed, 'source_kind': 'generated_terrain', 'source_sha256': sha,
                'origin_m_xz': list(origin), 'spacing_m': 30., 'shape_zx': [65, 65],
                'routing': {'boundary': 'unknown perimeter', 'local_discharge_m3_s_per_cell': .001,
                            **{k: v for k, v in discharge.items() if not isinstance(v, np.ndarray)}},
                'diffusion': {'operator': 'conservative_diffusion_step', 'coefficient': .01,
                              'sediment_flux': 1., 'initial_mobile_layer_m': 2., 'row_zero_closed': True,
                              'volume_delta_m3': float(delta.sum() * 900.), 'minimum_floor_margin_m': float(np.min(after - floor))},
                'glacier': {'scope': '9 cells, 240 m along-source; finite standalone diagnostic, no coupled valley claim',
                            'initial_thickness_m': 20., 'bedrock_stock_m3_per_cell': 900.,
                            'accumulation_mm_water_equivalent': 10., 'ablation_mm_water_equivalent': 5.,
                            'time_edges_s': [0., 86400.], 'model_metadata': glacier['metadata'], 'ledger': glacier['ledger']}}
    return arrays, metadata
