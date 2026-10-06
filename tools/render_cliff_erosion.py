"""Render exported production Java surfaces and a separately verified Minecraft block slice."""
from pathlib import Path
import argparse
import json
import os

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'cache/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

OUT = ROOT / 'preview/cliff-erosion-v2'


def surface_panel(ax, data, title):
    columns = int(data['column'].max()) + 1
    rows = int(data['row'].max()) + 1
    nx = 1 / np.hypot(1, .35)
    nz = .35 * nx
    along = (data['x'] - 256) * nz - (data['z'] - 256) * nx
    outward = (data['x'] - 256) * nx + (data['z'] - 256) * nz
    points = np.column_stack([along, outward, data['y']])
    triangles = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = row * columns + column
            if abs(data['u'][a]) > 115 or abs(data['v'][a]) > 40:
                continue
            b, c, d = a + 1, a + columns, a + columns + 1
            triangles.extend([(a, b, d), (a, d, c)])
    triangles = np.asarray(triangles)
    vertices = points[triangles]
    normals = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    normals /= np.maximum(1e-9, np.linalg.norm(normals, axis=1))[:, None]
    light = np.array([-.4, 1., 1.2]); light /= np.linalg.norm(light)
    shade = .38 + .55 * np.maximum(0, normals @ light)
    layers = .95 + .05 * np.sin(vertices[:, :, 2].mean(axis=1) * .5)
    colors = np.clip(shade[:, None] * layers[:, None] * np.array([.91, .85, .73]), 0, 1)
    mesh = Poly3DCollection(vertices, facecolors=colors, edgecolors='none', rasterized=True)
    ax.add_collection3d(mesh)
    ax.set(xlim=(-120, 120), ylim=(-42, 42), zlim=(65, 145), title=title)
    ax.set_box_aspect((2.3, 1, 1)); ax.set_proj_type('ortho'); ax.view_init(elev=20, azim=76)
    ax.set_xlabel('Along wall (blocks)', fontsize=8)
    ax.set_ylabel('Outward', fontsize=8); ax.set_zlabel('Height', fontsize=8)
    ax.tick_params(labelsize=7); ax.grid(False)


def render_surfaces():
    fig = plt.figure(figsize=(17, 6), facecolor='#f4f2ed')
    stages = [('skeleton', '1  Base wall / 76 degrees'), ('rock', '2  Voronoi rock + joints'),
              ('eroded', '3  Attached runoff + lateral erosion')]
    for index, (name, title) in enumerate(stages, 1):
        data = np.genfromtxt(OUT / f'{name}.csv', names=True, delimiter=',')
        surface_panel(fig.add_subplot(1, 3, index, projection='3d'), data, title)
    fig.suptitle('Remote Mountains 0.3.0 — production Java geometry, fixed seed 20260927', fontsize=15)
    fig.text(.5, .035, 'Terrain Diffusion base → local XYZ VDM → rock cells → surface runoff erosion. Surface render, not an in-game screenshot.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=.01, right=.99, top=.91, bottom=.11, wspace=.02)
    fig.savefig(OUT / 'comparison.png', dpi=160, facecolor=fig.get_facecolor()); plt.close(fig)
    data = np.genfromtxt(OUT / 'eroded.csv', names=True, delimiter=',')
    shape = (int(data['row'].max()) + 1, int(data['column'].max()) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for ax, key, title, cmap in zip(axes, ['flow', 'erosion'], ['Cumulative surface discharge (log scale)', 'Rock retreat (blocks)'], ['Blues', 'magma']):
        values = data[key].reshape(shape)
        if key == 'flow': values = np.log1p(values)
        image = ax.imshow(values, extent=(-160, 160, 80, -80), cmap=cmap, aspect='auto')
        ax.set(xlim=(-125, 125), ylim=(32, -32), title=title, xlabel='Along wall (blocks)', ylabel='Local chart cross-wall coordinate')
        fig.colorbar(image, ax=ax, shrink=.8)
    fig.savefig(OUT / 'flow-and-erosion.png', dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 5), constrained_layout=True)
    for angle, lean, label in [(60, -1, '60° inward slope'), (90, 1, '90° vertical'), (60, 1, '60° outward overhang')]:
        d = np.genfromtxt(OUT / f'angle-{angle}-lean-{lean}.csv', names=True, delimiter=',')[28:53]
        ax.plot(d['out'] - d['out'][-1], d['height'] - d['height'][-1], linewidth=2, label=label)
    ax.set(xlabel='Outward offset from foot (blocks)', ylabel='Height above foot (blocks)', title='Angle and lean are independent parameters')
    ax.set_aspect('equal'); ax.grid(alpha=.2); ax.legend()
    fig.savefig(OUT / 'angles.png', dpi=150); plt.close(fig)


def render_blocks():
    path = ROOT / 'verification/erosion-server/world-1.json'
    if not path.exists(): return
    report = json.loads(path.read_text())['cliff']
    blocks = np.asarray(report['rows_top_to_bottom'])
    fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
    ax.imshow(blocks, origin='upper', interpolation='nearest', cmap=ListedColormap(['#c5e3ee', '#746d5e', '#4481c9', '#6c8c52']),
              vmin=0, vmax=3, extent=(report['x_min'], report['x_max_exclusive'], report['y_min']-.5, report['y_max']+.5))
    ax.set(title='Actual Minecraft server blocks — cliff slice Z=256', xlabel='World X', ylabel='World Y')
    fig.text(.5, .01, 'Read from generated game chunks; this is a block cross-section, not a client screenshot.', ha='center', fontsize=8)
    fig.savefig(OUT / 'minecraft-block-slice.png', dpi=150); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--blocks-only', action='store_true'); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.blocks_only: render_surfaces()
    render_blocks()
    print('Rendered', OUT)
