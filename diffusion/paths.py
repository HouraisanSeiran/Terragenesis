"""Keep runtime, model and derived artifacts under the project root."""
from pathlib import Path
import os
import tempfile

ROOT=Path(os.environ.get('REMOTEMOUNTAINS_DIFFUSION_HOME', Path(__file__).resolve().parents[1])).resolve()
def configure():
    locations={'HF_HOME':'runtime/hf','TORCH_HOME':'runtime/torch','NUMBA_CACHE_DIR':'runtime/numba',
        'MPLCONFIGDIR':'runtime/mpl','PIP_CACHE_DIR':'runtime/pip-cache','TEMP':'runtime/tmp','TMP':'runtime/tmp',
        'TORCHINDUCTOR_CACHE_DIR':'runtime/inductor','TRITON_CACHE_DIR':'runtime/triton'}
    for variable,relative in locations.items():
        folder=ROOT/relative;folder.mkdir(parents=True,exist_ok=True);os.environ[variable]=str(folder)
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    tempfile.tempdir=str(ROOT/'runtime/tmp')

def inside(relative):
    path=(ROOT/relative).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Artifact path must stay inside workspace')
    return path
