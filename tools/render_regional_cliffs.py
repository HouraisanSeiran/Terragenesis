"""Render actual Java patch meshes before/after erosion with identical cameras."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'preview/regional-cliffs'
data=np.genfromtxt(out/'surfaces.csv',delimiter=',',names=True,dtype=None,encoding='utf-8')
fig=plt.figure(figsize=(14,10),facecolor='#20262c')
names=['76 deg slope (256, 256)','90 deg wall (512, 0)','68 deg overhang (0, 512)']
for site in range(3):
    rows=data[data['site']==site]
    for col,stage in enumerate(['rock','eroded']):
        points=rows[rows['stage']==stage]
        ax=fig.add_subplot(3,2,site*2+col+1,projection='3d',facecolor='#20262c')
        x=points['x'].reshape(81,161);y=points['y'].reshape(81,161);z=points['z'].reshape(81,161)
        ax.plot_surface(x,z,y,rcount=81,ccount=161,color='#b9ae93',linewidth=0,antialiased=False)
        ax.set_zlim(rows['y'].min()-3,rows['y'].max()+3)
        ax.set_box_aspect((2,2,1),zoom=1.5);ax.view_init(elev=24,azim=-60)
        ax.set_title(names[site]+' / '+stage,color='white',fontsize=11)
        ax.set_axis_off()
fig.suptitle('Actual Java VDM meshes / before and after surface runoff',color='white',fontsize=15)
fig.subplots_adjust(top=.92,bottom=.02,left=.01,right=.99,wspace=0,hspace=0)
fig.savefig(out/'comparison.png',dpi=135,facecolor=fig.get_facecolor());plt.close(fig)
print(out/'comparison.png')
