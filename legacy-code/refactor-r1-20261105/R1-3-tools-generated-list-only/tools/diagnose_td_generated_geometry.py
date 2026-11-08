"""Diagnose fixed saved TD network components without repeating routing."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_rivers.metric_td_generated_source import (
    load_generated_td_source,
)
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
    GeneratedRiverConfig,
    _continuous_profile,
    component_geometry,
    selected_components,
    save_component_geometry,
)
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def diagnose(baseline, source_report, output, geometry_case=None):
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for sample in range(6):
        terrain = load_generated_td_source(source_report, sample)["terrain"]
        previous = json.loads((baseline / f"sample-{sample}/report.json").read_text())
        with np.load(
            baseline / f"sample-{sample}/network.npz", allow_pickle=False
        ) as saved:
            data = {key: saved[key] for key in saved.files}
        src, dst = data["selected_edge_source_ids"], data["selected_edge_target_ids"]
        feasible = 0
        records = []
        for index, edges in enumerate(selected_components(src, dst)):
            ids = np.unique(np.r_[src[edges], dst[edges]])
            mapping = {int(cell): i for i, cell in enumerate(ids)}
            receiver = np.full(len(ids), -1, np.int64)
            for a, b in zip(src[edges], dst[edges]):
                receiver[mapping[int(a)]] = mapping[int(b)]
            cols = terrain.elevation_m.shape[1]
            points = np.column_stack(
                (
                    terrain.x0_m + ids % cols * terrain.dx_m,
                    terrain.z0_m + ids // cols * terrain.dz_m,
                )
            )
            record = dict(component_id=index, edge_count=len(edges))
            try:
                profile, depth = _continuous_profile(
                    points, receiver, data["base_depth_m"][ids], terrain, 4.0, 1.0
                )
                feasible += len(edges)
                record.update(
                    status="profile_feasible", maximum_endpoint_cut_m=float(depth.max())
                )
                if geometry_case == (sample, index):
                    bundle = component_geometry(
                        terrain,
                        ids,
                        receiver,
                        data["width_m"][ids],
                        data["base_depth_m"][ids],
                        GeneratedRiverConfig(),
                    )
                    path = output / f"sample-{sample}-component-{index}.npz"
                    save_component_geometry(path, bundle)
                    record.update(
                        geometry=dict(
                            path=path.name,
                            sha256=file_sha256(path),
                            identity_sha256=bundle["identity_sha256"],
                        ),
                        maximum_actual_cut_m=bundle["metadata"]["maximum_cut_m"],
                        moved_nodes=bundle["metadata"]["centerline_moved_nodes"],
                    )
            except ValueError as error:
                record.update(status="rejected", reason=str(error))
            records.append(record)
        case = dict(
            sample_index=sample,
            selected_edges=len(src),
            previous_accepted_edges=previous["accepted_edges"],
            profile_feasible_edges=feasible,
            component_records=records,
        )
        cases.append(case)
        print(
            json.dumps(
                {
                    key: value
                    for key, value in case.items()
                    if key != "component_records"
                }
            ),
            flush=True,
        )
    publish_bytes(
        output / "diagnosis.json",
        json.dumps(
            dict(schema="td-continuous-bed-profile-diagnosis-v1", samples=cases),
            indent=2,
        ).encode(),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry-case", type=int, nargs=2)
    args = parser.parse_args()
    diagnose(
        args.baseline,
        args.source_report,
        args.output,
        tuple(args.geometry_case) if args.geometry_case else None,
    )
