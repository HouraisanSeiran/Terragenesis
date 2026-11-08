"""Render review plots from an existing upstream sediment case."""
from pathlib import Path
import json
import numpy as np

def render(case):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    case=Path(case); u=np.load(case/'upstream.npz'); g=np.load(case/'geometry.npz'); m=np.load(case/'mouth.npz')
    q=u['q_m3_s']; qs=u['terminal_export_m3']/86400.; days=np.arange(q.size)
    fig,ax=plt.subplots(figsize=(10,4)); ax.plot(days,q,label='Q (m3/s)'); ax2=ax.twinx(); ax2.plot(days,qs,label='Qs terminal (m3/s)',color='tab:red'); ax.set_xlabel('day'); ax.set_ylabel('water'); ax2.set_ylabel('solid'); fig.tight_layout(); fig.savefig(case/'daily_q_qs.png',dpi=130); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4)); dist=np.r_[0,np.cumsum(g['length_m'][1:])]; ax.plot(dist,g['hardness'],label='hardness'); ax.set_xlabel('distance (m)'); ax.set_ylabel('hardness'); ax2=ax.twinx(); ax2.plot(dist,g['slope'],color='tab:orange',label='slope'); ax2.set_ylabel('slope'); fig.tight_layout(); fig.savefig(case/'along_reach_budget.png',dpi=130); plt.close(fig)
    fig,ax=plt.subplots(figsize=(6,5)); im=ax.imshow(m['height_delta_m'],cmap='RdBu_r'); fig.colorbar(im,ax=ax,label='bed change (m)'); ax.set_title('Mouth bed change'); fig.tight_layout(); fig.savefig(case/'mouth_bed_change.png',dpi=130); plt.close(fig)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('case',type=Path); render(p.parse_args().case)
