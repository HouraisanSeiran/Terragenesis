"""Boundary-inherited ocean classification for finite raw terrain support.

Only boundary cells supported by the frozen plate can seed ocean. This does not
establish global ocean connectivity beyond the supplied support rectangle.
"""
import numpy as np
from scipy.ndimage import label
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from terrain_pipeline import plate_td_product
from terrain_pipeline.tectonic_product import load_product
from diffusion.plate_td_conditioning import PLATE_IDENTITY, WORLD_SEED
from diffusion.physical_config import PhysicalGenerationConfig

SCHEMA = "new-world-source-mosaic-v1"
PLATE = ".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz"


def identity(record):
    record = {k: v for k, v in record.items() if k not in ("identity", "source_paths")}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def page_name(x, z):
    return f"page_{x:+d}_{z:+d}"


def _page(path, origin, side, plate_identity):
    manifest, arrays = plate_td_product.read_product(path)
    if (manifest["plate_identity"] != plate_identity or manifest["world_seed"] != WORLD_SEED or
            manifest["origin_native_xz"] != list(origin) or manifest["source_shape_zx"] != [side, side] or
            manifest["coastal"] or manifest["spacing_m"] != 30 or manifest["sea_m"] != 0):
        raise ValueError("page source or coordinates mismatch")
    return manifest, arrays


def prepare_pages(root, source=PLATE, *, core=1024, halo=128, indices=range(-2, 2), generate=False):
    """Reuse authenticated immutable pages; generate missing pages serially."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    side = core + 2 * halo
    for z in indices:
        for x in indices:
            path = root / page_name(x, z)
            origin = [x * core - halo, z * core - halo]
            if not path.exists():
                if not generate:
                    continue
                plate_td_product.prepare(source, path, origin, side, PhysicalGenerationConfig(),
                                         compose_coast=False, expected_identity=PLATE_IDENTITY)
            _page(path, origin, side, PLATE_IDENTITY)


def _boundary_evidence(plate, origin, shape):
    evidence = np.zeros(shape, bool)
    xs = (origin[0] + np.arange(shape[1])) * 30.
    zs = (origin[1] + np.arange(shape[0])) * 30.
    for row in (0, shape[0] - 1):
        evidence[row, :] = plate.sample(xs, np.full_like(xs, zs[row]), outside="reject")["ocean_connected"]
    for col in (0, shape[1] - 1):
        evidence[:, col] = plate.sample(np.full_like(zs, xs[col]), zs, outside="reject")["ocean_connected"]
    return evidence


def assemble(pages, output, source=PLATE, *, core=1024, halo=128, indices=range(-2, 2)):
    """Publish a derived product only after all fixed owner cores authenticate."""
    pages, output = Path(pages), Path(output)
    indices = list(indices)
    if not indices or indices != list(range(indices[0], indices[-1] + 1)) or core < 1 or halo < 1:
        raise ValueError("contiguous page grid and positive core/halo required")
    if output.exists():
        raise FileExistsError(output)
    side = core + 2 * halo
    size = core * len(indices)
    origin = [indices[0] * core, indices[0] * core]
    tmp = Path(tempfile.mkdtemp(prefix=".mosaic-stage-", dir=output.parent))
    raw = climate = None
    try:
        raw = np.lib.format.open_memmap(tmp / "raw_td.npy", mode="w+", dtype=np.float32, shape=(size, size))
        climate = np.lib.format.open_memmap(tmp / "td_climate.npy", mode="w+", dtype=np.float32, shape=(5, size, size))
        records, paths = [], []
        for iz, z in enumerate(indices):
            for ix, x in enumerate(indices):
                path = (pages / page_name(x, z)).resolve()
                parent, arrays = _page(path, [x * core - halo, z * core - halo], side, PLATE_IDENTITY)
                target = (slice(iz * core, (iz + 1) * core), slice(ix * core, (ix + 1) * core))
                raw[target] = arrays["raw_td"][halo:halo + core, halo:halo + core]
                climate[(slice(None), *target)] = arrays["td_climate"][:, halo:halo + core, halo:halo + core]
                records.append({"page_xz": [x, z], "identity": parent["identity"], "files": parent["files"], "owner_origin_native_xz": [x * core, z * core]})
                paths.append(str(path))
                del arrays
        raw.flush(); climate.flush()
        raw._mmap.close()
        climate._mmap.close()
        raw = climate = None
        files = {name: plate_td_product.digest(tmp / (name + ".npy")) for name in ("raw_td", "td_climate")}
        manifest = {"schema": SCHEMA, "source_schema": "plate-td-source-v1", "world_seed": WORLD_SEED,
                    "plate_identity": PLATE_IDENTITY, "origin_native_xz": origin, "shape_zx": [size, size],
                    "spacing_m": 30, "sea_m": 0, "core": core, "halo": halo, "indices": indices,
                    "pages": records, "files": files, "source_paths": {"plate": str(Path(source).resolve()), "pages": paths},
                    "ownership": "each absolute page coordinate owns its core; halo never owns"}
        manifest["identity"] = identity(manifest)
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_product(tmp)
        os.rename(tmp, output)
    finally:
        for array in (raw, climate):
            if array is not None:
                array._mmap.close()
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_product(output)


def read_product(path, expected_identity=None):
    path = Path(path)
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != identity(m) or (expected_identity is not None and m["identity"] != expected_identity):
        raise ValueError("mosaic identity mismatch")
    indices, core, halo = m["indices"], m["core"], m["halo"]
    if (m.get("schema") != SCHEMA or m.get("source_schema") != "plate-td-source-v1" or
            m.get("world_seed") != WORLD_SEED or m.get("plate_identity") != PLATE_IDENTITY or
            m.get("spacing_m") != 30 or m.get("sea_m") != 0 or type(core) is not int or core < 1 or
            type(halo) is not int or halo < 1 or not indices or indices != list(range(indices[0], indices[-1] + 1)) or
            m["origin_native_xz"] != [indices[0] * core] * 2 or m["shape_zx"] != [len(indices) * core] * 2 or
            set(m["files"]) != {"raw_td", "td_climate"}):
        raise ValueError("mosaic contract mismatch")
    arrays = {}
    for name in ("raw_td", "td_climate"):
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != m["files"][name]:
            raise ValueError("mosaic array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        shape = tuple(m["shape_zx"])
        if arrays[name].dtype != np.float32 or arrays[name].shape != ((5, *shape) if name == "td_climate" else shape):
            raise ValueError("mosaic array shape mismatch")
    paths = m["source_paths"]["pages"]
    plate_path = m["source_paths"]["plate"]
    if not Path(plate_path).is_absolute() or any(not Path(p).is_absolute() for p in paths):
        raise ValueError("absolute provenance paths required")
    plate = load_product(plate_path, expected_identity=m["plate_identity"])
    if plate.manifest["config"]["world_seed"] != WORLD_SEED:
        raise ValueError("plate seed mismatch")
    if len(paths) != len(indices) ** 2 or len(m["pages"]) != len(paths):
        raise ValueError("page count mismatch")
    for n, (z, x) in enumerate((z, x) for z in indices for x in indices):
        parent, page = _page(paths[n], [x * core - halo, z * core - halo], core + 2 * halo, m["plate_identity"])
        expected = {"page_xz": [x, z], "identity": parent["identity"], "files": parent["files"], "owner_origin_native_xz": [x * core, z * core]}
        if m["pages"][n] != expected:
            raise ValueError("page identity mismatch")
        iz, ix = divmod(n, len(indices))
        target = (slice(iz * core, (iz + 1) * core), slice(ix * core, (ix + 1) * core))
        for name in arrays:
            if not np.array_equal(arrays[name][(..., *target)], page[name][..., halo:halo + core, halo:halo + core]):
                raise ValueError("owner core mismatch")
        del page
    return m, arrays


def seam_report(path):
    """Measure independent overlap disagreement and adjacent owner-core steps."""
    m, arrays = read_product(path)
    core, halo, indices = m["core"], m["halo"], m["indices"]
    results = []
    paths = m["source_paths"]["pages"]
    width = len(indices)
    for iz, z in enumerate(indices):
        for ix, x in enumerate(indices):
            a_path = paths[iz * width + ix]
            _, a = _page(a_path, [x * core - halo, z * core - halo], core + 2 * halo, m["plate_identity"])
            for dx, dz in ((1, 0), (0, 1)):
                if ix + dx >= width or iz + dz >= width:
                    continue
                _, b = _page(paths[(iz + dz) * width + ix + dx], [(x + dx) * core - halo, (z + dz) * core - halo], core + 2 * halo, m["plate_identity"])
                overlap = min(2 * halo, core + 2 * halo)
                if dx:
                    difference = a["raw_td"][:, -overlap:] - b["raw_td"][:, :overlap]
                    boundary = (ix + 1) * core
                    step = arrays["raw_td"][iz * core:(iz + 1) * core, boundary] - arrays["raw_td"][iz * core:(iz + 1) * core, boundary - 1]
                else:
                    difference = a["raw_td"][-overlap:, :] - b["raw_td"][:overlap, :]
                    boundary = (iz + 1) * core
                    step = arrays["raw_td"][boundary, ix * core:(ix + 1) * core] - arrays["raw_td"][boundary - 1, ix * core:(ix + 1) * core]
                results.append({"page_xz": [x, z], "neighbor_xz": [x + dx, z + dz],
                                "overlap_max_abs_m": float(np.max(np.abs(difference))),
                                "overlap_rms_m": float(np.sqrt(np.mean(difference.astype(np.float64) ** 2))),
                                "owner_step_max_abs_m": float(np.max(np.abs(step))),
                                "owner_step_rms_m": float(np.sqrt(np.mean(step.astype(np.float64) ** 2)))})
                del b
            del a
    return results


def classify_boundary_ocean(raw_td_m, boundary_ocean_connected):
    """Return (ocean, closed below datum, unknown) four-connected masks.

    The second argument is a bool grid of inherited macro-ocean evidence; only
    its outermost cells are used. Interior depressions cannot become anchors.
    """
    raw = np.asarray(raw_td_m)
    evidence = np.asarray(boundary_ocean_connected)
    if raw.ndim != 2 or min(raw.shape) < 2 or evidence.shape != raw.shape:
        raise ValueError("matching two-dimensional arrays required")
    if evidence.dtype != np.bool_ or not np.isfinite(raw).all():
        raise ValueError("finite terrain and boolean evidence required")
    components, _ = label(raw < 0)
    boundary = np.zeros(raw.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    touching = np.unique(components[boundary])
    anchored = np.unique(components[boundary & evidence & (raw < 0)])
    touching = touching[touching != 0]
    anchored = anchored[anchored != 0]
    wet = raw < 0
    ocean = wet & np.isin(components, anchored)
    unknown = wet & np.isin(components, touching) & ~ocean
    closed = wet & ~ocean & ~unknown
    return ocean, closed, unknown
