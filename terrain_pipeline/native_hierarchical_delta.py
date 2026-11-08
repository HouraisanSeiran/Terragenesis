"""Finite hierarchical kinematic routing for a constructed delta tree."""
import numpy as np


def route_tree(water_m3,solid_m3,duration_s,parents,length_m,width_m,depth_m,eligible_masks,cell_area_m2,*,settling_velocity=1e-4,porosity=.35):
    water,solid,dt=(np.asarray(x,float) for x in (water_m3,solid_m3,duration_s))
    parent=np.asarray(parents,int);length,width,depth=(np.asarray(x,float) for x in (length_m,width_m,depth_m)); masks=np.asarray(eligible_masks)
    n=len(parent)
    if (n<1 or parent[0]!=-1 or np.any(parent[1:]<0) or np.any(parent[1:]>=np.arange(1,n)) or
        any(x.shape!=(n,) for x in (length,width,depth)) or masks.ndim!=3 or masks.shape[0]!=n or masks.dtype.kind!='b' or
        water.ndim!=1 or solid.shape!=water.shape or dt.shape!=water.shape or np.any(water<0) or np.any(solid<0) or
        np.any(dt<=0) or np.any(length<=0) or np.any(width<=0) or np.any(depth<=0) or cell_area_m2<=0 or not 0<=porosity<1 or
        not all(np.isfinite(x).all() for x in (water,solid,dt,length,width,depth))): raise ValueError('invalid tree or forcing')
    if np.any((water==0)&(solid>0)):raise ValueError('zero water requires explicit sediment escrow')
    iw=np.zeros((len(water),n));isolid=np.zeros_like(iw);deposit=np.zeros_like(iw);outsolid=np.zeros_like(iw);store=np.zeros(masks.shape[1:]);iw[:,0]=water;isolid[:,0]=solid
    for j in range(n):
        children=np.flatnonzero(parent==j)
        for t in range(len(water)):
            if iw[t,j]>0 and masks[j].any():
                velocity=iw[t,j]/dt[t]/(width[j]*depth[j]);fraction=-np.expm1(-settling_velocity*length[j]/(velocity*depth[j]));deposit[t,j]=isolid[t,j]*fraction;store[masks[j]]+=deposit[t,j]/masks[j].sum()
            outsolid[t,j]=isolid[t,j]-deposit[t,j]
            if len(children):
                share=width[children]/width[children].sum();iw[t,children]+=iw[t,j]*share;isolid[t,children]+=outsolid[t,j]*share
    leaves=np.array([j for j in range(n) if not np.any(parent==j)],int)
    if not np.allclose(iw[:,leaves].sum(axis=1),water) or not np.isclose(store.sum()+outsolid[:,leaves].sum(),solid.sum()): raise ArithmeticError('tree budget failure')
    return dict(edge_water_m3=iw,edge_solid_in_m3=isolid,edge_deposited_solid_m3=deposit,edge_solid_out_m3=outsolid,stored_solid_m3=store,height_delta_m=store/(cell_area_m2*(1-porosity)),leaf_indices=leaves)
