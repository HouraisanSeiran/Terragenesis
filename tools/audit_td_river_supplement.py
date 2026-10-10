"""Pinned supplementary cold audit with all water/material construction disabled."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork
from terrain_pipeline.surface_rivers.metric_lake_channel_coupling import (
    NETWORK_FIELDS,LakeChannelForcing,LakeChannelPort,load_lake_channel,
)
from terrain_pipeline.surface_rivers.metric_morphology_coupling import load_morphology_coupling
from terrain_pipeline.surface_rivers.metric_natural_lakes import load_natural_lakes
from tools.verify_td_morphology_extension import independent_cold
from tools.verify_td_natural_lake_extension import cold_evidence
from tools.verify_td_natural_channel_port import cold_evidence as port_evidence


ROOT=Path(__file__).resolve().parents[1]
PINNED={
    "natural":("verification/td-natural-lake-extension/td256-20261008-04","98bcdcdd40e0f7cb7416903834193ba70904427f82ce3edc9976adcf29171af0"),
    "port":("verification/td-natural-channel-port/td256-20261008-02","238288482493d83097d33aa8750db66be90d770fb28e6a8fc44dd5d6c4c52495"),
    "morphology":("verification/td-morphology-extension/td1024-20261008-03","b24acb8517ab5570154ac80d92b01edd82dc918e8e3d8efb67751b2054934d9d"),
    "reference":("verification/morphology-feedback-reference/20261008-03","c4342178f1e77d7a2feaf77d76126d7056562dbad06b7975c414c94ca37c0bb2"),
}
BLOCKED=(
    "terrain_pipeline.surface_rivers.metric_channel_geometry.build_channel_geometry",
    "terrain_pipeline.surface_rivers.metric_channel_solver.solve_channel",
    "terrain_pipeline.surface_rivers.metric_morphology_coupling.couple_morphology",
    "terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_channel",
    "terrain_pipeline.surface_rivers.metric_morphology_coupling.solve_sediment",
    "terrain_pipeline.surface_rivers.metric_sediment.solve_sediment",
    "terrain_pipeline.surface_rivers.metric_natural_lakes.build_natural_lakes",
    "terrain_pipeline.surface_rivers.metric_natural_lakes.solve_natural_lakes",
    "terrain_pipeline.surface_rivers.metric_lake_channel_coupling.solve_lake_channel",
)


def audit(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    manifests={}
    for name,(folder,sha) in PINNED.items():
        path=ROOT/folder/"acceptance.json"
        if file_sha256(path)!=sha:raise AssertionError(("changed manifest",name))
        manifests[name]=json.loads(path.read_text())
    evidence={}
    with ExitStack() as stack:
        for entry in BLOCKED:
            stack.enter_context(patch(entry,side_effect=AssertionError("cold forbidden "+entry)))
        for name in ("morphology","reference"):
            for key,pin in manifests[name]["artifacts"].items():
                product=load_morphology_coupling(ROOT/PINNED[name][0]/pin["path"],expected_sha256=pin["sha256"])
                if product["identity_sha256"]!=pin["identity_sha256"]:raise AssertionError("morphology identity pin")
                evidence[name+"/"+key]=independent_cold(product)
        natural=manifests["natural"]["artifacts"]
        domain_pin=natural["td-domain"]
        domain=load_natural_lakes(ROOT/PINNED["natural"][0]/domain_pin["path"],expected_sha256=domain_pin["sha256"],expected_identity=domain_pin["identity_sha256"])
        for key in ("td-coarse","td-fine"):
            pin=natural[key]
            product=load_natural_lakes(ROOT/PINNED["natural"][0]/pin["path"],expected_sha256=pin["sha256"],expected_identity=pin["identity_sha256"])
            evidence["natural/"+key]=cold_evidence(domain,product)
        for key in ("coarse","fine"):
            pin=manifests["port"]["artifacts"][key]
            product=load_lake_channel(ROOT/PINNED["port"][0]/pin["path"],expected_sha256=pin["sha256"])
            if product["identity_sha256"]!=pin["identity_sha256"]:raise AssertionError("port identity pin")
            a,m=product["arrays"],product["metadata"]
            local_domain=dict(arrays={k.removeprefix("domain_"):v for k,v in a.items() if k.startswith("domain_")},metadata=m["domain_metadata"],identity_sha256=m["domain_identity_sha256"])
            network=ChannelNetwork(**{key:a["network_"+key] for key in NETWORK_FIELDS},
                source_identity_sha256=m["network_source_identity_sha256"],section_source=m["network_section_source"],roughness_source=m["network_roughness_source"])
            drive=LakeChannelForcing(a["forcing_time_seconds"],a["forcing_channel_local_q_m3_s"],a["forcing_lake_local_q_m3_s"],
                a["forcing_tailwater_stage_m"],m["forcing_source_identity_sha256"],m["forcing_provenance"])
            ports=tuple(LakeChannelPort(**p) for p in m["ports"])
            evidence["port/"+key]=port_evidence(local_domain,network,ports[0],drive,product)
    report=dict(status="passed_bounded_supplement_cold",disabled_entries=list(BLOCKED),
        pinned_manifests=PINNED,evidence=evidence,
        limitations=["not_equilibrium_common_stage_or_global_geometry_acceptance","no_new_hydraulic_solve"],
        hydraulic_ready=False,natural_outlet_verified=False,publishable=False)
    publish_bytes(output/"cold-audit.json",json.dumps(report,indent=2,allow_nan=False).encode())
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    result=audit(parser.parse_args().output)
    print(json.dumps(dict(status=result["status"],cold_products=len(result["evidence"]))))
