"""Build an explicit geometry and consume a single mouth's interval forcing."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.new_world_delta import MouthConsumer, DurableMouthConsumer, geometry_fingerprint
from terrain_pipeline.new_world_sediment import load_supply
from terrain_pipeline.surface_rivers.metric_integrated_delta import build_channel_tree, integrated_solid_ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_npz")
    parser.add_argument("output_npz")
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--mouth-id", required=True)
    parser.add_argument("--sediment-source", default="legacy forcing")
    parser.add_argument("--geometry-sha256")
    parser.add_argument("--supply")
    parser.add_argument("--supply-sha256")
    parser.add_argument("--terrain-identity")
    parser.add_argument("--hydrology-identity")
    parser.add_argument("--ledger")
    parser.add_argument("--delivery-id")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--consumed-json",
                        help="JSON array of previously consumed [source, mouth, interval] keys")
    parser.add_argument("--legacy-concentration-forcing", action="store_true",
                        help="explicitly opt in to unverified legacy forcing; actual supplies use DurableMouthConsumer")
    args = parser.parse_args()
    if args.legacy_concentration_forcing:
        if not args.consumed_json:
            parser.error('legacy forcing requires --consumed-json')
    elif not all((args.supply, args.supply_sha256, args.terrain_identity,
                  args.hydrology_identity, args.ledger, args.delivery_id, args.geometry_sha256)):
        parser.error('actual supply requires --supply, --supply-sha256, --terrain-identity, --hydrology-identity, --geometry-sha256, --ledger and --delivery-id')
    if Path(args.output_npz).exists():
        raise FileExistsError(args.output_npz)
    if not args.legacy_concentration_forcing:
        from terrain_pipeline.common_infra import file_sha256
        if file_sha256(args.input_npz) != args.geometry_sha256:
            raise ValueError('geometry file digest mismatch')
    with np.load(args.input_npz, allow_pickle=False) as d:
        if not args.legacy_concentration_forcing:
            for key, expected in (('terrain_identity', args.terrain_identity),
                                  ('hydraulic_identity', args.source_identity), ('mouth_id', args.mouth_id)):
                if key not in d or d[key].shape != () or d[key].dtype.kind != 'U' or d[key].item() != expected:
                    raise ValueError('geometry source or mouth binding mismatch')
        bed, ocean = d["bed_m"], d["ocean_mask"]
        branches = [d[key] for key in sorted(d.files) if key.startswith("branch_path_")]
        geometry = build_channel_tree(bed, d["origin_xz_m"], float(d["spacing_m"]),
            d["mouth_xz_m"], d["apex_xz_m"], d["trunk_path_xz_m"], branches,
            d["widths_m"], ocean_mask=ocean)
        prohibited = d["prohibited_mask"]
        if prohibited.dtype.kind != "b" or prohibited.shape != bed.shape:
            raise ValueError("matching boolean prohibited_mask required")
        geometry.eligible_mask &= ~prohibited
        if args.legacy_concentration_forcing:
            consumed = json.loads(Path(args.consumed_json).read_text(encoding="utf-8"))
            product = MouthConsumer(consumed).run(source_identity=args.source_identity,
                mouth_id=args.mouth_id, interval_ids=d["interval_ids"].tolist(),
                duration_s=d["duration_s"], water_m3=d["water_m3"], solid_m3=d["solid_m3"],
                sediment_source=args.sediment_source, bed_m=bed, ocean_mask=ocean,
                geometry=geometry, prohibited_mask=prohibited)
            forcing = {k: d[k].copy() for k in ("interval_ids", "duration_s", "water_m3", "solid_m3")}
        else:
            supply = load_supply(args.supply, expected_sha256=args.supply_sha256)
            if supply['hydrology_identity'] != args.hydrology_identity:
                raise ValueError('wrong hydrology source identity')
            ids = d['interval_ids'].tolist()
            starts, ends, durations = d['start_seconds'], d['end_seconds'], d['duration_s']
            if not np.array_equal(ends - starts, durations):
                raise ValueError('wrong interval duration')
            consumer = DurableMouthConsumer(args.ledger)
            if args.recover:
                product = consumer.load_result(args.delivery_id)
                expected = {'terrain_identity': args.terrain_identity, 'hydrology_identity': args.hydrology_identity,
                    'hydraulic_identity': args.source_identity, 'sediment_identity': supply['sediment_identity'],
                    'mouth_id': args.mouth_id, 'interval_ids': ids,
                    'start_seconds': list(map(float, starts)), 'end_seconds': list(map(float, ends)),
                    'geometry_sha256': geometry_fingerprint(bed, ocean, geometry, prohibited, None)}
                if product.get('binding') != expected or supply['terrain_identity'] != args.terrain_identity or supply['hydraulic_identity'] != args.source_identity:
                    raise ValueError('recovery binding mismatch')
            else:
                product = consumer.run(supply=supply, terrain_identity=args.terrain_identity,
                    hydraulic_identity=args.source_identity, mouth_id=args.mouth_id, interval_ids=ids,
                    start_seconds=starts, end_seconds=ends, delivery_id=args.delivery_id,
                    bed_m=bed, ocean_mask=ocean, geometry=geometry, prohibited_mask=prohibited)
            forcing = product['forcing']
            consumed = []
        geometry_inputs = {k: d[k].copy() for k in d.files if k in
            ("origin_xz_m", "spacing_m", "mouth_xz_m", "apex_xz_m", "trunk_path_xz_m", "widths_m", "prohibited_mask")
            or k.startswith("branch_path_")}
    destination = Path(args.output_npz)
    if destination.exists():
        raise FileExistsError(destination)
    result = product["result"]
    if not isinstance(result, dict):
        raise ValueError("unsupported delta kernel result contract")
    arrays = {k: v for k, v in result.items() if isinstance(v, np.ndarray)}
    arrays.update({"forcing_" + k: v for k, v in forcing.items()})
    arrays.update({"geometry_" + k: v for k, v in geometry_inputs.items()})
    metadata = {k: v for k, v in product.items() if k not in ("result", "forcing")}
    metadata["all_consumed_keys"] = consumed + product["consumed_keys"]
    metadata["solid_ledger"] = integrated_solid_ledger(result, forcing["solid_m3"])
    metadata["records"] = [asdict(record) for record in result["records"]]
    metadata["config"] = asdict(result["config"])
    metadata["cell_area_m2"] = result["cell_area_m2"]
    arrays["consumption_json"] = np.asarray(json.dumps(metadata, allow_nan=False))
    with destination.open("xb") as handle:
        np.savez_compressed(handle, **arrays)


if __name__ == "__main__":
    main()

