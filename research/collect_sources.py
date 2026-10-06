"""Read public research references. Save all responses and metadata inside research/."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess, json, hashlib, datetime

ROOT=Path(__file__).resolve().parent
SOURCES=[
 ('terrain-diffusion','repo','xandergos/terrain-diffusion'),
 ('terrain-minecraft','repo','xandergos/terrain-diffusion-mc'),
 ('text2vdm','repo','HengyuMeng/Text2VDM'),
 ('multidiffusion','repo','omerbt/MultiDiffusion'),
 ('controlnet','repo','lllyasviel/ControlNet'),
 ('ddim','repo','ermongroup/ddim'),
 ('dpm-solver','repo','LuChengTHU/dpm-solver'),
 ('edm','repo','NVlabs/edm'),
 ('latent-diffusion','repo','CompVis/latent-diffusion'),
 ('consistency-models','repo','openai/consistency_models'),
 ('neural-terrain','repo','novaia/ntg'),
 ('adaptive-diffusion-terrain','repo','youwyu/Adaptive-Diffusion-Terrain'),
 ('fastscape','repo','fastscape-lem/fastscape'),
 ('fastscapelib','repo','fastscape-lem/fastscapelib'),
 ('landlab','repo','landlab/landlab'),
 ('richdem','repo','r-barnes/richdem'),
 ('whitebox','repo','jblindsay/whitebox-tools'),
 ('pysheds','repo','mdbartos/pysheds'),
 ('gpu-erosion','repo','bshishov/UnityTerrainErosionGPU'),
 ('particle-erosion','repo','weigert/SimpleErosion'),
 ('soil-machine','repo','weigert/SoilMachine'),
 ('hydrology-terrain','repo','bmelaiths/terrainHydrology'),
 ('delta-rcm','repo','DeltaRCM/pyDeltaRCM'),
 ('badlands','repo','badlands-model/badlands'),
 ('fastnoise','repo','Auburn/FastNoiseLite'),
 ('libigl','repo','libigl/libigl'),
 ('geometry-central','repo','nmwsharp/geometry-central'),
 ('openvdb','repo','AcademySoftwareFoundation/openvdb'),
 ('deep-sdf','repo','facebookresearch/DeepSDF'),
 ('trellis','repo','microsoft/TRELLIS'),
 ('terrain-training','url','https://api.github.com/repos/xandergos/terrain-diffusion/contents/TRAINING.md'),
 ('terrain-api','url','https://api.github.com/repos/xandergos/terrain-diffusion/contents/API_README.md'),
 ('curl-noise','url','https://graphics.pixar.com/library/CurlNoise/paper.pdf'),
 ('improved-perlin','url','https://cs.nyu.edu/~perlin/paper445.pdf'),
 ('iq-derivatives','url','https://iquilezles.org/articles/derivative/'),
 ('iq-distance','url','https://iquilezles.org/articles/distfunctions/'),
 ('scipy-sparse','url','https://docs.scipy.org/doc/scipy/reference/sparse.linalg.html'),
 ('scipy-morphology','url','https://docs.scipy.org/doc/scipy/reference/ndimage.html'),
 ('copernicus-dem','url','https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM'),
 ('usgs-3dep','url','https://www.usgs.gov/3d-elevation-program'),
 ('terrain-api-code','url','https://api.github.com/repos/xandergos/terrain-diffusion/contents/terrain_diffusion/inference/api.py'),
 ('terrain-pipeline-code','url','https://api.github.com/repos/xandergos/terrain-diffusion/contents/terrain_diffusion/inference/world_pipeline.py'),
 ('meanderpy','repo','zsylvester/meanderpy'),
 ('gudhi','repo','GUDHI/gudhi-devel'),
 ('scikit-fmm','repo','scikit-fmm/scikit-fmm'),
 ('pot','repo','PythonOT/POT'),
 ('gstools','repo','GeoStat-Framework/GSTools'),
 ('diffusion-posterior','repo','DPS2022/diffusion-posterior-sampling'),
 ('space-paper','url','https://gmd.copernicus.org/articles/10/4577/2017/'),
 ('priority-flood-paper','url','https://arxiv.org/abs/1511.04463'),
 ('hydrology-paper','url','https://api.crossref.org/works/10.1145/2461912.2461996'),
 ('karst-paper','url','https://api.crossref.org/works/10.1016/j.cag.2021.10.002'),
 ('orographic-paper','url','https://api.crossref.org/works?query.title=A%20Linear%20Theory%20of%20Orographic%20Precipitation&rows=2&select=title,DOI,URL'),
]

def fetch(item):
    ident,kind,target=item
    url='https://api.github.com/repos/'+target+'/readme' if kind=='repo' else target
    folder=ROOT/'sources';folder.mkdir(exist_ok=True)
    suffix='.pdf' if url.endswith('.pdf') else '.txt'
    path=folder/(ident+suffix)
    previous_path=ROOT/'sources.json'
    if previous_path.exists():
        old=next((r for r in json.loads(previous_path.read_text(encoding='utf-8')) if r['id']==ident),None)
        if old and old.get('http_status')=='200' and path.exists():return old
    cmd=['curl.exe','-L','--retry','1','--max-time','35','-sS','-H','Accept: application/vnd.github.raw+json','-o',str(path),'-w','%{http_code}',url]
    result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    entry={'id':ident,'url':'https://github.com/'+target if kind=='repo' else url,
           'retrieved_url':url,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'http_status':result.stdout,'exit_code':result.returncode,'local_file':str(path.relative_to(ROOT))}
    if path.exists():
        data=path.read_bytes();entry['bytes']=len(data);entry['sha256']=hashlib.sha256(data).hexdigest()
    if result.stderr:entry['error']=result.stderr.strip()
    return entry

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(fetch,SOURCES))
    (ROOT/'sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:print(r['id'],r['http_status'],r.get('bytes',0),r.get('error',''))
