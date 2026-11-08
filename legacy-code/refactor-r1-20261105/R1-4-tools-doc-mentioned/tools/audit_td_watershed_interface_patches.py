"""Independent cold audit of the core 07B record."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_watershed_interface_patches import SCHEMA,load_watershed_interface_patches,validate_watershed_interface_patches
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def digest(v): return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def audit(directory):
 directory=Path(directory); idx=json.loads((directory/'index.json').read_text(encoding='utf-8')); errors=[]; checks=[]
 patch_path=directory/idx['patches']['path']; review_path=directory/idx['review']['path']
 for name,path,expected in (('patches',patch_path,idx['patches']['sha256']),('review',review_path,idx['review']['sha256'])):
  ok=sha256(path)==expected; checks.append({'check':name+'_pin','passed':ok}); errors += [] if ok else [name+' pin mismatch']
 record=load_watershed_interface_patches(patch_path,expected_sha256=idx['patches']['sha256'],expected_identity=idx['core']['identity_sha256'])
 ok=record['schema']==SCHEMA and record['shape_identity_sha256']==idx['core']['shape_identity_sha256']; checks.append({'check':'core_schema_shape_identity','passed':ok}); errors += [] if ok else ['core schema/shape identity mismatch']
 ok=record['identity_sha256']==idx['core']['identity_sha256']; checks.append({'check':'core_identity','passed':ok}); errors += [] if ok else ['core identity mismatch']
 flags=('bed_changed','bed_rasterized','water_surface_meshed','hydraulic_solved','natural_outlet_certified','flow_regime_certified','publish_ready')
 ok=all(record[k] is False for k in flags) and record['parametric_only'] is True and record['source_bed_unchanged'] is True; checks.append({'check':'false_flags_and_semantics','passed':ok}); errors += [] if ok else ['core flags/semantics invalid']
 expected=record['summary']; actual={'total':len(record['patches']),'candidate':sum(p['status']=='candidate' for p in record['patches']),'rejected':sum(p['status']=='rejected' for p in record['patches']),'by_kind':{kind:sum(p['kind']==kind for p in record['patches']) for kind in ('junction','lake_anchor_transition','corner_transition')}}
 ok=actual==expected; checks.append({'check':'core_summary_mesh_rejections','passed':ok}); errors += [] if ok else ['core summary mismatch']
 for p in record['patches']:
  if p['status']=='candidate' and (not p['triangles'] or p['rejection_reasons']): errors.append(p['patch_id']+' candidate mesh/rejection mismatch')
  if p['status']=='rejected' and p['triangles']: errors.append(p['patch_id']+' rejected patch has triangles')
 review=json.loads(review_path.read_text(encoding='utf-8')); ok=review['source_artifacts']==idx['source_artifacts'] and review['core_identity_sha256']==record['identity_sha256']; checks.append({'check':'parent_pins_and_review_core_identity','passed':ok}); errors += [] if ok else ['review parent/core pin mismatch']
 result={'schema':'td-watershed-interface-patch-independent-audit-v2','status':'passed' if not errors else 'failed','checks':checks,'errors':errors,'core_schema':record['schema'],'core_identity_sha256':record['identity_sha256'],'core_shape_identity_sha256':record['shape_identity_sha256'],'summary':record['summary'],'solver_calls':0,'forest_rebuilds':0,'water_solves':0}; result['identity_sha256']=digest(result); (directory/'independent-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); return result
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--directory',type=Path,required=True); print(json.dumps(audit(ap.parse_args().directory),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
