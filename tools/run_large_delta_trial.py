"""CPU-bounded 128x128 native-30m delta trial using the live FV water-sediment solver."""
import argparse, hashlib, json, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, save, load

WORLD_SEED = 20261020
ORIGIN = (1374000.0, 1242000.0)
SPACING = 30.0
SHAPE = (128, 128)
PURPOSE = "large-delta-macro-bed-30m-v1"

def _microrelief(x, z):
    token = f"{WORLD_SEED}:{PURPOSE}:{float(x).hex()}:{float(z).hex()}".encode()
    return .02 * (2.0 * int.from_bytes(hashlib.sha256(token).digest()[:8], "little") / (2**64-1) - 1.0)

def initial_product(tide=False, perturb=False, max_wall_s=240.0):
    rows, cols = SHAPE
    rr, cc = np.indices(SHAPE)
    shoreline = 76
    bed = np.empty(SHAPE, float)
    ocean = cc < shoreline
    # Offshore shallow shelf (-1.0 m at boundary to -0.15 m at shoreline).
    bed[ocean] = -1.0 + 0.85 * cc[ocean] / (shoreline - 1)
    bed[~ocean] = 0.8
    # One broad, continuous upstream channel; no prescribed downstream branches.
    channel_half = 3.5 + 0.025 * (cc - shoreline).clip(0)
    channel = (~ocean) & (np.abs(rr - rows/2) <= channel_half)
    bed[channel] = -0.35 - 0.45 * ((cc[channel]-shoreline)/(cols-shoreline-1))
    if perturb:
        for r, c in zip(*np.nonzero(ocean)):
            bed[r, c] += _microrelief(ORIGIN[0]+c*SPACING, ORIGIN[1]+r*SPACING)
    floor = bed.copy(); floor[ocean] -= 0.60; floor[channel] = bed[channel] - 0.35
    inlet = [rows//2*cols + cols-2]
    cfg = FVDeltaConfig(coupling_interval_s=20.0, max_hydro_dt_s=4.0,
                        tide_amplitude_m=0.12 if tide else 0.0,
                        tide_period_s=43200.0, max_wall_s=max_wall_s)
    return initialize(bed, ocean, inlet, origin_m_xz=ORIGIN,
        source_world_identity=f"seed{WORLD_SEED}", source_identity=f"large-delta-trial-v1:{'tide' if tide else 'river'}:{'perturb' if perturb else 'flat'}",
        floor_m=floor, config=cfg)

def report(product, stage, path):
    a, m = product["arrays"], product["metadata"]; area = SPACING**2
    wet = a["depth_m"] > m["config"]["bedload"]["dry_depth_m"]
    delta = a["bed_m"] - a["initial_bed_m"]
    dt = m["last_coupling_interval_s"]
    water_res = float(a["depth_m"].sum()*area + m["ledger"]["water_export_m3"] - m["initial_water_m3"] - m["ledger"]["water_input_m3"] - m["ledger"]["sea_import_m3"])
    solid_res = float(((a["bed_m"]-a["floor_m"])*area*(1-m["config"]["bedload"]["porosity"])).sum()+a["suspended_solid_m3"].sum() + m["ledger"]["solid_export_m3"] - m["initial_bed_solid_m3"] - m["ledger"]["solid_input_m3"])
    return {"stage": stage, "physical_time_s": m["physical_time_s"],
      "sha256": file_sha256(path), "shape_zx": list(SHAPE), "spacing_m": SPACING,
      "bed_min_m": float(a["bed_m"].min()), "bed_max_m": float(a["bed_m"].max()),
      "water_depth_max_m": float(a["depth_m"].max()), "wet_cells": int(wet.sum()),
      "deposition_volume_m3": float(np.maximum(delta,0).sum()*area),
      "erosion_volume_m3": float(np.maximum(-delta,0).sum()*area),
      "maximum_bed_rise_m": float(delta.max()), "maximum_bed_erosion_m": float(-delta.min()),
      "floor_hit_cells": int(np.count_nonzero((a["bed_m"]-a["floor_m"]) <= 1e-8)),
      "flooded_land_cells": int(np.count_nonzero(wet & ~a["ocean_mask"])),
      "dry_ocean_cells": int((~wet & a["ocean_mask"]).sum()),
      "water_inventory_m3": float(a["depth_m"].sum()*area),
      "solid_inventory_m3": float(((a["bed_m"]-a["floor_m"])*area*(1-m["config"]["bedload"]["porosity"])).sum()+a["suspended_solid_m3"].sum()),
      "water_input_m3": m["ledger"]["water_input_m3"], "water_export_m3": m["ledger"]["water_export_m3"],
      "sea_import_m3": m["ledger"]["sea_import_m3"], "solid_input_m3": m["ledger"]["solid_input_m3"],
      "solid_export_m3": m["ledger"]["solid_export_m3"],
      "water_budget_residual_m3": water_res, "solid_budget_residual_m3": solid_res,
      "last_boundary_q_m3_s": float(a["boundary_last_water_transfer_m3"].sum()/dt) if dt else 0.}

def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    meta = {"world_seed": WORLD_SEED, "origin_m_xz": ORIGIN, "spacing_m": SPACING,
      "shape_zx": list(SHAPE), "domain_extent_m": [SHAPE[1]*SPACING, SHAPE[0]*SPACING],
      "engineering_scale": "3.84 km x 3.84 km; inspired by river-dominated tidewater deltas, not geographic reproduction",
      "design": "upstream main channel plus floodplain, finite 0.6 m erodible marine cover and 0.85 m shelf slope; no prescribed distributaries",
      "baseline": {"river_Q_m3_s": 180.0, "solid_supply_m3_s": 0.8, "concentration": 0.0044},
      "optional_single_factor": "tide" if args.tide else "none", "cases": {}}
    case = args.output/('tide' if args.tide else 'river-baseline'); case.mkdir()
    product = initial_product(args.tide, args.perturb, args.max_wall_s)
    stages = [("initial", 0., 0., 0.)] if args.smoke else [("initial",0.,0.,0.), ("warmup",600.,180.,0.), ("growth_6h",21600.,180.,0.8), ("growth_12h",21600.,180.,0.8)]
    records = []
    for name, duration, q, solid in stages:
        started=time.monotonic(); pth=case/(name+'.npz')
        if duration:
            t=product['metadata']['physical_time_s']; product=advance(product,[{"id":name,"source":"declared river-scale baseline forcing","time_start_s":t,"time_end_s":t+duration,"water_m3":q*duration,"solid_m3":solid*duration}])
        save(pth, product); product=load(pth, expected_sha256=file_sha256(pth))
        rec=report(product,name,pth); rec['runtime_s']=time.monotonic()-started; records.append(rec)
        (case/(name+'.json')).write_text(json.dumps(rec,indent=2),encoding='utf-8')
    meta['cases'][case.name]={'stages':records,'state_directory':str(case.resolve()), 'runtime_total_s':sum(r['runtime_s'] for r in records),
      'forcing_semantics':'finite upstream river records; solid input is consumed once per stage; sea exchange is ledgered separately'}
    (args.output/'summary.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(args.output.resolve()),'case':case.name,'stages':len(records),'final_hash':records[-1]['sha256']}))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True); p.add_argument('--smoke',action='store_true'); p.add_argument('--tide',action='store_true'); p.add_argument('--perturb',action='store_true'); p.add_argument('--max-wall-s',type=float,default=240.); run(p.parse_args())
if __name__=='__main__': main()
