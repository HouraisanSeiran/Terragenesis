"""Lightweight acceptance checks for the saved connector artifact."""
from pathlib import Path
import json
import numpy as np

CASE=Path('verification/upstream-sediment/same-source-20261016-04')

def test_saved_case_budget_and_shapes():
    report=json.loads((CASE/'summary.json').read_text(encoding='utf-8'))
    assert report['nodes']==85 and report['days']==365
    assert abs(report['path_m']-report['length_sum_m'])<1e-6
    budget=report['mouth_budget']
    assert abs(budget['residual_solid_m3'])<1e-8
    assert abs(budget['input_solid_m3']-budget['deposited_solid_m3']-budget['ocean_export_solid_m3'])<1e-6
    assert report['frozen_water'] is True and report['hydraulic_ready'] is False
    assert report['interface_bed_difference_m']>1.0
    assert np.load(CASE/'geometry.npz')['node_xz_m'].shape==(85,2)
