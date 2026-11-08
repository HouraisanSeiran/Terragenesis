import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.coastal_terrain import prepare_archipelago as prepare

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--strength', type=float, required=True)
    p.add_argument('--expected-baseline-identity', required=True)
    p.add_argument('--memory-budget-bytes', type=int, default=1200000000)
    a = p.parse_args()
    m, _ = prepare(a.baseline, a.output, a.strength, a.expected_baseline_identity, a.memory_budget_bytes)
    print(m['identity'])

