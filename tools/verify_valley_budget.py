"""Fixed valley-budget and recovery diagnostics for saved river plans."""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_channel_plan import load_plan
from terrain_pipeline.valley_budget import ValleyRecipe, allocate_valley_budget, plan_recovery


PLAN_ROOT = ROOT / "verification/metric-channel-plan/run-20260929T140629572001Z"
OUTPUT = ROOT / "verification/valley-budget"


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir()
    report = {"purpose": "bounded valley shaping allocation and explicit recovery selection",
              "limitations": "no source mutation, route mutation, hydraulic solve, erosion or publication",
              "samples": {}}
    for name in ("pressure_mountain", "normal_mountain"):
        plan = load_plan(PLAN_ROOT / f"{name}-plan.npz")
        protected = np.zeros(plan["arrays"]["source_height_m"].shape, bool)
        protected[plan["arrays"]["channel_mask"]] = False
        allocation = allocate_valley_budget(plan, protected,
                                            {"pass": False, "blockers": {"plan": True}},
                                            ValleyRecipe(total_area_cells=10000))
        recovery = plan_recovery(plan, {"plan": True, "stage": True},
                                 candidate_routes=[{"id": "reroute-protected", "crosses_protection": True,
                                                    "plan_identity_sha256": plan["identity_sha256"]}],
                                 lake_spills=[{"id": "unverified-spill", "legal_outlet": False,
                                               "plan_identity_sha256": plan["identity_sha256"]}])
        report["samples"][name] = {"allocation": allocation["summary"],
                                    "recovery": recovery,
                                    "source_plan": str((PLAN_ROOT / f"{name}-plan.npz").relative_to(ROOT))}
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
