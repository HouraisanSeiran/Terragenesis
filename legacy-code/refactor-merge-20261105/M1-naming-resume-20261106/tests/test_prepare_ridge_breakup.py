import numpy as np
import pytest
from tools.prepare_ridge_breakup import generate, metrics


def test_metrics_show_constant_structure_has_no_gradient():
    fields = {name: np.ones((5, 5)) for name in ('original_delta_m','gaussian_delta_m','breakup_delta_m','final_delta_m','gap_field')}
    fields['metadata'] = {'config': {'gap_strength': .65}}
    fields['ridge_retention'] = np.ones((5, 5))
    fields['warped_delta_m'] = np.ones((5, 5))
    result = metrics(fields, 120.)
    assert result['gaussian']['mean_abs_change_from_original_m'] == 0
    assert result['gaussian']['gradient_energy'] == 0


def test_existing_destination_is_preserved(tmp_path):
    target = tmp_path / 'output'
    target.mkdir()
    (target / 'keep').write_text('keep')
    with pytest.raises(FileExistsError):
        generate(target)
    assert (target / 'keep').read_text() == 'keep'
