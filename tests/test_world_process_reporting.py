import numpy as np

from terrain_pipeline.world_process_reporting import island_peak_report


def test_peaks_use_prepared_ownership_and_final_process_extrema():
    initial=np.array([[100.,300.,900.],[500.,50.,800.]])
    final=np.array([[120.,250.,900.],[400.,55.,800.]])
    owner=np.array([[1,1,0],[2,2,0]])
    report=island_peak_report(initial,final,owner,spacing_m=2000.,source_identity='initial',
        final_identity='final',component_ids={1:'island-one',2:'island-two'})
    assert [r['component_id'] for r in report['components']]==['island-one','island-two']
    assert [r['initial_peak_elevation_m'] for r in report['components']]==[300.,500.]
    assert [r['final_peak_elevation_m'] for r in report['components']]==[250.,400.]
    assert report['components'][0]['sampled_support_area_m2']==8e6
    assert np.array_equal(final,np.array([[120.,250.,900.],[400.,55.,800.]]))
