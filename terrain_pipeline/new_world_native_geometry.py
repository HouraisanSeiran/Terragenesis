"""Small geometry helpers for saved native-event window products."""
import numpy as np


def native_lake_wet(bed_m, pool_index, levels_m, ocean_mask, unknown_mask):
    """Classify wet control cells from actual pool level; NaN means dry."""
    bed=np.asarray(bed_m,float); pool=np.asarray(pool_index); levels=np.asarray(levels_m,float)
    ocean=np.asarray(ocean_mask);unknown=np.asarray(unknown_mask)
    if (bed.ndim!=2 or pool.shape!=bed.shape or ocean.shape!=bed.shape or unknown.shape!=bed.shape
            or pool.dtype.kind not in 'iu' or ocean.dtype.kind!='b' or unknown.dtype.kind!='b'
            or levels.ndim!=1 or not np.isfinite(bed).all() or np.any(pool < -1)
            or np.any(pool >= len(levels))):
        raise ValueError('invalid lake inputs')
    valid=pool>=0; result=np.zeros(bed.shape,bool)
    result[valid]=np.isfinite(levels[pool[valid]]) & (bed[valid]<levels[pool[valid]])
    return result & ~ocean & ~unknown
