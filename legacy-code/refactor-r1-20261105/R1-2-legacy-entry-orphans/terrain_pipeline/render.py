"""Render actual displaced geometry, with identical camera and scale for comparisons."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

def render_comparison(folder,base,sculpted,spacing):
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    n=base.shape[1];zz,xx=np.mgrid[:n,:n]*spacing
    fig=plt.figure(figsize=(17,8),facecolor='#101a22')
    zmin=min(base[1].min(),sculpted[1].min())+72-5
    zmax=max(base[1].max(),sculpted[1].max())+72+5
    for i,(vectors,title) in enumerate([(base,'Terrain Diffusion · 基础地形'),(sculpted,'基础地形 → VDM → 局部悬崖')]):
        ax=fig.add_subplot(1,2,i+1,projection='3d',facecolor='#101a22')
        y=72+vectors[1];dz,dx=np.gradient(y,spacing)
        slope=np.hypot(dx,dz)
        rgb=np.empty((*y.shape,3));rgb[:]=[.34,.46,.25]
        rock=np.clip((slope-.4)/1.5,0,1)[:,:,None]
        rgb=rgb*(1-rock)+np.array([.57,.54,.48])*rock
        colors=LightSource(azdeg=310,altdeg=40).shade_rgb(rgb,y,vert_exag=1,dx=spacing,dy=spacing,blend_mode='soft')
        ax.plot_surface(xx+vectors[0],zz+vectors[2],y,facecolors=colors,rcount=min(n,180),ccount=min(n,180),linewidth=0,antialiased=True,shade=False)
        ax.set(xlim=(0,(n-1)*spacing),ylim=(0,(n-1)*spacing),zlim=(zmin,zmax))
        ax.set_box_aspect(((n-1)*spacing,(n-1)*spacing,zmax-zmin));ax.view_init(36,-58)
        ax.set_axis_off();ax.set_title(title,color='white',fontsize=16,pad=10)
    fig.text(.5,.055,'同一模型输出、同一镜头与比例。右图只在局部遮罩内进行 VDM 塑形；不含洞穴。',ha='center',color='#c3d0d8',fontsize=11)
    fig.savefig(folder/'comparison.png',dpi=160,facecolor=fig.get_facecolor(),bbox_inches='tight');plt.close(fig)
