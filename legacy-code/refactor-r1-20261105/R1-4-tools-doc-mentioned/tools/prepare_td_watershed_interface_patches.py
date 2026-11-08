"""Prepare task07B by invoking the core saved-interface patch algorithm."""
from __future__ import annotations
import argparse, hashlib, json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_watershed_interface_patches import build_watershed_interface_patches, save_watershed_interface_patches, validate_watershed_interface_patches

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def prepare(source: Path, destination: Path):
    started=time.time()
    if destination.exists(): raise FileExistsError(destination)
    destination.mkdir(parents=True)
    source_index_path=source/'index.json'; source_index=json.loads(source_index_path.read_text(encoding='utf-8'))
    if source_index.get('status') not in {'ready_for_independent_audit','accepted'}: raise ValueError('06 package is not frozen')
    paths_path=source/source_index['paths']['path']; sections_path=source/source_index['sections']['path']; review_path=source/source_index['review']['path']
    for key,path in (('paths',paths_path),('sections',sections_path),('review',review_path)):
        if sha256(path)!=source_index[key]['sha256']: raise ValueError('06 '+key+' pin mismatch')
    paths=json.loads(paths_path.read_text(encoding='utf-8')); sections=json.loads(sections_path.read_text(encoding='utf-8'))
    core_result=build_watershed_interface_patches(paths,sections)
    validate_watershed_interface_patches(core_result)
    patch_path=save_watershed_interface_patches(core_result,destination/'patches.json')
    review={
        'schema':'td-watershed-interface-patch-review-v2','source_06_index_sha256':sha256(source_index_path),
        'source_artifacts':{'paths':sha256(paths_path),'sections':sha256(sections_path),'review':sha256(review_path)},
        'core_schema':core_result['schema'],'core_algorithm':core_result['algorithm'],
        'core_identity_sha256':core_result['identity_sha256'],'core_shape_identity_sha256':core_result['shape_identity_sha256'],
        'summary':core_result['summary'],'rejection_reasons':{reason:sum(reason in p['rejection_reasons'] for p in core_result['patches']) for p in core_result['patches'] for reason in p['rejection_reasons']},
        'parametric_only':core_result['parametric_only'],'source_bed_unchanged':core_result['source_bed_unchanged'],'candidate_semantics':core_result['candidate_semantics'],
    }
    review['identity_sha256']=digest(review); review_path_out=destination/'review.json'; review_path_out.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    index={'schema':'td-watershed-interface-patch-preparation-v2','status':'ready_for_independent_audit','source_06_index_sha256':sha256(source_index_path),
           'source_artifacts':review['source_artifacts'],'core':{'schema':core_result['schema'],'algorithm':core_result['algorithm'],'identity_sha256':core_result['identity_sha256'],'shape_identity_sha256':core_result['shape_identity_sha256']},
           'patches':{'path':'patches.json','sha256':sha256(patch_path),'bytes':patch_path.stat().st_size},'review':{'path':'review.json','sha256':sha256(review_path_out),'bytes':review_path_out.stat().st_size},
           'summary':core_result['summary'],'resource':{'elapsed_s':time.time()-started,'water_solves':0,'forest_rebuilds':0},
           'false_flags':{key:core_result[key] for key in ('bed_changed','bed_rasterized','water_surface_meshed','hydraulic_solved','natural_outlet_certified','flow_regime_certified','publish_ready')}}
    index['identity_sha256']=digest(index); (destination/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8'); return index
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',type=Path,required=True); ap.add_argument('--destination',type=Path,required=True); print(json.dumps(prepare(ap.parse_args().source,ap.parse_args().destination),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
