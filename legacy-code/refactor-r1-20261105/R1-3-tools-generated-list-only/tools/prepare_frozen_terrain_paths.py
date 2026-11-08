"""Complete frozen edges on the saved 38.4km genuine seed3 TD source."""
import argparse
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_hydrology_v5_lake import limit_resources
limit_resources()
import numpy as np
from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.frozen_terrain_centerline import prepare_frozen_edge_path
from terrain_pipeline.mountain_source_adapter import file_sha256

parser = argparse.ArgumentParser()
parser.add_argument("--select-only", action="store_true")
args = parser.parse_args()
base = ROOT / "verification/hydrological-planning-domain"
source_path = base / "large-td-preview-20261014-01/native-routing.npz"
with np.load(source_path, allow_pickle=False) as saved:
    height = saved["original_td_m"].copy()
    source_meta = json.loads(str(saved["metadata_json"].item()))
plan = load_plan(base / "multiseed-coarse-20261014-01/plan-seed3.npz")
origin = np.asarray(source_meta["origin_xz_m"])
spacing = float(source_meta["spacing_m"])
maximum = origin+(np.array(height.shape)[::-1]-1)*spacing
columns = plan["height_m"].shape[1]
receiver = plan["receiver"].ravel()
source_cells = np.flatnonzero(plan["river_mask"].ravel() & (receiver >= 0))
eligible, unsupported = [], []
for first in source_cells:
    edge = [int(first), int(receiver[first])]
    anchors = np.asarray(plan["origin_xz_m"])+plan["spacing_m"]*np.column_stack((np.asarray(edge)%columns,np.asarray(edge)//columns))
    if np.all(anchors >= origin) and np.all(anchors <= maximum):
        eligible.append(edge)
    elif np.all(np.maximum(anchors.min(axis=0),origin)<=np.minimum(anchors.max(axis=0),maximum)):
        unsupported.append(edge)
if args.select_only:
    print(json.dumps({"origin_xz_m":origin.tolist(),"shape":list(height.shape),"eligible_complete_edges":eligible,
                      "source_edge_fragments_refused":unsupported,"source_sha256":file_sha256(source_path)}),flush=True)
    sys.exit(0)
z,x = np.indices(height.shape)
coarse_x = np.rint((origin[0]+x*spacing-plan["origin_xz_m"][0])/plan["spacing_m"]).astype(int)
coarse_z = np.rint((origin[1]+z*spacing-plan["origin_xz_m"][1])/plan["spacing_m"]).astype(int)
owner = plan["owner_domain_id"][coarse_z,coarse_x]
protected = plan["ocean_mask"][coarse_z,coarse_x]
source_sha = file_sha256(source_path)
directory = base / "naturalness-20261014-03/seed3-frozen-terrain-paths"
directory.mkdir(parents=True,exist_ok=False)
records, existing = [], []
for edge in eligible:
    try:
        result = prepare_frozen_edge_path(plan,edge,height,origin,spacing,source_sha,
            owner_domain_id=owner,protected_mask=protected,existing_paths=existing)
        path = directory / (f"edge-{edge[0]}-{edge[1]}.npz")
        with path.open("xb") as stream:
            np.savez_compressed(stream,**result["arrays"],metadata_json=np.array(json.dumps(result["metadata"])),identity_sha256=np.array(result["identity"]))
        existing.append(result["arrays"]["points_xz_m"])
        records.append({"source_edge":edge,"status":"complete_candidate_path","path":str(path),
                        "sha256":file_sha256(path),"identity":result["identity"],"metadata":result["metadata"]})
    except ValueError as error:
        records.append({"source_edge":edge,"status":"rejected","reason":str(error)})
report = {"schema":"genuine-td-complete-frozen-edge-path-candidates-v1","source_path":str(source_path),
          "source_sha256":source_sha,"records":records,"source_edge_fragments_refused":unsupported,
          "bed_certified":False,"hydraulic_certified":False,"parameter_scan_run":False}
(directory / "report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report),flush=True)
