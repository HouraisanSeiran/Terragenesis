"""Run bounded 1D resolution comparison from a pinned TD M3 native product."""
import argparse
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_channel_product import NETWORK_FIELDS, load_channel_product
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.metric_resolution_exchange import run_resolution_comparison, audit_comparison, save_comparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="M3 acceptance.json with pinned td_fine product")
    parser.add_argument("output", type=Path, help="comparison.json")
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    pin = dict(source["artifacts"]["td_fine"])
    source_path = (args.input.parent / pin["path"]).resolve()
    pin["path"] = str(source_path)
    product = load_channel_product(source_path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    a, m = product["arrays"], product["metadata"]
    network = ChannelNetwork(**{k: a["network_" + k] for k in NETWORK_FIELDS if "network_" + k in a}, source_identity_sha256=m["network_source_identity_sha256"], section_source=m["section_source"], roughness_source=m["roughness_source"])
    forcing = ChannelForcing(a["forcing_time_seconds"], a["forcing_local_q_m3_s"], m["forcing_source_identity_sha256"])
    counts = np.ones(network.receiver.size, np.int64)
    counts[len(counts) // 3:2 * len(counts) // 3] = 2
    report = run_resolution_comparison(network, forcing, local_counts=counts, output_path=args.output,
        config=ChannelConfig(**m["config"]), sediment_config=SedimentConfig(max_steps=4000),
        material=MaterialParameters(settling_velocity_m_s=1e-6, provenance="declared homogeneous slow-settling M7 scenario; uncalibrated"),
        source_manifest={"acceptance_path": str(args.input.resolve()),
            "acceptance_sha256": file_sha256(args.input), "native_channel_product": pin,
            "td_selection": source["td_selection"], "local_selection": "middle third split in two; two mixed interfaces"})
    audit = audit_comparison(args.output)
    report["acceptance"]["conservative_exchange"] = audit["status"]
    save_comparison(args.output, report)
    (args.output.parent / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"comparison": str(args.output), "audit": audit}, indent=2))


if __name__ == "__main__":
    main()
