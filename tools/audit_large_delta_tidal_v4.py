"""Audit existing v4 product against the source without generating data."""
import argparse
import json
import numpy as np
from terrain_pipeline.large_delta_tidal_source import load_source
from terrain_pipeline.large_delta_tidal_product_v4 import read_product

parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('product');args=parser.parse_args()
s=load_source(args.source);p=read_product(args.product);a=p['native'];m=p['manifest'];state=p['checkpoint'];g=p['geometry'];q=p['series']['records']
change=a['bed_m']-s['initial_bed_m'];coverage=a['coverage'];native=float(change.sum(dtype=np.float64)*540);graph=float((state.bed_solid_m3-g['initial_stock']).sum());water=float(a['water_depth_m'].sum(dtype=np.float64)*900)
report=dict(source_identity=m['source_identity'],seconds=state.time_s,native_solid_delta_m3=native,graph_solid_delta_m3=graph,solid_mapping_error_m3=native-graph,native_water_m3=water,graph_water_m3=float(state.water_m3.sum()),water_mapping_error_m3=water-float(state.water_m3.sum()),minimum_floor_margin_m=float((a['bed_m']-s['active_layer']['floor_m']).min()),changed_cells=int(np.count_nonzero(np.abs(change)>1e-8)),covered_cells=int(coverage.sum()),native_bed_change_min_m=float(change.min()),native_bed_change_max_m=float(change.max()),outlet_min_m3_s=q[:,2:5].min(0).tolist(),outlet_max_m3_s=q[:,2:5].max(0).tolist(),outlet_reversal_samples=(q[:,2:5]<0).sum(0).tolist(),low_wet_cells=int(np.count_nonzero(a['low_depth_m'])),high_wet_cells=int(np.count_nonzero(a['high_depth_m'])),wet_changed_cells=int(np.count_nonzero((a['low_depth_m']>0)!=(a['high_depth_m']>0))),ledger=m['ledger'])
print(json.dumps(report,indent=2))
