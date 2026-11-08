from types import SimpleNamespace

import numpy as np

from terrain_pipeline.coastal_delta_branching import _event_edges, mouth_exterior_faces


def test_wide_mouth_side_face_and_dry_barrier():
    bed = np.ones((5, 6))
    bed[:, 5] = -2
    bed[1, 4] = -2
    state = SimpleNamespace(valid_mask=np.ones_like(bed, dtype=bool), bed_m=bed,
                            base_bed_m=np.full_like(bed, -2), porosity=np.full_like(bed, .4),
                            spacing_m=1., ocean_seed_mask=np.zeros_like(bed, dtype=bool))
    state.ocean_seed_mask[:, 5] = True
    progress = {'routes': [[[3, 2], [2, 2]]], 'shares': [1.],
                'discharge_m3_s': 10., 'solid_rate_m3_s': 1., 'node_footprints': [
        [2, 2, [[2, 2, 1., 0., 0., 0.], [1, 2, 1., 0., 0., 0.],
                [1, 3, 1., 0., 0., 0.]]]]}
    assert mouth_exterior_faces(state, progress) == [[[1, 4]]]
    edges = _event_edges(state, progress, 0.)
    assert edges[-1]['from_zx'] == [2, 2]
    assert edges[-1]['to_zx'] == [1, 4]
    assert edges[-1]['discharge_m3_s'] == 10.
    progress['node_footprints'][0][2][1][3] = 1.8
    assert mouth_exterior_faces(state, progress) == [[]]
    del progress['node_footprints']
    assert mouth_exterior_faces(state, progress) == [[]]
