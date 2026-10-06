"""Install a pinned upstream checkout, isolated runtime and model inside this workspace."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, zipfile
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
REVISION='e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230'
def setup():
    runtime=ROOT/'runtime'; runtime.mkdir(exist_ok=True)
    for name in ['tmp','pip-cache','hf','torch','numba','mpl']:(runtime/name).mkdir(exist_ok=True)
    os.environ.update(TMP=str(runtime/'tmp'),TEMP=str(runtime/'tmp'),PIP_CACHE_DIR=str(runtime/'pip-cache'),
        HF_HOME=str(runtime/'hf'),TORCH_HOME=str(runtime/'torch'),NUMBA_CACHE_DIR=str(runtime/'numba'),MPLCONFIGDIR=str(runtime/'mpl'),PYTHONDONTWRITEBYTECODE='1')
    archive=runtime/'terrain-diffusion.zip'
    source=ROOT/'vendor'/('terrain-diffusion-'+REVISION)
    if not (source/'inference-files.json').exists():
        if not (runtime/'upstream-tree.json').exists():
            subprocess.run(['curl.exe','-L','--fail','-sS','--retry','2',
                f'https://api.github.com/repos/xandergos/terrain-diffusion/git/trees/{REVISION}?recursive=1',
                '-o',str(runtime/'upstream-tree.json')],check=True)
        tree=json.loads((runtime/'upstream-tree.json').read_text())
        prefixes=('terrain_diffusion/models/','terrain_diffusion/scheduler/','terrain_diffusion/common/')
        paths=[e['path'] for e in tree['tree'] if e['type']=='blob' and (
            e['path'] in ('LICENSE','README.md','terrain_diffusion/data/laplacian_encoder.py') or
            (e['path'].endswith('.py') and (e['path'].startswith(prefixes) or
            (e['path'].startswith('terrain_diffusion/inference/') and e['path'].count('/')==2))))]
        def fetch(name):
            dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():return
            part=dest.with_suffix(dest.suffix+'.part')
            subprocess.run(['curl.exe','-L','--fail','-sS','--retry','2','--max-time','60','-H',
                'Accept: application/vnd.github.raw+json',f'https://api.github.com/repos/xandergos/terrain-diffusion/contents/{name}?ref={REVISION}',
                '-o',str(part)],check=True)
            part.replace(dest)
        with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(fetch,paths))
        (source/'inference-files.json').write_text(json.dumps(paths,indent=2))
    python=runtime/'venv/Scripts/python.exe'
    if not python.exists():subprocess.run([sys.executable,'-m','venv',str(runtime/'venv')],check=True)
    def pip(*args):subprocess.run([str(python),'-m','pip','--disable-pip-version-check',*args],check=True,env=os.environ)
    pip('install','torch==2.9.1','torchvision==0.24.1','--index-url','https://download.pytorch.org/whl/cu126')
    pip('install','diffusers==0.35.2','h5py','infinite-tensor>=0.3.0','numpy','scipy','matplotlib','scikit-image',
        'numba','pyfastnoiselite==0.0.6','safetensors','huggingface_hub<1.0','einops','tqdm','easydict','click','pillow','rasterio','ema-pytorch')
    (runtime/'upstream.json').write_text(json.dumps({'repository':'https://github.com/xandergos/terrain-diffusion',
        'revision':REVISION,'source':str(source.relative_to(ROOT)),'inference_files':json.loads((source/'inference-files.json').read_text())},indent=2))
    with (runtime/'requirements-lock.txt').open('w',encoding='utf-8') as lock:
        subprocess.run([str(python),'-m','pip','freeze'],stdout=lock,check=True)
    print('Runtime ready:',python,flush=True)
if __name__=='__main__':setup()
