"""Download pinned public weights with content validation; no model files outside workspace."""
from pathlib import Path
import json,subprocess,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
MODEL='xandergos/terrain-diffusion-30m'
REV='9ef8030cb805b433b98ec25c5dddefbac07a9e26'
ENDPOINT=os.environ.get('REMOTE_MODEL_ENDPOINT','https://hf-mirror.com')
def download():
    target=ROOT/'models/terrain-diffusion-30m';target.mkdir(parents=True,exist_ok=True)
    files=['config.json','README.md']+[f'{stage}/{name}' for stage in ['coarse_model','base_model','decoder_model'] for name in ['config.json','diffusion_pytorch_model.safetensors']]
    manifest={'model':MODEL,'revision':REV,'endpoint':ENDPOINT,'files':{}}
    for name in files:
        path=target/name;path.parent.mkdir(exist_ok=True)
        if not path.exists():
            part=path.with_suffix(path.suffix+'.part')
            url=f'{ENDPOINT}/{MODEL}/resolve/{REV}/{name}'
            print('Downloading',name,flush=True)
            subprocess.run(['curl.exe','-L','--fail','--retry','4','--retry-delay','2','--connect-timeout','25','--max-time','1800','-C','-','-o',str(part),url],check=True)
            if name.endswith('.json'):json.loads(part.read_text())
            if name.endswith('.safetensors'):
                with part.open('rb') as f:
                    length=int.from_bytes(f.read(8),'little')
                    if not 0<length<10_000_000:raise RuntimeError('Invalid model weight header')
                    header=json.loads(f.read(length));expected=max(v['data_offsets'][1] for k,v in header.items() if k!='__metadata__')
                    if part.stat().st_size!=8+length+expected:raise RuntimeError('Incomplete model weight file')
            part.replace(path)
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest['files'][name]={'bytes':path.stat().st_size,'sha256':digest}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Pinned model complete',flush=True)
if __name__=='__main__':download()
