"""Save isolated branch sensitivity and sediment transport comparisons."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from terrain_pipeline.surface_rivers.branches import build_branches
from terrain_pipeline.surface_rivers.hydraulics import BranchHydraulics, ChannelHydraulics
from terrain_pipeline.surface_rivers.transport import TransportInput, route_sediment


def main():
    output = Path('verification/river-experiments')
    output.mkdir(parents=True, exist_ok=True)
    terrain = np.zeros((7, 11))
    main_path = [(3, x) for x in range(1, 10)]
    for x in range(1, 10):
        terrain[3, x] = 20 - x
    for x in range(2, 9):
        terrain[2, x] = 19 - x
    fractions = []
    for depth in (1, 2):
        hydraulics = BranchHydraulics(ChannelHydraulics(2, 2, .03, .01),
                                      ChannelHydraulics(2, depth, .03, .01))
        result = build_branches(terrain, main_path, np.ones_like(terrain, bool),
                                100, hydraulics=hydraulics)
        fractions.append(result.fractions[1])
    shape = (12, 15)
    land = np.zeros(shape, bool)
    land[:2] = True
    ocean = ~land
    direction = np.zeros(shape + (2,))
    direction[..., 0] = 1
    boundary = np.zeros(shape, bool)
    boundary[-1] = True
    report = {'experimental_only': True, 'side_depth': [1, 2],
              'side_fraction': fractions, 'cases': []}
    figures, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    axes[0].bar(['Depth 1', 'Depth 2'], fractions)
    axes[0].set(title='Side channel flow share', ylim=(0, 1))
    payload = {}
    for index, settling in enumerate((.1, 2.)):
        result = route_sediment(TransportInput(
            np.zeros(shape), land, ocean, ocean.astype(float), direction,
            ocean.astype(float), boundary, ((0, 7), (1, 7), (2, 7)),
            10, settling, max_steps=12))
        budget = result.deposited_solid + result.exported_solid + result.mobile_solid.sum()
        assert abs(budget - 10) < 1e-9
        report['cases'].append({'settling_velocity': settling,
            'input_solid': 10, 'deposited_solid': result.deposited_solid,
            'mobile_solid': float(result.mobile_solid.sum()),
            'exported_solid': result.exported_solid, 'budget_residual': float(10 - budget)})
        payload[f'height_delta_{index}'] = result.height_delta
        payload[f'mobile_solid_{index}'] = result.mobile_solid
        plot = axes[index + 1].imshow(result.height_delta, origin='lower', cmap='terrain')
        axes[index + 1].set_title(f'Deposit: settling velocity {settling}')
        figures.colorbar(plot, ax=axes[index + 1])
    figures.savefig(output / 'comparison.png', dpi=140)
    plt.close(figures)
    np.savez_compressed(output / 'comparison.npz', **payload,
                        metadata=np.array(json.dumps(report)))
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
