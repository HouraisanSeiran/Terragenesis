"""只读重绘已验收的海洋输送 checkpoint；不调用求解器。"""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.coastal_delta_product import load_checkpoint, _source_fingerprint
from terrain_pipeline.coastal_marine_sediment import classify_ocean
from tools.render_remote_sensing import surface_rgb

WORK = ROOT / '.scratch/coast-marine-reorganization-20261102'
SOURCE = ROOT / '.scratch/delta-scale-suite-20261102/source-case300'
BASE = WORK / 'base-product-v2'
DEFAULT_OUTPUT = ROOT / '验收图片/海岸三角洲长期输沙-20261103'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def prefix(value):
    path = Path(value)
    return path if path.is_absolute() else WORK / path


def compatible(reference, state):
    return (reference.source_identity == state.source_identity
            and reference.origin_xz_m == state.origin_xz_m
            and reference.spacing_m == state.spacing_m
            and np.array_equal(reference.valid_mask, state.valid_mask)
            and np.array_equal(reference.ocean_seed_mask, state.ocean_seed_mask)
            and np.array_equal(reference.base_bed_m, state.base_bed_m))


def packets_match(before, after):
    # An event without new packets may release previously pending stock.
    mutable = {'pending_solid_m3', 'delivered_solid_m3', 'delivered_water_m3'}
    if len(before) != len(after):
        return False
    for left, right in zip(before, after):
        if {k: v for k, v in left.items() if k not in mutable} != {k: v for k, v in right.items() if k not in mutable}:
            return False
        for key in ('delivered_solid_m3', 'delivered_water_m3'):
            if left.get(key) is not None and (right.get(key) is None or right[key] < left[key]):
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', nargs='?', default='ltransport-v2-lobe-stage20')
    parser.add_argument('--event', help='对应事件 checkpoint 前缀')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    initial_prefix, final_prefix = WORK / 'growth-v3-stage10', prefix(args.checkpoint)
    initial, initial_meta = load_checkpoint(initial_prefix)
    final, meta = load_checkpoint(final_prefix)
    if not compatible(initial, final) or meta.get('source_state_fingerprint') != _source_fingerprint(initial):
        raise ValueError('最终状态与原状态的来源或指纹不匹配')
    states = [initial, final]
    prefixes = [initial_prefix, final_prefix]
    if args.event:
        event_prefix = prefix(args.event)
        event, event_meta = load_checkpoint(event_prefix)
        if not compatible(final, event):
            raise ValueError('事件与最终状态来源不匹配')
        if event_meta != meta or not packets_match(final.consumed_packets, event.consumed_packets):
            raise ValueError('事件形成进度或输入记录与最终状态不一致')
        if not np.isfinite(event.time_s - final.time_s) or event.time_s <= final.time_s:
            raise ValueError('事件时间必须晚于最终状态')
        states.append(event)
        prefixes.append(event_prefix)
    base_meta = json.loads((BASE / 'manifest.json').read_text(encoding='utf8'))
    if base_meta['identity'] != initial.source_identity:
        raise ValueError('基础产品身份不匹配')
    base_bed = np.load(BASE / 'final_bed.npy', allow_pickle=False)
    if not np.array_equal(base_bed, initial.base_bed_m):
        raise ValueError('基础产品床面不匹配')

    beds = [s.bed_m for s in states]
    oceans = [classify_ocean(s, 0.)[0] for s in states]
    valid = initial.valid_mask
    change = beds[1] - beds[0]
    # Include every appreciable bed change, plus margin for context.
    relevant = valid & (np.abs(change) >= 0.01)
    if len(states) == 3:
        relevant |= valid & (np.abs(beds[2] - beds[0]) >= 0.01)
    if not relevant.any():
        raise ValueError('没有达到 0.01 m 的床变，无法确定局部窗口')
    rows, cols = np.where(relevant)
    pad = 10
    r0, r1 = max(0, rows.min()-pad), min(valid.shape[0], rows.max()+pad+1)
    c0, c1 = max(0, cols.min()-pad), min(valid.shape[1], cols.max()+pad+1)
    spacing = initial.spacing_m
    def window(r0, r1, c0, c1):
        x = initial.origin_xz_m[0] + np.arange(c0, c1) * spacing
        z = initial.origin_xz_m[1] + np.arange(r0, r1) * spacing
        extent = [x[0]-spacing/2, x[-1]+spacing/2, z[-1]+spacing/2, z[0]-spacing/2]
        width = extent[1]-extent[0]
        bar = max(v for v in [500, 1000, 2000, 5000, 10000, 20000, 50000] if v <= max(500, width/4))
        return np.s_[r0:r1, c0:c1], x, z, extent, bar

    broad = window(r0, r1, c0, c1)
    newly = oceans[0] & valid & (beds[1] >= 0)
    if not newly.any():
        raise ValueError('没有新增出露地块，无法按要求确定局部窗口')
    nr, nc = np.where(newly)
    context = int(np.ceil(3000 / spacing))
    local_window = window(max(0, nr.min()-context), min(valid.shape[0], nr.max()+context+1),
                          max(0, nc.min()-context), min(valid.shape[1], nc.max()+context+1))

    def terrain(ax, bed, ocean, view):
        sl, x, z, extent, bar = view
        width = extent[1] - extent[0]
        local = bed[sl]
        # Reuse the existing relief shader; compress its highlights uniformly,
        # preserving terrain rather than claiming a land-cover classification.
        rgb = surface_rgb(local, spacing) * 0.78
        depth = np.clip(-local / 15, 0, 1)[..., None]
        water = np.array([.24, .56, .62]) * (1-depth) + np.array([.06, .20, .34]) * depth
        rgb = np.where(ocean[sl][..., None], water, rgb)
        rgb = np.where((valid[sl] & (local < 0) & ~ocean[sl])[..., None], np.array([.5, .5, .5]), rgb)
        rgb = np.where(valid[sl][..., None], rgb, np.array([.8, .8, .8]))
        ax.imshow(rgb, extent=extent, origin='upper', interpolation='nearest')
        if ocean[sl].any() and (~ocean[sl]).any():
            ax.contour(x, z, ocean[sl].astype(float), levels=[.5], colors='black', linewidths=.7)
        ax.set(xlim=extent[:2], ylim=extent[2:], aspect='equal', xlabel='绝对 X（米，向东）', ylabel='绝对 Z（米，向南）')
        bx, bz = extent[0]+width*.06, extent[2]-(extent[2]-extent[3])*.07
        ax.plot([bx, bx+bar], [bz, bz], color='white', linewidth=3, solid_capstyle='butt')
        ax.text(bx+bar/2, bz, f'{bar/1000:g} km' if bar >= 1000 else f'{bar} m', color='white', ha='center', va='bottom', fontsize=8,
                bbox=dict(facecolor='black', alpha=.6, pad=1, edgecolor='none'))

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    titles = ['原状态｜growth-v3-stage10', f'继承原状态后继续 {meta["years_delivered"]:g} 等效年\n不含原状态前史']
    if len(states) == 3:
        titles.append(f'事件后｜相对增加 {states[2].time_s - final.time_s:g} 秒')
    def comparison(view, filename, label):
        fig, axes = plt.subplots(1, len(states), figsize=(7*len(states), 6), layout='constrained', squeeze=False)
        for ax, bed, ocean, title in zip(axes[0], beds, oceans, titles):
            terrain(ax, bed, ocean, view)
            ax.set_title(title)
        fig.suptitle(f'海岸三角洲长期输沙｜{label}（地形配色，非卫星观测）\n黑线：0 m 边界连通海岸；蓝：连通海洋；深灰：封闭负高程；浅灰：无效')
        image = out / filename
        fig.savefig(image, dpi=160)
        plt.close(fig)
        return image
    main_image = comparison(broad, '01-同源地形与海岸.png', '广域俯视')
    local_image = comparison(local_window, '03-新增出露局部俯视.png', '新增出露局部俯视｜600 m 格')

    fig, ax = plt.subplots(figsize=(9, 7), layout='constrained')
    terrain(ax, beds[1], oceans[1], broad)
    sl, _, _, extent, bar = broad
    submerged = oceans[1] & (change >= .01)
    classes = np.zeros(valid.shape, dtype=np.uint8)
    classes[submerged] = 1
    classes[newly] = 2
    ax.imshow(np.ma.masked_equal(classes[sl], 0), extent=extent, origin='upper', interpolation='nearest',
              cmap=ListedColormap(['#e49d37', '#e64324']), vmin=1, vmax=2, alpha=.78)
    ax.legend(handles=[Patch(color='#e64324', label='新出露：原为连通海洋，最终床 ≥ 0 m'),
                       Patch(color='#e49d37', label='连通海洋中净增厚 ≥ 0.01 m'),
                       Patch(color='#808080', label='封闭负高程'), Patch(color='#cccccc', label='无效区域')], loc='upper right', fontsize=8)
    ax.set_title('床面变化｜最终相对原状态（米）\n覆盖色仅显示分类，黑线为最终连通海洋边界')
    change_image = out / '02-新出露与水下沉积.png'
    fig.savefig(change_image, dpi=160)
    plt.close(fig)

    files = [p.with_suffix(ext) for p in prefixes for ext in ('.json', '.npz')]
    files += [BASE / 'manifest.json', BASE / 'final_bed.npy', SOURCE / 'manifest.json',
              ROOT / 'terrain_pipeline/coastal_delta_product.py', ROOT / 'terrain_pipeline/coastal_marine_sediment.py',
              ROOT / 'terrain_pipeline/coastal_marine_longterm.py', ROOT / 'terrain_pipeline/coastal_delta_lobes.py', ROOT / 'tools/render_remote_sensing.py', Path(__file__).resolve()]
    snapshots = out / '来源与实现快照'
    snapshots.mkdir()
    copied = []
    for i, file in enumerate(files):
        destination = snapshots / f'{i:02d}-{file.name}'
        shutil.copyfile(file, destination)
        copied.append({'source': str(file), 'sha256': digest(file), 'copy': str(destination.relative_to(out))})
    scenario = {'discharge_m3_s': meta['config']['discharge_m3_s'], 'solid_rate_m3_s': meta['config']['solid_rate_m3_s'],
                'forcing': meta.get('longterm_forcing'), 'description': '假定情景，非观测', 'equivalent_years': meta['years_delivered']}
    common = {'terrain_basis': 'Terrain Diffusion：source-case300 → base-product-v2 → growth-v3-stage10 → 所选 checkpoint',
              'source_manifest_recorded_td_binding': json.loads((SOURCE / 'manifest.json').read_text(encoding='utf8')),
              'source_identity': initial.source_identity, 'world_seed': 20261020, 'source_spacing_m': 30,
              'calculation_spacing_m': spacing, 'origin_xz_m': initial.origin_xz_m,
              'coordinates': '绝对 X 向东、Z 向南并向下；数组 [Z,X]，坐标为格心',
              'scenario': scenario,
              'event_binding_check': ('形成进度元数据完全相同；来源、基底、有效区及海洋种子一致；输入记录身份及不可变量一致，已交付量不减；事件时间正增量。此检查不证明唯一父状态。' if len(states) == 3 else '未提供事件'),
              'algorithms': ['coast-following-v2', 'growth-v3', meta.get('longterm_algorithm')],
              'coverage_status': 'partial', 'render': 'surface_rgb 地形配色与阴影；整体亮度乘 0.78；水深配色；非植被和卫星观测',
              'inputs_and_snapshots': copied}
    images = {}
    for file, legend, view in [(main_image, '黑：连通海洋边界；蓝：连通海洋；深灰：封闭负高程；浅灰：无效', broad),
                               (local_image, '黑：连通海洋边界；蓝：连通海洋；深灰：封闭负高程；浅灰：无效', local_window),
                               (change_image, '红：新出露；橙：连通海洋中净增厚 ≥ 0.01 m；深灰：封闭负高程；浅灰：无效', broad)]:
        images[file.name] = dict(common, sha256=digest(file), legend=legend, extent_pixel_edges_m=view[3], scale_bar_m=view[4],
                                 state_times_s=[s.time_s for s in states], created_utc=datetime.now(timezone.utc).isoformat())
    manifest = {'images': images, 'notes': '只读重绘；原始 TD 页摘要沿用来源清单，未重新读取全部大文件。'}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    (out / 'README.md').write_text(f'''# 海岸三角洲长期输沙

只读重绘已保存 MarineState，不重新求解。继承 growth-v3-stage10 原状态后继续 {meta['years_delivered']:g} 等效年，不含原状态前史。黑线为 0 m 时边界连通海洋的格网边界；封闭负高程另用深灰显示。水下沉积为连通海洋中相对原状态的净床面增厚，并非独立沉积通量。图中不绘制解析河道线。

源 TD 为 30 m，计算床面为 600 m；X 向东，Z 向南并在图中向下。地形配色不是植被。Q={scenario['discharge_m3_s']} m³/s、固体 {scenario['solid_rate_m3_s']} m³/s 为假定情景而非观测。长期等效年与状态物理秒数分别记录。广域窗口包含绝对床变至少 0.01 m 的有效格及边距；局部窗口为新增出露包围盒加约 3 km 上下文，显示原始 600 m 网格。

逐图来源、时间、情景、图例、坐标、比例尺、哈希和 TD 来源绑定见 manifest.json。快照保留 checkpoint、基础产品及必要实现，不复制 TD 页；其摘要来自原清单，未重新验证每页。
''', encoding='utf8')
    size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    if size >= 80 * 1024 * 1024:
        raise ValueError(f'出版目录超过 80 MiB：{size} 字节；保留文件供检查')
    print(f'{out} ({size} bytes)')


if __name__ == '__main__':
    main()
