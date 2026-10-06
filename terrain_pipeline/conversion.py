"""Lossless geometry conversion after explicit Minecraft vertical remapping."""
import numpy as np

def height_to_vdm(elevation,meters_per_block=30):
    if not np.isfinite(meters_per_block) or meters_per_block<=0:raise ValueError('Positive vertical scale required')
    elevation=np.asarray(elevation,dtype=np.float32)
    if elevation.ndim!=2 or not np.isfinite(elevation).all():raise ValueError('Expected finite elevation grid')
    offset=elevation/meters_per_block
    offset=np.where(offset>=0,225*np.tanh(offset/225),125*np.tanh(offset/125))
    vectors=np.zeros((3,*elevation.shape),dtype=np.float32)
    vectors[1]=offset
    return vectors
