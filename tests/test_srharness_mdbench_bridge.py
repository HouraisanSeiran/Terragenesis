import sys
from pathlib import Path

import numpy as np
import pytest
pytest.importorskip('src.export_problems', reason='optional mdbench bridge environment required')
from argparse import Namespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import run_srharness_mdbench_bridge as bridge  # noqa: E402


TASK = str(ROOT / '.scratch/deepseek-harness/tasks/srharness-mdbench-bridge-20261016-01/vendor/mdbench/tasks/physics/Terminal Settling/Terminal Settling - Original.yaml')


@pytest.fixture()
def exported(tmp_path):
    bridge._cmd_export(Namespace(task=TASK, output=str(tmp_path / 'data'), train_samples=128, id_test_samples=64, ood_test_samples=64))
    return tmp_path / 'data'


def test_export_load_public_problem(exported):
    assert (exported / 'problem' / 'problem.json').exists()
    assert (exported / 'problem' / 'train.npy').exists()
    assert (exported / 'answer' / 'answer.json').exists()

    train = np.load(exported / 'problem' / 'train.npy')
    problem, variables, target, columns, data = bridge._load_public_problem(exported / 'problem', np)

    assert columns == ['speed', 'radius', 'particle_density', 'fluid_density', 'viscosity']
    assert train.shape == (5, 128)
    assert target == 'speed'
    assert isinstance(data, dict)

    for i, col in enumerate(columns):
        np.testing.assert_array_equal(data[col], train[i])
        assert data[col].shape == (128,)


def test_public_loader_validation(exported):
    from src import validate_problem

    problem_dir = exported / 'problem'
    prob_path = problem_dir / 'problem.json'
    train_path = problem_dir / 'train.npy'

    original = prob_path.read_text(encoding='utf-8')

    problem, variables, target, columns, data = bridge._load_public_problem(problem_dir, np)
    assert target == 'speed'
    assert prob_path.read_text(encoding='utf-8') == original

    import json

    mutated = json.loads(original)
    mutated['mechanism_model'] = 'x'
    prob_path.write_text(json.dumps(mutated), encoding='utf-8')
    try:
        with pytest.raises(ValueError):
            bridge._load_public_problem(problem_dir, np)
    finally:
        prob_path.write_text(original, encoding='utf-8')

    train = np.load(train_path)
    nan_train = train.copy()
    nan_train[0, 0] = np.nan
    np.save(train_path, nan_train)
    try:
        with pytest.raises(validate_problem.ValidationError):
            bridge._load_public_problem(problem_dir, np)
    finally:
        np.save(train_path, train)

    obj_train = np.empty((5, 128), dtype=object)
    np.save(train_path, obj_train, allow_pickle=True)
    try:
        with pytest.raises(ValueError):
            bridge._load_public_problem(problem_dir, np)
    finally:
        np.save(train_path, train)
