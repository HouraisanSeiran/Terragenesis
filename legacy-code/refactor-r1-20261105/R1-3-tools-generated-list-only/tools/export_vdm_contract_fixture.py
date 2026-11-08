"""Known XYZ values for cross-language format validation; not terrain generation."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from vdm_diffusion.export import export
export('verification/vdm-contract',np.arange(192,dtype=np.float32).reshape(3,8,8)-64,
       {'origin':[-8,0],'spacing':2,'reference':'world-x-y-z-plane72','source':'format fixture'})
