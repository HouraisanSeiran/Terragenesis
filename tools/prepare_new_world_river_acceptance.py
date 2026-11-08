"""Run a bounded native event river diagnostic (CPU only)."""
import argparse
import json
from terrain_pipeline.new_world_river_acceptance import run, save, build_supply_inputs, save_supply_inputs
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('water_path')
    parser.add_argument('output')
    for name in ('terrain', 'planner', 'water'):
        parser.add_argument('--expected-' + name + '-identity', required=True)
    parser.add_argument('--origin-native-xz', nargs=2, type=int, required=True)
    parser.add_argument('--shape-zx', nargs=2, type=int, required=True)
    parser.add_argument('--mouth-id')
    parser.add_argument('--width-m', type=float, required=True)
    parser.add_argument('--max-depth-m', type=float, required=True)
    parser.add_argument('--roughness', type=float, required=True)
    parser.add_argument('--downstream-stage-m', type=float, required=True)
    parser.add_argument('--export-supply-input', help='immutable NPZ output path')
    parser.add_argument('--active-layer-bulk-thickness-m', type=float)
    parser.add_argument('--rock-depth-m', type=float)
    parser.add_argument('--initial-mobile-solid-m3-per-node', type=float)
    args = vars(parser.parse_args())
    export = args.pop('export_supply_input')
    thickness = args.pop('active_layer_bulk_thickness_m')
    rock_depth = args.pop('rock_depth_m')
    mobile = args.pop('initial_mobile_solid_m3_per_node')
    if export and any(v is None for v in (thickness, rock_depth, mobile)):
        parser.error('export requires active layer thickness, rock depth and mobile stock')
    output = args.pop('output')
    report, result = run(**args)
    if export:
        material = MaterialParameters(provenance='named homogeneous engineering policy; not calibrated lithology')
        bundle = build_supply_inputs(report, result, active_layer_bulk_thickness_m=thickness, rock_depth_m=rock_depth, initial_mobile_solid_m3_per_node=mobile, material=material)
        report['supply_input_file_sha256'] = save_supply_inputs(export, bundle)
        report['supply_input_scene_identity'] = bundle['metadata']['report']['source_identities']['scene']
    save(report, result, output)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['status'].startswith('physical_solve_complete') else 2


if __name__ == '__main__':
    raise SystemExit(main())
