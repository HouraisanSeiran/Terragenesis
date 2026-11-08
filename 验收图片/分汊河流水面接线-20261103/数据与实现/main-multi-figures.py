"""Read-only terrain-map views, using the existing cartographic style."""
from pathlib import Path
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_marine_sediment import classify_ocean
from matplotlib.colors import LinearSegmentedColormap, Normalize
from terrain_pipeline.terrain_map_style import LAND_COLORS, ocean_colormap, apply_hillshade

parser = argparse.ArgumentParser()
parser.add_argument('--prefix', default='multi-branch-v2')
parser.add_argument('--stage')
parser.add_argument('--source', default='growth-v3-stage10')
args = parser.parse_args()
p = Path(__file__).parent
source, source_progress = load_checkpoint(p/args.source)
formed, progress = load_checkpoint(p/(args.stage or args.prefix+'-stage'))
event, event_progress = load_checkpoint(p/(args.prefix+'-event'))
plt.rcParams['font.family'] = 'Microsoft YaHei'
plt.rcParams['axes.unicode_minus'] = False
cells = np.array([c for route in progress['routes'] for c in route])
lo = np.maximum(cells.min(axis=0)-8, 0)
hi = np.minimum(cells.max(axis=0)+9, np.array(source.bed_m.shape))
sl = np.s_[lo[0]:hi[0], lo[1]:hi[1]]
spacing = source.spacing_m
ox, oz = source.origin_xz_m
extent = [(ox+lo[1]*spacing)/1000, (ox+hi[1]*spacing)/1000,
          (oz+hi[0]*spacing)/1000, (oz+lo[0]*spacing)/1000]

def xy(route):
    a = np.array(route)
    return (ox+(a[:,1]+.5)*spacing)/1000, (oz+(a[:,0]+.5)*spacing)/1000

def terrain(ax, state, title):
    ocean, _ = classify_ocean(state, 0.)
    rgb = LinearSegmentedColormap.from_list('existing-land', LAND_COLORS)(Normalize(0.,500.,clip=True)(state.bed_m))[...,:3]
    rgb[ocean] = ocean_colormap()(Normalize(0.,35.,clip=True)(-state.bed_m[ocean]))[...,:3]
    rgb = apply_hillshade(rgb, state.bed_m, spacing)
    rgb[~state.valid_mask] = .8
    ax.imshow(rgb[sl], extent=extent, origin='upper', interpolation='nearest')
    bed = state.bed_m[sl]
    xs = (ox+(np.arange(lo[1],hi[1])+.5)*spacing)/1000
    zs = (oz+(np.arange(lo[0],hi[0])+.5)*spacing)/1000
    ax.contour(xs, zs, bed, levels=[0.], colors='#55482c', linewidths=.6)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('X 向东（km）'); ax.set_ylabel('Z 向南（km）')
    ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:])
    x, z = extent[0]+1.5, extent[2]-1.5
    ax.plot([x,x+5], [z,z], color='black', lw=2)
    ax.text(x,z-.4,'5 km', fontsize=9)

fig, axes = plt.subplots(1,3, figsize=(17,7), constrained_layout=True)
terrain(axes[0], source, '同源起始床面（继承已有三路）' if args.source=='growth-v3-stage10' else '继承1年及首事件后的床面（已有五路）')
terrain(axes[1], formed, f"{progress['years']:g} 等效年：{sum(progress.get('active',[True]*len(progress['routes'])))} 路活动")
terrain(axes[2], event, f"25 小时潮浪后：{sum(event_progress.get('active',[True]*len(event_progress['routes'])))} 路活动")
plot_states=list(zip(axes[1:], (formed,event), (progress,event_progress)))
if args.source!='growth-v3-stage10':
    plot_states.insert(0,(axes[0],source,source_progress))
for ax, state, shown_progress in plot_states:
    for index, route in enumerate(shown_progress['routes']):
        x,z = xy(route); color = '#e357b7' if index>=3 else '#0068ba'
        active=shown_progress.get('active',[True]*len(shown_progress['routes']))[index]
        if not active:
            color='#9e4a31'
        ax.plot(x,z, color=color, lw=1.,ls='-' if active else '--')
        ax.scatter(x[-1],z[-1], color=color, s=16, zorder=4)
        ax.annotate(str(index+1), (x[-1],z[-1]), xytext=(4,4), textcoords='offset points', fontsize=9)
    for h in shown_progress['history']:
        if h.get('event') != 'split':
            continue
        x,z = xy([h['proposal']['path'][0]])
        ax.scatter(x,z, s=45, facecolors='none', edgecolors='#bd3c00', lw=1.4, zorder=5)
fig.legend(handles=[Line2D([0],[0],color='#0068ba',label='原三路'),
                    Line2D([0],[0],color='#e357b7',label='本轮新增路线'),
                    Line2D([0],[0],marker='o',ls='',mfc='none',mec='#bd3c00',label='新增分叉位置'),
                    Line2D([0],[0],color='#9e4a31',ls='--',label='关闭的历史路线')],
           loc='outside lower center', ncol=4)
headline = ('遥感式合成影像／地形配色：同源 TD＋共同床面＋分汊＋水沙潮浪\n'
            'TD 原生 30 m，计算 600 m；线为保存路线，线宽不代表真实河宽；Q=3000 m³/s、固体=1.6 m³/s 为情景')
if 'river_hydraulics' in event_progress:
    h = event_progress['river_hydraulics']
    headline = ('同源 TD＋河床＋分汊河流水面＋潮浪；地形配色，海岸底色按平均海位\n'
                f"TD 原生30 m／计算600 m；输入3000 m³/s，末态仅接收{h['accepted_q_m3_s']:.1f} m³/s；"
                f"假定上游水位上限{h['parameters']['upstream_stage_limit_m']:g} m；线宽不代表真实河宽")
fig.suptitle(headline, fontsize=12)
fig.savefig(p/(args.prefix+'-main-map.png'), dpi=145)
plt.close(fig)

fig, ax = plt.subplots(figsize=(9,8), constrained_layout=True)
change = event.bed_m-formed.bed_m
im = ax.imshow(change[sl], extent=extent, origin='upper', cmap='RdBu_r', vmin=-.5, vmax=.5, interpolation='nearest')
for route in progress['routes']:
    ax.plot(*xy(route), color='black', lw=.6)
ax.set_xlabel('X 向东（km）'); ax.set_ylabel('Z 向南（km）')
ax.set_title('25 小时共同床面变化（m）；黑线为保存路线')
fig.colorbar(im, ax=ax, label='事件后床面 − 事件前床面（m）', extend='both')
fig.savefig(p/(args.prefix+'-event-change.png'), dpi=145)
plt.close(fig)
print(p/(args.prefix+'-main-map.png'))
