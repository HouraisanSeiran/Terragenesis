"""Saved terrain and actual active discharge; no new hydrology for drawing."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from terrain_pipeline.terrain_map_style import LAND_COLORS, ocean_colormap, apply_hillshade
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_marine_sediment import classify_ocean

p=Path(__file__).parent
before, bp=load_checkpoint(p/'multi-branch-v3-repaired-long')
after, ap=load_checkpoint(p/'active-routes-v1-event')
plt.rcParams['font.family']='Microsoft YaHei'
plt.rcParams['axes.unicode_minus']=False
fig,axes=plt.subplots(1,2,figsize=(13,7),constrained_layout=True)
spacing=before.spacing_m
ox,oz=before.origin_xz_m
extent=[ox/1000,(ox+before.bed_m.shape[1]*spacing)/1000,(oz+before.bed_m.shape[0]*spacing)/1000,oz/1000]
for ax,state,pr,title in zip(axes,(before,after),(bp,ap),('10年形成期：事件前','25小时后：堵塞支流关闭并重分配')):
    bed=state.bed_m;wet,_=classify_ocean(state,0.)
    rgb=LinearSegmentedColormap.from_list('land',LAND_COLORS)(Normalize(0,500,clip=True)(bed))[...,:3]
    rgb[wet]=ocean_colormap()(Normalize(0,35,clip=True)(-bed[wet]))[...,:3]
    rgb=apply_hillshade(rgb,bed,spacing);rgb[~state.valid_mask]=.8
    ax.imshow(rgb,extent=extent,origin='upper',interpolation='nearest')
    xs=(ox+(np.arange(bed.shape[1])+.5)*spacing)/1000
    zs=(oz+(np.arange(bed.shape[0])+.5)*spacing)/1000
    ax.contour(xs,zs,bed,levels=[0],colors='#4d4b37',linewidths=.5)
    route_shares=list(enumerate(zip(pr['routes'],pr.get('actual_shares',pr['shares']))))
    for i,(route,share) in sorted(route_shares,key=lambda item:item[1][1]>0):
        a=np.array(route);x=(ox+(a[:,1]+.5)*spacing)/1000;z=(oz+(a[:,0]+.5)*spacing)/1000
        color='#005ba3' if share>0 else '#a83d2a'
        ax.plot(x,z,color=color,lw=1.2,ls='-' if share>0 else '--')
        ax.scatter(x[-1],z[-1],s=14,color=color)
        ax.annotate(f'{i+1}: {share*pr["discharge_m3_s"]:.0f}',(x[-1],z[-1]),xytext=(4,4),textcoords='offset points',fontsize=8,color=color,
                    bbox={'facecolor':'white','alpha':.75,'edgecolor':'none','pad':1})
    ax.set_xlim(-16,21);ax.set_ylim(21,-11);ax.set_title(title)
    ax.set_xlabel('X 向东（km）');ax.set_ylabel('Z 向南（km）')
    ax.plot([-14,-9],[19,19],color='black',lw=2);ax.text(-14,18.5,'5 km')
fig.suptitle('同源TD遥感式合成影像／地形配色＋活动河网\n'
             '数字为河口实际分配流量（m³/s）；红虚线保留已关闭路线；计算600m，线宽非真实河宽\n'
             'Q=3000m³/s、固体1.6m³/s、潮幅1m、波高1.5m为情景',fontsize=11)
fig.savefig(p/'main-active-routes.png',dpi=145)
plt.close(fig)
print(p/'main-active-routes.png')
