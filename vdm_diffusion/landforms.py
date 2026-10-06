"""Special geometry operators act after diffusion and only through explicit masks."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class CliffSettings:
    center:tuple
    normal:tuple
    height:float=24.0
    transition:float=12.0
    overhang:float=3.0
    def __post_init__(self):
        values=(*self.center,*self.normal,self.height,self.transition,self.overhang)
        if not np.isfinite(values).all() or self.transition<=0 or np.hypot(*self.normal)<1e-8:
            raise ValueError('Invalid cliff settings')

class CliffOperator:
    """Fault scarp profile plus bounded lip displacement, in world coordinates."""
    def __init__(self,settings):self.settings=settings
    def apply(self,vectors,metadata,mask):
        mask=np.asarray(mask,dtype=np.float32)
        if mask.shape!=vectors.shape[1:] or not np.isfinite(mask).all() or (mask<0).any() or (mask>1).any():
            raise ValueError('Cliff mask must match VDM and lie in [0,1]')
        s=self.settings;h,w=mask.shape;zz,xx=np.mgrid[:h,:w]
        x=metadata['origin'][0]+xx*metadata['spacing']+vectors[0]
        z=metadata['origin'][1]+zz*metadata['spacing']+vectors[2]
        normal=np.asarray(s.normal)/np.hypot(*s.normal)
        distance=(x-s.center[0])*normal[0]+(z-s.center[1])*normal[1]
        profile=np.tanh(distance/s.transition)
        lip=s.overhang*(1-profile*profile)*mask
        result=vectors.copy()
        result[0]+=normal[0]*lip;result[2]+=normal[1]*lip
        result[1]+=.5*s.height*profile*mask
        return result
