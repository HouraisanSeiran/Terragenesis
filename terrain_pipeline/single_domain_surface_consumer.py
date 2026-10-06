"""Relocatable pinned surface consumption and allowlisted read-only HTTP."""

from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path,PurePosixPath
import shutil
from urllib.parse import urlsplit,unquote

from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from terrain_pipeline.rainfall_runoff import _strict_json

BUDGETS = dict(max_memory_bytes=1073741824,max_output_bytes=2147483648,max_artifact_bytes=268435456,max_wall_s=1800)
SCHEMA = "single-domain-readonly-consumer-v1"
FLAGS = ("hydraulic_ready","natural_outlet_verified","publishable")


def array_roles(arrays):
    records = {}
    for name,value in arrays.items():
        if "_mm" in name or name.endswith("_mm_h"):
            role,units = "hydrologic_store_or_forcing","mm/h" if name.endswith("_mm_h") else "mm"
        elif name.endswith("_m3_s"):
            role,units = "discharge","m3/s"
        elif name.endswith("_m3"):
            role,units = "water_volume","m3"
        elif name.endswith("_m2_s"):
            role,units = "depth_integrated_momentum","m2/s"
        elif name.endswith("_m2"):
            role,units = "area","m2"
        elif name.endswith("_s"):
            role,units = "physical_seconds","s"
        elif name.endswith("xyz_m"):
            role,units = "physical_xyz","m"
        elif "triangles" in name or "indices" in name or name.endswith("ids") or name.endswith("_cell_ids") or name in ("receiver","face_cells","boundary_cells"):
            role,units = "topology_index","dimensionless"
        elif "depth" in name or name.endswith("_m"):
            role,units = "metric_scalar","m"
        elif value.dtype.kind=="b":
            role,units = "classification_mask","boolean"
        else:
            role,units = "saved_evidence","dimensionless"
        records[name] = dict(role=role,units=units,dtype=value.dtype.str,shape=list(value.shape),
                             byte_order="little" if value.dtype.byteorder in ("<","=") else "not_applicable")
        if name=="ledger":
            records[name].update(role="cumulative_surface_water_ledger", units="m3",
                components=["supplied", "boundary_input", "boundary_output", "surface_inventory", "residual"])
        elif name=="state" and value.ndim==2 and value.shape[1]==3:
            records[name].update(role="leaf_hydraulic_state", units="mixed",
                components=["mean_depth", "momentum_x", "momentum_z"], component_units=["m", "m2/s", "m2/s"])
    return records


def _safe_payload(root,name):
    if not isinstance(name,str) or "\\" in name:
        raise ValueError("consumer payload requires portable relative POSIX path")
    portable = PurePosixPath(name)
    if portable.is_absolute() or any(part in ("..",".") for part in portable.parts) or not portable.parts:
        raise ValueError("consumer payload traversal rejected")
    target = root.joinpath(*portable.parts)
    if any(parent.is_symlink() for parent in (target,*target.parents)) or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("consumer payload containment rejected")
    return target


def copy_payload(output,name,pin,bundle,*,role,provenance):
    output = Path(output).resolve(strict=True)
    if not isinstance(name,str) or "\\" in name:
        raise ValueError("consumer copy requires portable relative POSIX path")
    portable = PurePosixPath(name)
    if (portable.is_absolute() or not portable.parts or portable.as_posix()!=name
            or any(part in ("..", ".") or ":" in part for part in portable.parts)):
        raise ValueError("consumer copy destination traversal rejected")
    target = output.joinpath(*portable.parts)
    if not target.resolve().is_relative_to(output):
        raise ValueError("consumer copy destination containment rejected")
    if target.exists() or Path(pin["path"]).stat().st_size>BUDGETS["max_artifact_bytes"] or file_sha256(pin["path"])!=pin["expected_sha256"]:
        raise ValueError("consumer source size/SHA or destination collision")
    target.parent.mkdir(parents=True,exist_ok=True)
    with open(pin["path"],"rb") as source,open(target,"xb") as destination:
        shutil.copyfileobj(source,destination,length=1048576)
    if file_sha256(target)!=pin["expected_sha256"] or file_sha256(pin["path"])!=pin["expected_sha256"]:
        raise ValueError("consumer copy source changed")
    return dict(path=name,sha256=pin["expected_sha256"],identity_sha256=pin["expected_identity"],
                bytes=target.stat().st_size,media_type="application/octet-stream",format="pinned-npz-bundle",
                role=role,arrays=array_roles(bundle["arrays"]),metadata=bundle["metadata"],provenance=provenance)


def publish_manifest(output,manifest):
    target = output/"manifest.json"
    publish_bytes(target,(json.dumps(manifest,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8"))
    return dict(path=str(target.resolve()),expected_sha256=file_sha256(target))


def load_consumer_manifest(path,*,expected_sha256,authenticate_payloads=True):
    path = Path(path).resolve(strict=True)
    if file_sha256(path)!=expected_sha256 or path.stat().st_size>8388608:
        raise ValueError("consumer manifest external SHA/budget mismatch")
    manifest = _strict_json(path.read_text(encoding="utf-8"))
    if (manifest.get("schema")!=SCHEMA or manifest.get("budgets")!=BUDGETS
            or manifest.get("solver_advanced") is not False or any(manifest.get(flag) is not False for flag in FLAGS)
            or manifest.get("backend") not in ("native-v10-saved-dual-cell","fine-saved-fan","adaptive-saved-canonical-fan")
            or manifest.get("evidence_status") not in ("native-accepted-temporal-and-same-bed-review","diagnostic-fine-only","adaptive-finite-window-evidence")):
        raise ValueError("consumer schema/backend/certification mismatch")
    paths,total = {},0
    for item in manifest["artifacts"]:
        target = _safe_payload(path.parent,item["path"])
        if item["path"] in paths or type(item["bytes"]) is not int or not 0<item["bytes"]<=BUDGETS["max_artifact_bytes"] or target.stat().st_size!=item["bytes"]:
            raise ValueError("consumer artifact inventory/bytes mismatch")
        if authenticate_payloads and file_sha256(target)!=item["sha256"]:
            raise ValueError("consumer payload SHA mismatch")
        paths[item["path"]] = target
        total += item["bytes"]
    if total!=manifest["output_bytes"] or total>BUDGETS["max_output_bytes"]:
        raise ValueError("consumer complete byte budget mismatch")
    for scenario in manifest["scenarios"].values():
        if scenario["geometry"] not in paths:
            raise ValueError("consumer geometry not allowlisted")
        frames = scenario["frames"]
        if any(frame["artifact"] not in paths or frame["frame"]!=number for number,frame in enumerate(frames)):
            raise ValueError("consumer frame coverage/allowlist mismatch")
        if manifest["backend"]=="native-v10-saved-dual-cell" and (len(frames)!=25 or [frame["time_s"] for frame in frames]!=[hour*3600. for hour in range(25)]):
            raise ValueError("consumer native complete saved-time coverage mismatch")
    if manifest["backend"]=="native-v10-saved-dual-cell" and set(manifest["scenarios"])!={"eastward","westward"}:
        raise ValueError("consumer complete native directions required")
    if manifest["backend"]=="fine-saved-fan" and manifest["evidence_status"]!="diagnostic-fine-only":
        raise ValueError("fine consumer cannot upgrade unaccepted evidence")
    if manifest["backend"]=="adaptive-saved-canonical-fan":
        if manifest["evidence_status"]!="adaptive-finite-window-evidence" or manifest.get("uniform_coarse_convergence_claim") is not False:
            raise ValueError("adaptive consumer unsupported convergence claim")
        for scenario in manifest["scenarios"].values():
            frames = scenario["frames"]
            if (len(frames)<2 or any(frame.get("snapshot") not in paths or frame.get("adaptive_geometry") not in paths for frame in frames)
                    or frames[0]["time_s"]!=0 or any(first["time_s"]>=second["time_s"] for first,second in zip(frames,frames[1:]))):
                raise ValueError("adaptive consumer snapshot/geometry/time coverage mismatch")
    return dict(manifest=manifest,manifest_path=path,allowlist=paths,expected_sha256=expected_sha256)


def readonly_server(context,*,host="127.0.0.1",port=8766):
    """Only manifest.json and its exact payload allowlist are exposed."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = unquote(urlsplit(self.path).path)
            if route=="/manifest.json":
                target = context["manifest_path"]
                digest = context["expected_sha256"]
                media = "application/json"
            elif route.startswith("/payload/") and route[len("/payload/"):] in context["allowlist"]:
                name = route[len("/payload/"):]
                target = context["allowlist"][name]
                item = next(item for item in context["manifest"]["artifacts"] if item["path"]==name)
                digest,media = item["sha256"],item["media_type"]
            else:
                self.send_error(404)
                return
            if file_sha256(target)!=digest:
                self.send_error(409,"Pinned artifact changed")
                return
            self.send_response(200)
            self.send_header("Content-Type",media)
            self.send_header("Content-Length",str(target.stat().st_size))
            self.send_header("ETag",'"'+digest+'"')
            self.send_header("Cache-Control","no-transform")
            self.end_headers()
            with open(target,"rb") as stream:
                shutil.copyfileobj(stream,self.wfile,length=1048576)
        def log_message(self,format,*args):
            pass
    return ThreadingHTTPServer((host,port),Handler)
