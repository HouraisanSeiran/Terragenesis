"""Independent regional experiment. Run from repository root with PYTHONPATH=."""
import json
import time
from pathlib import Path

import numpy as np
from terrain_pipeline import coastal_delta_window as window
from terrain_pipeline.coastal_delta_routes import prepare_routes, save_routes
from terrain_pipeline.coastal_delta_evolution import initialize, advance_years, advance_event, save, TidalConfig
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_marine_sediment import load_state, MarineConfig
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_product import file_hash

OUT = Path('.scratch/delta-large-acceptance-20261103')
OLD = Path('.scratch/coast-marine-reorganization-20261102')
SHAPE = (500, 500)
ORIGIN = (-39900., -39900.)
SPACING = 200.

def main():
    started = time.perf_counter()
    source = OUT / 'case-source'
    if not source.exists():
        sample = window.sample_pages
        migrate = window.migrate_volume
        window.SHAPE, window.ORIGIN, window.SPACING = SHAPE, ORIGIN, SPACING
        window.sample_pages = lambda manifest: sample(manifest, SHAPE, ORIGIN, SPACING)
        window.migrate_volume = lambda array, old_origin, old_spacing: migrate(array, old_origin, old_spacing, SHAPE, ORIGIN, SPACING)
        window.prepare(source)
    print('source prepared', time.perf_counter()-started, flush=True)
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    state = load_state(source/'state.npz')
    fine_meta = json.loads((OLD/'river-connection-v4-data.json').read_text(encoding='utf-8-sig'))
    assert file_hash(OLD/'river-connection-v4-data.npz') == fine_meta['data_sha256']
    with np.load(source/'source.npz') as src, np.load(OLD/'river-connection-v4-data.npz') as fine:
        _, routes, meta = prepare_routes(state, src['source_ocean'], fine, fine_meta)
    meta.update(source_identity=state.source_identity, source_sha256=manifest['source_sha256'], state_sha256=manifest['state_sha256'], fine_sha256=fine_meta['data_sha256'])
    save_routes(OUT/'routes', routes, meta)
    print('routes', json.dumps({k:meta[k] for k in ('main_length_m','candidate_count','accepted_q_m3_s','extension_port_stage_m')}), flush=True)
    state, progress = initialize(state, routes, meta)
    save(OUT/'initial', state, progress)
    cfg = HydraulicConfig(meta['extension_port_stage_m'])
    print('hydraulic', json.dumps(solve(state, progress, 0., cfg), default=lambda x: x.tolist() if hasattr(x,'tolist') else x)[:1000], flush=True)
    state, progress = advance_years(state, progress, .0625, input_id='regional-formation', hydraulic_config=cfg, marine_config=LongtermConfig(settling_velocity_m_s=1e-5), river_deposition_fraction=.0001, tidal_config=TidalConfig(amplitude_m=.3, phase_count=4), step_years=.0625)
    save(OUT/'formed', state, progress)
    print('formed', time.perf_counter()-started, flush=True)
    forcing = MarineConfig(step_s=3600., tide_amplitude_m=.3, wave_height_m=.5, transport_rate_s=1e-6, entrainment_rate_s=1e-7, settling_rate_s=1e-6)
    state, event = advance_event(state, progress, 3600., forcing, input_id='regional-event', hydraulic_config=cfg, inlet_solid_rate_m3_s=.08)
    save(OUT/'event', state, event['updated_progress'])
    (OUT/'event-report.json').write_text(json.dumps(event, default=lambda x: x.tolist() if hasattr(x,'tolist') else x, indent=2), encoding='utf-8')
    print('event', time.perf_counter()-started, flush=True)

if __name__ == '__main__':
    main()
