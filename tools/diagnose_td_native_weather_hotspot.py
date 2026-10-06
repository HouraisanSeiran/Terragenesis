"""Read-only weather refinement hotspot attribution; never advances a solver."""
from pathlib import Path
import json,argparse
import numpy as np
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from terrain_pipeline.mountain_source_adapter import load_bundle

def load_saved(pin):
    return load_bundle(pin["path"],expected_sha256=pin["expected_sha256"],validator=lambda value: True,max_bytes=512*1024*1024)

def diagnose(run,cell=60279):
    run=Path(run); out=[]
    coarse=[];fine=[]
    for step,target in ((2.5,coarse),(1.25,fine)):
        for hour in range(24):
            report=json.loads((run/f"eastward-{step:g}s"/f"hour-{hour:02d}"/"report.json").read_text(encoding="utf8"))
            saved=load_saved(report["storage"]); arrays=saved["arrays"]
            rain=arrays["rain_mm_h"][0,cell]
            wet=bool(arrays["depth_m"][0,cell]>1e-9)
            faces=arrays["face_cells"]
            selected=np.flatnonzero((faces[:,0]==cell)|(faces[:,1]==cell))
            target.append({"hour":hour,"rain_mm_h":float(rain),"wet_at_start":wet,
                "depth_start_m":float(arrays["depth_m"][0,cell]),"depth_end_m":float(arrays["depth_m"][-1,cell]),
                "soil_start_mm":float(arrays["soil_mm"][0,cell]),"soil_end_mm":float(arrays["soil_mm"][-1,cell]),
                "fast_start_mm":float(arrays["fast_mm"][0,cell]),"fast_end_mm":float(arrays["fast_mm"][-1,cell]),
                "slow_start_mm":float(arrays["slow_mm"][0,cell]),"slow_end_mm":float(arrays["slow_mm"][-1,cell]),
                "face_count":int(len(selected)),"face_forward_m3":float(arrays["face_forward_m3"][selected].sum()),
                "face_reverse_m3":float(arrays["face_reverse_m3"][selected].sum()),"routed_m3":float(arrays["routed_volume_m3"][cell]),"wet_duration_s":float(arrays["wet_duration_s"][cell])})
    deltas=[]
    for coarse_row,fine_row in zip(coarse,fine):
        deltas.append({key:fine_row[key]-coarse_row[key] for key in ("depth_end_m","soil_end_mm","fast_end_mm","slow_end_mm","face_forward_m3","face_reverse_m3","routed_m3","wet_duration_s")}|{"hour":coarse_row["hour"]})
    report={"schema":"td-weather-hotspot-attribution-v1","scope":"saved eastward pages only; read-only no solver advance","cell":cell,"coarse_step_s":2.5,"fine_step_s":1.25,"coarse":coarse,"fine":fine,"fine_minus_coarse":deltas}
    destination=run/"eastward-hotspot-attribution.json";publish_bytes(destination,json.dumps(report,indent=2,allow_nan=False).encode())
    return destination

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--run",required=True);parser.add_argument("--cell",type=int,default=60279);a=parser.parse_args();p=diagnose(a.run,a.cell);print(json.dumps({"path":str(p),"sha256":file_sha256(p)}))
