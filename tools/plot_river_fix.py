"""Render reproducible river bank and longitudinal comparisons for the demo seed."""
import csv
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'preview/watershed/river-profile-v2.csv'
CROSS = ROOT / 'preview/watershed/river-cross-section-v2.csv'
OUTPUT = ROOT / 'preview/watershed/river-fix.png'

with PROFILE.open(newline='', encoding='utf-8') as stream:
    rows = list(csv.DictReader(stream))

route = [row for row in rows if abs(float(row['z'])) < 55]
route.sort(key=lambda row: float(row['x']))

fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), layout='constrained')
axes[0].plot([float(r['x']) for r in route], [float(r['water']) for r in route],
             color='#1679b9', linewidth=2, label='Corrected river level')
axes[0].plot([float(r['x']) for r in route], [min(float(r['original_bank_left']),
             float(r['original_bank_right'])) for r in route], color='#8c6b42',
             alpha=.7, linewidth=1, label='Lower original bank')
axes[0].set(title='Along the main valley', xlabel='Local distance east (blocks)',
            ylabel='Local elevation (blocks)')
axes[0].legend()

with CROSS.open(newline='', encoding='utf-8') as stream:
    section = list(csv.DictReader(stream))
z = [float(r['local_z']) for r in section]
axes[1].plot(z, [float(r['legacy_ground']) for r in section],
             color='#be5a47', alpha=.65, label='Previous ground')
axes[1].plot(z, [float(r['corrected_ground']) for r in section],
             color='#8c6b42', label='Corrected ground')
axes[1].plot(z, [float(r['legacy_water']) if r['legacy_water'] else float('nan') for r in section],
             color='#df9066', label='Previous water')
axes[1].plot(z, [float(r['corrected_water']) if r['corrected_water'] else float('nan') for r in section],
             color='#1679b9', label='Corrected water')
axes[1].set(title='Before and after near reported X 382', xlabel='Local north/south (blocks)',
            ylabel='Local elevation (blocks)')
axes[1].legend()
fig.suptitle('Terrain-aware watershed profile (seed 20260927)', fontsize=14)
fig.savefig(OUTPUT, dpi=160)
print(OUTPUT)
