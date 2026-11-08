"""Attribute pinned single-domain epoch transfers to four domain inventories."""

import os

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil

from terrain_pipeline.fine_domain_mosaic import partition_saved_window, audit_saved_epoch_exchange
from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from tools.verify_fine_domain_mosaic import MANIFEST, MANIFEST_SHA


def read_index(record):
    path = Path(record["path"]).resolve()
    if ROOT not in path.parents or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("saved index outside workspace or pin mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def load(record, schema):
    path = Path(record["path"]).resolve()
    if ROOT not in path.parents:
        raise ValueError("saved epoch payload outside workspace")
    bundle = load_bundle(path, expected_sha256=record["expected_sha256"],max_bytes=268435456,validator=lambda value:True)
    if bundle["identity_sha256"] != record["expected_identity"] or bundle["metadata"].get("schema") != schema:
        raise ValueError("saved epoch schema/identity mismatch")
    return bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT not in output.parents or output.exists():
        raise ValueError("new output directory inside workspace required")
    context = load_consumer_manifest(MANIFEST,expected_sha256=MANIFEST_SHA)
    stage_pin = context["manifest"]["source_index"]
    stage = read_index(stage_pin)
    records = []
    for scenario, position in (("tailwater-baseline-root4",0),("tailwater-rise-root4",0),("tailwater-rise-root4",-1)):
        run_pin = stage["cases"][scenario]["run"]
        run = read_index(run_pin)
        pin = run["epochs"][position]
        bundle = load(pin,"surface-adaptive-epoch-v1")
        packet = dict(bundle["metadata"],**bundle["arrays"])
        geometry_bundle = load(run["geometries"][packet["geometry_identity"]],"surface-adaptive-geometry-v1")
        geometry = dict(arrays=geometry_bundle["arrays"],metadata=geometry_bundle["metadata"]["raw_geometry_metadata"],
            identity_sha256=geometry_bundle["metadata"]["raw_geometry_identity"])
        arrays = geometry["arrays"]
        mosaic = partition_saved_window(arrays["canonical_bed_m"],arrays["canonical_bed_m"]*0,
            arrays["canonical_owner"],row_cuts=(168,),column_cuts=(16,),version=packet["geometry_identity"])
        audit = audit_saved_epoch_exchange(mosaic,geometry,packet)
        records.append(dict(scenario=scenario,epoch_pin=pin,run_pin=run_pin,audit=audit))
        read_index(run_pin)
    read_index(stage_pin)
    if file_sha256(MANIFEST) != MANIFEST_SHA:
        raise ValueError("saved consumer pin changed")
    peak = psutil.Process().memory_info().peak_wset
    if peak > 1073741824:
        raise MemoryError("unchanged 1GiB audit budget exceeded")
    report = dict(schema="saved-fine-domain-exchange-attribution-v1",status="passed_saved_epoch_accounting_scope",
        manifest_sha256=MANIFEST_SHA,stage_pin=stage_pin,records=records,peak_rss_bytes=peak,
        independent_domain_hydraulics_verified=False,cross_precision_hydraulic_evolution_verified=False,
        solver_advanced=False,hydraulic_ready=False,natural_outlet_verified=False,publishable=False)
    output.mkdir(parents=True)
    path = output / "report.json"
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(dict(report=str(path),sha256=file_sha256(path),records=records)))


if __name__ == "__main__":
    main()
