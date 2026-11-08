"""Bounded, read-only source inventory; no terrain computation or source certification."""

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import tempfile


VERSION = "geography-preparation-inventory-v1"
MAX_MANIFEST_BYTES = 1024 * 1024
DATA = "01-完整流域样本/data/"
KNOWN = {
    "srtm_61_07.tif": "source_dem_candidate",
    "srtm_61_07.hdr": "source_dem_sidecar",
    "srtm_61_07.tfw": "source_dem_sidecar",
    "srtm_61_07.zip": "source_dem_archive",
    "readme.txt": "source_claim_unverified",
    "ninghai_water_plan_ch3.pdf": "source_document_candidate",
    "funxi_basin_report.json": "dem_derived_candidate",
    "funxi_coarse_basin.json": "dem_derived_candidate",
    "funxi_control_section.json": "area_selected_candidate",
    "funxi_mouth_trace.json": "dem_derived_candidate",
    "funxi_srtm30m_grid.csv": "dem_derived_candidate",
    "funxi_srtm30m_grid_wide.csv": "dem_derived_candidate",
    "funxi_climate_runoff.csv": "modeled_climate_runoff_candidate",
    "valley_cross_sections.json": "other_place_sections",
}
REQUIREMENTS = {
    "valid_real_basin_coverage": ([DATA + "srtm_61_07.tif", DATA + "funxi_basin_report.json", DATA + "funxi_coarse_basin.json"], "DEM coverage and area-selected basin do not certify a real basin boundary or outlet"),
    "vertical_datum": ([DATA + "srtm_61_07.hdr", DATA + "srtm_61_07.tfw", DATA + "readme.txt"], "Horizontal WGS84 and angular pixel spacing do not establish a vertical datum"),
    "independent_river_tributaries": ([DATA + "hydrosheds/HydroRIVERS_v10_as_shp.zip", DATA + "funxi_basin_report.json"], "Regional vector archive and DEM extraction need independent local alignment and tributary verification"),
    "mouth_and_coast": ([DATA + "funxi_mouth_trace.json", DATA + "funxi_control_section.json"], "DEM trace and proposed control point do not certify mouth or coast"),
    "same_place_sections_synchronous_flow": (["02-河谷断面与形态/data/valley_cross_sections.json", DATA + "funxi_climate_runoff.csv"], "Other-place sections and modeled runoff are not colocated synchronous observations"),
    "lake_dam_boundaries": ([DATA + "depression_vs_reservoirs.json", DATA + "ninghai_reservoirs_geocoded.csv"], "DEM depressions and geocoded reservoirs do not certify lake or dam boundary conditions"),
}


class InventoryError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostics = [diagnostic]
        super().__init__(diagnostic)


@dataclass(frozen=True)
class InventoryLimits:
    max_files: int = 512
    max_directories: int = 512
    max_entries: int = 2048
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 128 * 1024 * 1024
    max_metadata_bytes: int = 64 * 1024

    def __post_init__(self):
        caps = (4096, 4096, 16384, 2 * 1024**3, 512 * 1024**2, 1024 * 1024)
        if any(type(value) is not int or not 0 < value <= cap for value, cap in zip(self.__dict__.values(), caps)):
            raise InventoryError("invalid resource limits")


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def _strict_json(content):
    return json.loads(content, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _safe_relative(path):
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts) and not path.startswith("/")


def _kind(path):
    if path.startswith(DATA) and path[len(DATA):] in KNOWN:
        return KNOWN[path[len(DATA):]]
    if path == "02-河谷断面与形态/data/valley_cross_sections.json":
        return "other_place_sections"
    if path.startswith("03-河床与水力/data/") or path.startswith("04-湖泊与溢流/data/"):
        return "other_place_hydraulics"
    if path.startswith(DATA + "hydrosheds/"):
        return "regional_vector_candidate"
    if path.startswith(DATA + "depression/") or path.startswith(DATA) and path.endswith(("depression_vs_reservoirs.json", "ninghai_reservoirs_geocoded.csv")):
        return "dem_derived_candidate"
    return "unreviewed"


def _extract(path, relative, limit):
    if relative in {DATA + "srtm_61_07.hdr", DATA + "srtm_61_07.tfw"}:
        if path.stat().st_size > limit:
            return {"status": "skipped_metadata_limit"}
        try:
            content = path.read_text(encoding="utf-8-sig")
            if relative.endswith(".tfw"):
                numbers = [float(line.strip()) for line in content.splitlines()]
                if len(numbers) != 6 or not all(math.isfinite(number) for number in numbers):
                    raise ValueError("invalid world file")
                return {"status": "parsed_unverified", "world_file_coefficients": numbers}
            return {"status": "parsed_unverified", "declares_wgs84_horizontal": "GCS_WGS_84" in content,
                    "declares_vertical_datum": "VerticalCSTypeGeoKey" in content}
        except (OSError, UnicodeError, ValueError) as error:
            return {"status": "parse_failed", "reason": type(error).__name__}
    if not relative.startswith(DATA) or relative[len(DATA):] not in {
        "funxi_basin_report.json", "funxi_control_section.json", "funxi_mouth_trace.json",
        "funxi_coarse_basin.json", "funxi_climate_runoff.csv"}:
        return None
    if path.stat().st_size > limit:
        return {"status": "skipped_metadata_limit"}
    try:
        content = path.read_text(encoding="utf-8-sig")
        if relative.endswith(".json"):
            value = _strict_json(content)
            if not isinstance(value, dict):
                raise ValueError("expected object")
            result = {"status": "parsed_unverified", "top_level_keys": sorted(value)[:64]}
            if relative.endswith("funxi_control_section.json"):
                control = value.get("control_section")
                if isinstance(control, dict) and type(control.get("upstream_area_km2")) in (int, float):
                    result["reported_control_upstream_area_km2"] = control["upstream_area_km2"]
            return result
        rows = list(csv.reader(io.StringIO(content)))
        if not rows or len(rows) > 4096 or len(rows[0]) > 128:
            raise ValueError("invalid CSV dimensions")
        return {"status": "parsed_unverified", "columns": rows[0], "data_rows": len(rows) - 1}
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        return {"status": "parse_failed", "reason": type(error).__name__}


def prepare(root, limits=InventoryLimits()):
    if not isinstance(limits, InventoryLimits):
        raise InventoryError("invalid resource limits")
    root = Path(root).absolute()
    if not root.is_dir():
        raise InventoryError("source root must be a real directory")
    for ancestor in (root, *root.parents):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise InventoryError(f"source root traverses link or reparse point: {ancestor}")
    files = []
    diagnostics = []
    total = 0
    stack = [root]
    directory_count = 0
    entry_count = 0
    while stack:
        directory = stack.pop()
        directory_count += 1
        if directory_count > limits.max_directories:
            raise InventoryError(f"directory limit at {directory}; visited={directory_count}")
        try:
            with os.scandir(directory) as listing:
                entries = []
                for entry in listing:
                    entry_count += 1
                    if entry_count > limits.max_entries:
                        raise InventoryError(f"entry limit at {directory}; seen={entry_count}")
                    entries.append(entry)
            entries.sort(key=lambda item: item.name)
        except OSError as error:
            raise InventoryError(f"cannot scan {directory}: {error}") from error
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            if not _safe_relative(relative):
                raise InventoryError(f"unsafe source path: {relative}")
            try:
                info = os.stat(entry.path, follow_symlinks=False)
                is_reparse = bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
                if entry.is_symlink() or is_reparse:
                    diagnostics.append({"path": relative, "status": "skipped_link_or_reparse"})
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if directory_count + len(stack) + 1 > limits.max_directories:
                        raise InventoryError(f"directory limit at {relative}; pending={len(stack)}")
                    stack.append(Path(entry.path))
                    continue
                if not stat.S_ISREG(info.st_mode):
                    diagnostics.append({"path": relative, "status": "skipped_non_regular"})
                    continue
                if len(files) >= limits.max_files or info.st_size > limits.max_file_bytes or total + info.st_size > limits.max_total_bytes:
                    raise InventoryError(f"resource limit at {relative}; files={len(files)}, bytes={total}, next={info.st_size}")
                hasher = hashlib.sha256()
                with open(entry.path, "rb") as source:
                    while chunk := source.read(1024 * 1024):
                        hasher.update(chunk)
                after = os.stat(entry.path, follow_symlinks=False)
                if (after.st_size, after.st_mtime_ns, after.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
                    raise InventoryError(f"source changed during read: {relative}")
                file = {"path": relative, "type": Path(relative).suffix.lower() or "extensionless", "bytes": info.st_size,
                        "sha256": hasher.hexdigest(), "source_class": _kind(relative)}
                metadata = _extract(Path(entry.path), relative, limits.max_metadata_bytes)
                after_metadata = os.stat(entry.path, follow_symlinks=False)
                if (after_metadata.st_size, after_metadata.st_mtime_ns, after_metadata.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
                    raise InventoryError(f"source changed during metadata read: {relative}")
                if metadata is not None:
                    file["metadata"] = metadata
                files.append(file)
                total += info.st_size
            except OSError as error:
                raise InventoryError(f"cannot read {relative}: {error}") from error
    files.sort(key=lambda file: file["path"])
    present = {file["path"] for file in files}
    requirements = {name: {"available_files": [path for path in paths if path in present], "certified": False, "limitation": reason}
                    for name, (paths, reason) in REQUIREMENTS.items()}
    payload = {"format": VERSION, "source_root": str(root), "file_count": len(files), "total_bytes": total,
               "files": files, "diagnostics": diagnostics, "requirements": requirements,
               "readiness": {"real_basin_certified": False, "outlet_certified": False, "ready": False,
                             "conclusion": "Candidate materials exist; real basin and outlet are not certified."}}
    payload["identity"] = _digest(payload)
    validate(payload)
    return payload


def validate(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"format", "source_root", "file_count", "total_bytes", "files", "diagnostics", "requirements", "readiness", "identity"}:
        raise InventoryError("invalid manifest fields")
    if manifest["format"] != VERSION or not isinstance(manifest["source_root"], str) or not Path(manifest["source_root"]).is_absolute():
        raise InventoryError("invalid manifest format or root")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) > 4096 or type(manifest["file_count"]) is not int or manifest["file_count"] != len(files):
        raise InventoryError("invalid file count")
    seen = set()
    total = 0
    for file in files:
        if not isinstance(file, dict) or not {"path", "type", "bytes", "sha256", "source_class"} <= set(file) or set(file) - {"path", "type", "bytes", "sha256", "source_class", "metadata"}:
            raise InventoryError("invalid file record")
        path = file["path"]
        if not _safe_relative(path) or path in seen or file["type"] != (Path(path).suffix.lower() or "extensionless") or file["source_class"] != _kind(path):
            raise InventoryError("unsafe or inconsistent file record")
        seen.add(path)
        if type(file["bytes"]) is not int or not 0 <= file["bytes"] <= 512 * 1024**2 or not isinstance(file["sha256"], str) or len(file["sha256"]) != 64 or any(char not in "0123456789abcdef" for char in file["sha256"]):
            raise InventoryError("invalid file size or hash")
        if "metadata" in file:
            metadata = file["metadata"]
            if not isinstance(metadata, dict) or metadata.get("status") not in {"skipped_metadata_limit", "parsed_unverified", "parse_failed"} or set(metadata) - {"status", "top_level_keys", "reported_control_upstream_area_km2", "columns", "data_rows", "reason", "world_file_coefficients", "declares_wgs84_horizontal", "declares_vertical_datum"}:
                raise InventoryError("invalid metadata")
            status = metadata["status"]
            if (status == "skipped_metadata_limit" and set(metadata) != {"status"}
                    or status == "parse_failed" and set(metadata) != {"status", "reason"}
                    or status == "parsed_unverified" and ("reason" in metadata or len(metadata) == 1)):
                raise InventoryError("inconsistent metadata status")
            if ("columns" in metadata) != ("data_rows" in metadata):
                raise InventoryError("inconsistent CSV metadata")
            if ("declares_wgs84_horizontal" in metadata) != ("declares_vertical_datum" in metadata):
                raise InventoryError("inconsistent sidecar metadata")
            if "top_level_keys" in metadata and (not isinstance(metadata["top_level_keys"], list) or len(metadata["top_level_keys"]) > 64 or any(not isinstance(key, str) for key in metadata["top_level_keys"])):
                raise InventoryError("invalid metadata keys")
            if "columns" in metadata and (not isinstance(metadata["columns"], list) or len(metadata["columns"]) > 128 or any(not isinstance(column, str) for column in metadata["columns"])):
                raise InventoryError("invalid metadata columns")
            if "data_rows" in metadata and (type(metadata["data_rows"]) is not int or not 0 <= metadata["data_rows"] <= 4095):
                raise InventoryError("invalid metadata rows")
            if "reported_control_upstream_area_km2" in metadata and (type(metadata["reported_control_upstream_area_km2"]) not in (int, float) or not math.isfinite(metadata["reported_control_upstream_area_km2"])):
                raise InventoryError("invalid metadata area")
            if "world_file_coefficients" in metadata and (not isinstance(metadata["world_file_coefficients"], list) or len(metadata["world_file_coefficients"]) != 6 or any(type(number) not in (int, float) or not math.isfinite(number) for number in metadata["world_file_coefficients"])):
                raise InventoryError("invalid metadata world file")
            if any(type(metadata[key]) is not bool for key in ("declares_wgs84_horizontal", "declares_vertical_datum") if key in metadata) or "reason" in metadata and (not isinstance(metadata["reason"], str) or len(metadata["reason"]) > 64):
                raise InventoryError("invalid metadata flags")
            if len(json.dumps(metadata, ensure_ascii=False, allow_nan=False)) > 65536:
                raise InventoryError("invalid metadata")
        total += file["bytes"]
    if [file["path"] for file in files] != sorted(seen) or type(manifest["total_bytes"]) is not int or total != manifest["total_bytes"] or total > 2 * 1024**3:
        raise InventoryError("invalid totals or order")
    if not isinstance(manifest["diagnostics"], list) or len(manifest["diagnostics"]) > 4096:
        raise InventoryError("invalid diagnostics")
    for diagnostic in manifest["diagnostics"]:
        if not isinstance(diagnostic, dict) or set(diagnostic) != {"path", "status"} or not _safe_relative(diagnostic["path"]) or diagnostic["status"] not in {"skipped_link_or_reparse", "skipped_non_regular"}:
            raise InventoryError("invalid diagnostic")
    expected = {name: {"available_files": [path for path in paths if path in seen], "certified": False, "limitation": reason}
                for name, (paths, reason) in REQUIREMENTS.items()}
    if not isinstance(manifest["requirements"], dict) or any(
            not isinstance(item, dict) or type(item.get("certified")) is not bool
            for item in manifest["requirements"].values()):
        raise InventoryError("invalid requirement flags")
    if not isinstance(manifest["readiness"], dict) or any(
            type(manifest["readiness"].get(name)) is not bool
            for name in ("real_basin_certified", "outlet_certified", "ready")):
        raise InventoryError("invalid readiness flags")
    if manifest["requirements"] != expected or manifest["readiness"] != {"real_basin_certified": False, "outlet_certified": False, "ready": False, "conclusion": "Candidate materials exist; real basin and outlet are not certified."}:
        raise InventoryError("invalid readiness or requirements")
    identity = manifest["identity"]
    if not isinstance(identity, str) or identity != _digest({key: value for key, value in manifest.items() if key != "identity"}):
        raise InventoryError("manifest identity mismatch")


def save(manifest, destination):
    validate(manifest)
    encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise InventoryError("manifest exceeds size limit")
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".inventory-", delete=False) as output:
            temporary = Path(output.name)
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def load(source):
    source = Path(source)
    if source.stat().st_size > MAX_MANIFEST_BYTES:
        raise InventoryError("manifest exceeds size limit")
    try:
        manifest = _strict_json(source.read_text(encoding="utf-8"))
        validate(manifest)
    except (UnicodeError, json.JSONDecodeError, TypeError, OverflowError, ValueError) as error:
        raise InventoryError(f"invalid manifest: {error}") from error
    return manifest
