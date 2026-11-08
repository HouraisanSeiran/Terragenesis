"""Bounded 5 m saved-TD remobilization experiment and independent cold audit."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta,
)
from tools.verify_fluvial_delta import SOURCE, save_result

CROP = (116, 140, 230, 262)
FACTOR = 6
DEFAULT_OUTPUT = ROOT / "verification/fluvial-delta/channel-remobilization-20261015-01"


def refine(height, ocean, factor=FACTOR):
    """Cell-centered bilinear interpolation, nearest at crop/class boundaries.

    A fine cell inherits its native ocean label. Interpolation never mixes ocean
    and land supports; this preserves the registered discontinuous macrocoast.
    """
    rows, columns = height.shape
    rr, cc = np.indices((rows * factor, columns * factor))
    native_r, native_c = rr // factor, cc // factor
    y, x = (rr + .5) / factor - .5, (cc + .5) / factor - .5
    r0, c0 = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - r0, x - c0
    r0, c0 = np.clip(r0, 0, rows - 1), np.clip(c0, 0, columns - 1)
    r1, c1 = np.clip(np.floor(y).astype(int) + 1, 0, rows - 1), np.clip(np.floor(x).astype(int) + 1, 0, columns - 1)
    label = ocean[native_r, native_c]
    same = ((ocean[r0, c0] == label) & (ocean[r1, c0] == label)
            & (ocean[r0, c1] == label) & (ocean[r1, c1] == label))
    interpolated = ((1-fy) * ((1-fx)*height[r0, c0] + fx*height[r0, c1])
                    + fy * ((1-fx)*height[r1, c0] + fx*height[r1, c1]))
    return np.where(same, interpolated, height[native_r, native_c]), label.copy()


def source_input():
    with np.load(SOURCE, allow_pickle=False) as archive:
        meta = json.loads(str(archive["metadata_json"].item()))
        r0, r1, c0, c1 = CROP
        bed, ocean = refine(archive["derived_height_m"][r0:r1, c0:c1], archive["ocean_mask"][r0:r1, c0:c1])
        raw, _ = refine(archive["original_td_m"][r0:r1, c0:c1], archive["ocean_mask"][r0:r1, c0:c1])
    origin = meta["origin_xz_m"]
    provenance = {"kind": "saved_TD", "path": str(SOURCE), "sha256": file_sha256(SOURCE),
                  "crop_rows_columns": list(CROP), "refinement_factor": FACTOR,
                  "interpolation": "cell-centered bilinear within ocean class; nearest native support at class boundary",
                  "native_spacing_m": 30., "fine_spacing_m": 5., "new_TD_detail": False,
                  "raw_td_sha256": meta["raw_provenance"]["archive_sha256"],
                  "saved_detail_identity": meta["identity"], "plan_identity": meta["plan_identity"],
                  "sediment_origin": "explicit synthetic delivery; original TD bed is never eroded",
                  "macrocoast_discontinuity_preserved": True}
    fine_x0, fine_z0 = refined_origin(origin, CROP, FACTOR)
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), fine_x0, fine_z0,
                          5., 5., "conditioned_terrain", "saved-TD-local-class-preserving-refinement", provenance["sha256"],
                          generation_seed=3, source_path=str(SOURCE))
    export = np.zeros(bed.shape, bool)
    export[:, -1] = ocean[:, -1]
    boundary = FluvialDeltaBoundary(ocean, export, 0., 2., "saved-v5-ocean-east-perimeter")
    inlet = (12*FACTOR+3, 8*FACTOR+3)
    forcing = tuple(FluvialDeltaInterval(inlet, 200000., 1200. if i < 8 else 0.) for i in range(16))
    config = FluvialDeltaConfig(split_cost_scale_m=15., max_reentrainment_depth_per_interval_m=.1)
    return terrain, boundary, forcing, config, provenance, raw


def refined_origin(origin, crop, factor):
    offset = 30. * (.5/factor-.5)
    return origin[0]+crop[2]*30.+offset, origin[1]+crop[0]*30.+offset


def synthetic_input():
    bed = np.full((13, 41), 3.)
    bed[4:9, :] = .1
    bed[4:9, 24:] = -.5
    ocean = bed < 0.
    export = np.zeros(bed.shape, bool)
    export[4:9, -1] = True
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 0., 0., 1., 1.,
                          "diagnostic_dem_proxy", "SYNTHETIC-controlled-corridor", "a"*64)
    boundary = FluvialDeltaBoundary(ocean, export, 0., 2., "SYNTHETIC-registered-sea")
    forcing = tuple(FluvialDeltaInterval((6, 0), 100., 8. if i < 4 else 0.) for i in range(20))
    config = FluvialDeltaConfig(max_reentrainment_depth_per_interval_m=.1)
    return terrain, boundary, forcing, config, {"kind": "SYNTHETIC", "path": "SYNTHETIC fixture", "sha256": "a"*64}, bed.copy()


def save_archive(path, terrain, boundary, forcing, result, source, raw):
    with tempfile.TemporaryDirectory(dir=Path(path).parent) as directory:
        temporary = Path(directory)/"base.npz"
        save_result(temporary, terrain, boundary, forcing, result, source, raw)
        with np.load(temporary, allow_pickle=False) as archive:
            arrays = {key: archive[key].copy() for key in archive.files}
    records = result["intervals"]
    arrays.update(reentrained_solid_m3=result["reentrained_solid_m3"], stored_solid_m3=result["stored_solid_m3"],
                  reentrainment=np.stack([item["reentrained_solid_m3"] for item in records]),
                  storage=np.stack([item["stored_solid_m3"] for item in records]))
    area = terrain.cell_area_m2 * (1.-result["metadata"]["config"]["porosity"])
    arrays["beds_m"] = result["initial_bed_m"][None, :, :] + arrays["storage"] / area
    arrays["height_delta_m"] = result["height_delta_m"]
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, **arrays)


def _close(actual, expected):
    np.testing.assert_allclose(actual, expected, atol=1e-7, rtol=1e-12)


def _reachable(active, export):
    seen = np.zeros(active.shape, bool)
    pending = [tuple(cell) for cell in np.argwhere(export & active)]
    for cell in pending:
        seen[cell] = True
    while pending:
        row, column = pending.pop()
        for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            neighbor = row+dr, column+dc
            if not (0 <= neighbor[0] < active.shape[0] and 0 <= neighbor[1] < active.shape[1]):
                continue
            if (active[neighbor] and not seen[neighbor]
                    and (not dr or not dc or (active[row+dr,column] and active[row,column+dc]))):
                seen[neighbor] = True
                pending.append(neighbor)
    return seen


def _check_flow_dag(cells, inlet, water_input, columns, size):
    if not cells.size:
        return
    if water_input <= 0.:
        raise ValueError("positive flow edges without inlet water")
    origins = cells[:,0]*columns+cells[:,1]
    destinations = cells[:,2]*columns+cells[:,3]
    adjacency = {}
    for origin, destination in zip(origins, destinations):
        adjacency.setdefault(int(origin), []).append(int(destination))
    indegree = np.bincount(destinations, minlength=size)
    nodes = set(map(int, np.concatenate((origins, destinations))))
    pending = [cell for cell in nodes if indegree[cell] == 0]
    ordered = []
    while pending:
        cell = pending.pop()
        ordered.append(cell)
        for neighbor in adjacency.get(cell, ()):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                pending.append(neighbor)
    if len(ordered) != len(nodes):
        raise ValueError("saved positive water flow contains a cycle")
    reachable = {inlet[0]*columns+inlet[1]}
    for cell in ordered:
        if cell in reachable:
            reachable.update(adjacency.get(cell, ()))
    if not nodes <= reachable:
        raise ValueError("saved flow has no directed inlet support")


def audit_archive(path, expected_sha256=None):
    """Reconstruct all evidence from saved arrays, without calling the simulator."""
    if expected_sha256 and file_sha256(path) != expected_sha256:
        raise ValueError("saved artifact hash mismatch")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        meta = json.loads(str(archive["metadata_json"].item()))
    for name, value in arrays.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite saved array: " + name)
    source = meta["source"]
    if source["kind"] == "saved_TD":
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError("TD source hash mismatch")
        r0, r1, c0, c1 = source["crop_rows_columns"]
        with np.load(source["path"], allow_pickle=False) as archive:
            ocean = archive["ocean_mask"][r0:r1, c0:c1]
            for name, key in (("initial_bed_m", "derived_height_m"), ("raw_td_m", "original_td_m")):
                refined, labels = refine(archive[key][r0:r1, c0:c1], ocean, source["refinement_factor"])
                np.testing.assert_array_equal(arrays[name], refined)
                np.testing.assert_array_equal(arrays["ocean_mask"], labels)
            original = json.loads(str(archive["metadata_json"].item()))
            _close([meta["terrain"]["x0_m"], meta["terrain"]["z0_m"]],
                   refined_origin(original["origin_xz_m"], source["crop_rows_columns"], source["refinement_factor"]))
        _close([meta["terrain"]["dx_m"], meta["terrain"]["dz_m"]], [30/source["refinement_factor"]]*2)
    elif source["kind"] != "SYNTHETIC":
        raise ValueError("unknown source kind")
    initial, export = arrays["initial_bed_m"], arrays["export_mask"]
    rows, columns = initial.shape
    perimeter = np.ones(initial.shape, bool)
    perimeter[1:-1, 1:-1] = False
    if np.any(export & ~(perimeter & arrays["ocean_mask"] & arrays["valid_mask"])) or not export.any():
        raise ValueError("invalid declared ocean exports")
    if np.any(initial[arrays["ocean_mask"]] > meta["core"]["sea_level_m"]):
        raise ValueError("ocean support above sea level")
    config = meta["core"]["config"]
    solid_area = meta["terrain"]["dx_m"] * meta["terrain"]["dz_m"] * (1-config["porosity"])
    bed, storage = initial.copy(), np.zeros(initial.shape)
    totals = {key: 0. for key in ("water_in", "water_out", "retained", "solid_in", "solid_out", "unresolved", "deposit", "reentrained")}
    if len(arrays["edge_offsets"]) != len(meta["forcing"])+1 or arrays["edge_offsets"][0] != 0 or arrays["edge_offsets"][-1] != len(arrays["edge_cells"]):
        raise ValueError("invalid edge offsets")
    for i, forcing in enumerate(meta["forcing"]):
        start, stop = arrays["edge_offsets"][i:i+2]
        if stop < start:
            raise ValueError("nonmonotone offsets")
        cells, volumes = arrays["edge_cells"][start:stop], arrays["edge_volumes"][start:stop]
        if np.any(volumes < 0.) or (cells.size and (np.any(cells < 0) or np.any(cells[:, (0,2)] >= rows) or np.any(cells[:, (1,3)] >= columns))):
            raise ValueError("invalid edge")
        delta = np.abs(cells[:, :2]-cells[:, 2:])
        if np.any(delta > 1) or np.any(delta.sum(axis=1) == 0):
            raise ValueError("nonlocal edge")
        active = arrays["valid_mask"] & (bed <= meta["core"]["river_head_m"])
        if cells.size and (np.any(~active[cells[:,0],cells[:,1]]) or np.any(~active[cells[:,2],cells[:,3]])):
            raise ValueError("edge crosses blocked bed")
        diagonal = cells[(delta[:,0] == 1) & (delta[:,1] == 1)]
        if diagonal.size and (np.any(~active[diagonal[:,0],diagonal[:,3]]) or np.any(~active[diagonal[:,2],diagonal[:,1]])):
            raise ValueError("diagonal crosses blocked corner")
        incoming, outgoing = [], []
        for channel in range(2):
            incoming.append(np.bincount(cells[:,2]*columns+cells[:,3], weights=volumes[:,channel], minlength=initial.size).reshape(initial.shape))
            outgoing.append(np.bincount(cells[:,0]*columns+cells[:,1], weights=volumes[:,channel], minlength=initial.size).reshape(initial.shape))
        inlet = tuple(forcing["inlet_cell"])
        _check_flow_dag(cells, inlet, forcing["water_volume_m3"], columns, initial.size)
        incoming[0][inlet] += forcing["water_volume_m3"]
        incoming[1][inlet] += forcing["sediment_solid_m3"]
        _close(incoming[0], arrays["water"][i])
        _close(incoming[1], arrays["sediment"][i])
        deposit, eroded = arrays["deposits"][i], arrays["reentrainment"][i]
        if np.any(deposit < 0) or np.any(eroded < 0) or np.any(eroded > storage+1e-8):
            raise ValueError("erosion exceeds available prior inventory")
        if np.any(deposit > config["max_deposit_depth_per_interval_m"]*solid_area+1e-8) or np.any(eroded > config["max_reentrainment_depth_per_interval_m"]*solid_area+1e-8):
            raise ValueError("interval depth cap exceeded")
        depth = np.maximum(0., meta["core"]["sea_level_m"]-bed)
        share = np.minimum(1., incoming[0]/forcing["water_volume_m3"]) if forcing["water_volume_m3"] else np.zeros(initial.shape)
        capacity = incoming[0]*config["capacity_solid_per_water"]*share**config["flow_concentration_exponent"]*np.exp(-np.minimum(745., depth*config["marine_capacity_decay_per_m"]))
        reachable = _reachable(active, export)
        exchanged = reachable & ~export & (incoming[0] > 0.)
        expected_deposit = np.where(exchanged, np.minimum(np.maximum(incoming[1]-capacity, 0.), config["max_deposit_depth_per_interval_m"]*solid_area), 0.)
        expected_erosion = np.where(exchanged, np.minimum(np.minimum(np.maximum(capacity-incoming[1], 0.), storage), config["max_reentrainment_depth_per_interval_m"]*solid_area), 0.)
        _close(deposit, expected_deposit)
        _close(eroded, expected_erosion)
        if cells.size:
            origins = cells[:,0], cells[:,1]
            if np.any(volumes[:,0] <= 0.) or np.any(export[origins]) or np.any(~reachable[origins]):
                raise ValueError("edge has no supported flowing origin")
            carried = incoming[1]+eroded-deposit
            _close(volumes[:,1]*incoming[0][origins], volumes[:,0]*carried[origins])
        if np.any(eroded > np.maximum(0., capacity-incoming[1])+1e-8) or np.any(eroded[export] > 0):
            raise ValueError("erosion exceeds transport deficit")
        water_rest = incoming[0]-outgoing[0]
        solid_rest = incoming[1]+eroded-outgoing[1]-deposit
        permitted = export.copy()
        permitted[inlet] = True
        for rest in (water_rest, solid_rest):
            if np.any(rest < -1e-7) or np.max(np.abs(rest[~permitted]), initial=0.) > 1e-7:
                raise ValueError("per-cell conservation failed")
        prior = float(storage.sum())
        storage += deposit-eroded
        _close(storage, arrays["storage"][i])
        bed = initial+storage/solid_area
        _close(bed, arrays["beds_m"][i])
        values = dict(water_in=forcing["water_volume_m3"], water_out=float(water_rest[export].sum()), retained=float(water_rest[~export].sum()),
                      solid_in=forcing["sediment_solid_m3"], solid_out=float(solid_rest[export].sum()), unresolved=float(solid_rest[~export].sum()),
                      deposit=float(deposit.sum()), reentrained=float(eroded.sum()))
        ledger = meta["interval_ledgers"][i]
        _check_ledgers(ledger["water"], ledger["solid"], values, prior, float(storage.sum()), config["porosity"])
        for key, value in values.items():
            totals[key] += value
    _close(bed, arrays["final_bed_m"])
    _close(bed-initial, arrays["height_delta_m"])
    for stages, total in (("deposits", "deposited_solid_m3"), ("reentrainment", "reentrained_solid_m3")):
        _close(arrays[stages].sum(axis=0), arrays[total])
    _close(storage, arrays["stored_solid_m3"])
    _check_ledgers(meta["water_ledger"], meta["solid_ledger"], totals, 0., float(storage.sum()), config["porosity"])
    return {"passed": True, "independent_cell_inventory_bed_flux_source_audit": True,
            "interval_count": len(meta["forcing"]), "reentrained_solid_m3": totals["reentrained"],
            "stored_solid_m3": float(storage.sum()), "minimum_bed_minus_original_m": float((bed-initial).min()),
            "channel_evidence": channel_evidence(arrays, meta)}


def _check_ledgers(water, solid, values, prior, stored, porosity):
    for key, value in (("input_m3", values["water_in"]), ("ocean_export_m3", values["water_out"]), ("retained_m3", values["retained"]),
                       ("residual_m3", values["water_in"]-values["water_out"]-values["retained"])):
        _close(water[key], value)
    for key, value in (("input_solid_m3", values["solid_in"]), ("ocean_export_solid_m3", values["solid_out"]),
                       ("unresolved_solid_m3", values["unresolved"]), ("deposited_solid_m3", values["deposit"]),
                       ("reentrained_solid_m3", values["reentrained"]), ("initial_stored_solid_m3", prior),
                       ("stored_solid_m3", stored), ("deposit_bulk_m3", values["deposit"]/(1-porosity)),
                       ("stored_bulk_m3", stored/(1-porosity)),
                       ("residual_solid_m3", prior+values["solid_in"]-values["solid_out"]-values["unresolved"]-stored)):
        _close(solid[key], value)


def channel_evidence(arrays, meta):
    """A strict, cardinal connected corridor lowered below its flanking beds.

    Routing edges alone are insufficient. Require actual net flush lowering and
    at least 1 cm relief on both transverse flanks along one bed-derived path.
    """
    flush = next((i for i, item in enumerate(meta["forcing"]) if item["sediment_solid_m3"] == 0.), len(meta["forcing"]))
    if flush == 0 or flush == len(meta["forcing"]):
        return {"continuous_incised_channel": False, "reason": "no deposition-then-clear-water phase"}
    pre, final = arrays["beds_m"][flush-1], arrays["final_bed_m"]
    lowering = pre-final
    lowered = (lowering >= .01) & (arrays["water"][flush:].sum(axis=0) > 1e-5)
    horizontal, vertical = np.zeros(final.shape, bool), np.zeros(final.shape, bool)
    horizontal[1:-1,:] = ((final[:-2,:]-final[1:-1,:] >= .01) & (final[2:,:]-final[1:-1,:] >= .01))
    vertical[:,1:-1] = ((final[:,:-2]-final[:,1:-1] >= .01) & (final[:,2:]-final[:,1:-1] >= .01))
    eligible = lowered & (horizontal | vertical)
    inlet = tuple(meta["forcing"][0]["inlet_cell"])
    pending, seen = [inlet] if eligible[inlet] else [], set()
    while pending:
        cell = pending.pop()
        if cell in seen:
            continue
        seen.add(cell)
        for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
            neighbor = cell[0]+dr, cell[1]+dc
            flanks = horizontal if dc else vertical
            if (0 <= neighbor[0] < final.shape[0] and 0 <= neighbor[1] < final.shape[1]
                    and eligible[neighbor] and flanks[cell] and flanks[neighbor] and neighbor not in seen):
                pending.append(neighbor)
    reaches_ocean = any(arrays["ocean_mask"][cell] for cell in seen)
    return {"continuous_incised_channel": bool(reaches_ocean), "criterion": "cardinal inlet-to-registered-ocean path; >=1 cm flush lowering and both transverse flanks >=1 cm higher",
            "lowered_cell_count": int(lowered.sum()), "lowered_and_low_relative_to_flanks_cell_count": int(eligible.sum()),
            "inlet_connected_low_bed_cell_count": len(seen), "maximum_flush_lowering_m": float(lowering.max()),
            "original_bed_floor_respected": bool(np.all(final >= arrays["initial_bed_m"]-1e-9)),
            "interpretation": "remobilized sediment-cover groove only; not hydraulic downslope or bedrock certification",
            "bedrock_channel_excavation": False}


def render(path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with np.load(path, allow_pickle=False) as archive:
        a = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        m = json.loads(str(archive["metadata_json"].item()))
    flush = next(i for i, item in enumerate(m["forcing"]) if item["sediment_solid_m3"] == 0.)
    pre, final = a["beds_m"][flush-1], a["final_bed_m"]
    spacing = m["terrain"]["dx_m"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    panels = ((a["initial_bed_m"], "Initial actual bed (m)", "terrain"), (final, "Final actual bed (m)", "terrain"),
              (final-a["initial_bed_m"], "Final net deposit thickness (m)", "magma"),
              (pre-final, "Net clear-water lowering (m)", "coolwarm"))
    extent = (0, final.shape[1]*spacing, final.shape[0]*spacing, 0)
    for ax, (data, title, cmap) in zip(axes.flat, panels):
        im = ax.imshow(data, extent=extent, cmap=cmap)
        ax.set(title=title, xlabel="x (m)", ylabel="z (m)")
        fig.colorbar(im, ax=ax, shrink=.75)
    row = m["forcing"][0]["inlet_cell"][0]
    x = (np.arange(final.shape[1])+.5)*spacing
    for data, label in ((a["initial_bed_m"], "original floor"), (pre, "before clear water"), (final, "final")):
        axes[1,1].plot(x, data[row], label=label)
    axes[1,1].set(title="Actual bed section through inlet", xlabel="x (m)", ylabel="bed elevation (m)")
    axes[1,1].legend(fontsize=8)
    steps = np.arange(len(m["forcing"]))
    for key, label in (("deposits", "gross deposited"), ("reentrainment", "reentrained"), ("storage", "end inventory")):
        axes[1,2].plot(steps, a[key].sum(axis=(1,2)), label=label)
    axes[1,2].plot(steps, [item["solid"]["ocean_export_solid_m3"] for item in m["interval_ledgers"]], label="ocean solid export")
    axes[1,2].axvline(flush-.5, color="gray", linestyle=":")
    axes[1,2].set(title="Solid material and export", xlabel="generation interval (not years)", ylabel="solid volume (m3)")
    axes[1,2].legend(fontsize=8)
    fig.suptitle(m["source"]["kind"]+" | fine grid "+str(spacing)+" m | original bed is immutable floor")
    fig.savefig(output, dpi=140)
    plt.close(fig)


def render_zoom(path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with np.load(path, allow_pickle=False) as archive:
        meta = json.loads(str(archive["metadata_json"].item()))
        flush = next(i for i, item in enumerate(meta["forcing"]) if item["sediment_solid_m3"] == 0.)
        row, column = meta["forcing"][0]["inlet_cell"]
        spacing = meta["terrain"]["dx_m"]
        radius = int(np.ceil(150./spacing))
        shape = archive["initial_bed_m"].shape
        r0, r1 = max(0,row-radius), min(shape[0],row+radius+1)
        c0, c1 = max(0,column-radius), min(shape[1],column+radius+1)
        crop = np.s_[r0:r1,c0:c1]
        pre = archive["beds_m"][flush-1][crop]
        final = archive["final_bed_m"][crop]
        water = archive["water"][flush:].sum(axis=0)[crop]
    extent = (c0*spacing,c1*spacing,r1*spacing,r0*spacing)
    low, high = min(pre.min(),final.min()), max(pre.max(),final.max())
    panels = ((pre,"Before clear water: actual bed (m)","terrain",low,high),
              (final,"After clear water: actual bed (m)","terrain",low,high),
              (pre-final,"Net clear-water bed lowering (m)","coolwarm",None,None),
              (np.log10(1.+water),"Clear-water passage log10(1 + m3)","viridis",0,None))
    fig, axes = plt.subplots(2,2,figsize=(12,10),constrained_layout=True)
    for axis, (data,title,cmap,vmin,vmax) in zip(axes.flat,panels):
        im = axis.imshow(data,extent=extent,cmap=cmap,vmin=vmin,vmax=vmax)
        axis.plot((column+.5)*spacing,(row+.5)*spacing,"+",color="black",markersize=9,label="inlet")
        axis.set(title=title,xlabel="local x (m)",ylabel="local z (m)")
        fig.colorbar(im,ax=axis,shrink=.8)
    fig.suptitle("Actual saved fine cells; "+str(spacing)+" m spacing; water passage is not an excavated channel")
    fig.savefig(output,dpi=150)
    plt.close(fig)


def resource_limits():
    if os.name == "nt":
        import ctypes
        handle = ctypes.c_void_p(-1)
        if not ctypes.windll.kernel32.SetProcessAffinityMask(handle, 3) or not ctypes.windll.kernel32.SetPriorityClass(handle, 0x4000):
            raise OSError("cannot enforce two-core BelowNormal policy")


def run(output=DEFAULT_OUTPUT):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reports = {}
    for name, inputs in (("TD-local-5m", source_input()), ("SYNTHETIC-corridor", synthetic_input())):
        directory = output/name
        directory.mkdir()
        terrain, boundary, forcing, config, source, raw = inputs
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        artifact = directory/"delta.npz"
        save_archive(artifact, terrain, boundary, forcing, result, source, raw)
        digest = file_sha256(artifact)
        cold = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--audit", str(artifact), "--expected-sha256", digest],
                              check=True, capture_output=True, text=True)
        audit = json.loads(cold.stdout)
        render(artifact, directory/"bed-material-flux.png")
        render_zoom(artifact, directory/"mouth-zoom.png")
        report = {"source": source, "artifact_sha256": digest, "cold_audit": audit,
                  "cold_audit_in_new_process": True, "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
                  "fine_grid_shape": list(terrain.elevation_m.shape), "fine_spacing_m": terrain.dx_m,
                  "resource_policy": "2 CPU cores; BelowNormal; one numerical thread; no GPU or server",
                  "naturalness_verified": False, "hydraulics_verified": False, "publishable": False}
        (directory/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        reports[name] = report
    publish_reports(output, reports)
    return reports


def publish_reports(output, reports):
    previous = "01 retained as failed/incomplete evidence: fine-grid sample coordinates were shifted by 12.5 m; no acceptance report. 02 corrects the sample origin."
    for report in reports.values():
        report["previous_attempt"] = previous
    (output/"report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    html = "<!doctype html><meta charset='utf-8'><title>Channel remobilization</title><style>body{font:16px sans-serif;margin:24px;color:#222}img{width:100%;max-width:1600px}pre{white-space:pre-wrap}</style><h1>Channel remobilization</h1>"
    html += "<p>"+previous+"</p>"
    for name, report in reports.items():
        html += "<h2>"+name+"</h2><a href='"+name+"/bed-material-flux.png'><img src='"+name+"/bed-material-flux.png'></a><a href='"+name+"/mouth-zoom.png'><img src='"+name+"/mouth-zoom.png'></a><pre>"+json.dumps(report["cold_audit"], indent=2)+"</pre>"
    (output/"index.html").write_text(html, encoding="utf-8")


def refresh(output, add_open_control=False):
    output = Path(output)
    if add_open_control:
        directory = output/"SYNTHETIC-open-corridor"
        directory.mkdir(exist_ok=False)
        terrain, boundary, forcing, config, source, raw = synthetic_input()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        save_archive(directory/"delta.npz", terrain, boundary, forcing, result, source, raw)
        report = {"source": source, "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
                  "fine_grid_shape": list(terrain.elevation_m.shape), "fine_spacing_m": terrain.dx_m,
                  "scenario": "Four deposition intervals leave inlet below head; sixteen clear-water intervals. Eight-deposition clogged case is retained separately.",
                  "naturalness_verified": False, "hydraulics_verified": False, "publishable": False}
        (directory/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    reports = {}
    for directory in sorted(output.iterdir()):
        if not directory.is_dir() or not (directory/"report.json").exists():
            continue
        report = json.loads((directory/"report.json").read_text(encoding="utf-8"))
        artifact = directory/"delta.npz"
        digest = file_sha256(artifact)
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--audit", str(artifact), "--expected-sha256", digest], check=True, capture_output=True, text=True)
        report.update(cold_audit=json.loads(completed.stdout), artifact_sha256=digest, cold_audit_in_new_process=True,
                      verification_tool_sha256=file_sha256(Path(__file__)),
                      previous_attempt="01 retained failed/incomplete: sample coordinates offset by 12.5 m; superseded by 02")
        with np.load(artifact, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"].item()))
            flush = next(i for i, item in enumerate(metadata["forcing"]) if item["sediment_solid_m3"] == 0.)
            report["phase_evidence"] = {}
            for phase, start, stop in (("deposition", 0, flush), ("clear_water", flush, len(metadata["forcing"]))):
                ledgers = metadata["interval_ledgers"][start:stop]
                prior = archive["initial_bed_m"] if start == 0 else archive["beds_m"][start-1]
                end = archive["beds_m"][stop-1]
                report["phase_evidence"][phase] = {
                    "reentrained_solid_m3": float(archive["reentrainment"][start:stop].sum()),
                    "gross_deposited_solid_m3": float(archive["deposits"][start:stop].sum()),
                    "water_ocean_export_m3": sum(item["water"]["ocean_export_m3"] for item in ledgers),
                    "water_retained_m3": sum(item["water"]["retained_m3"] for item in ledgers),
                    "solid_ocean_export_m3": sum(item["solid"]["ocean_export_solid_m3"] for item in ledgers),
                    "maximum_net_lowering_m": float((prior-end).max()),
                    "positive_sediment_flow_edge_count": int(np.count_nonzero(archive["edge_volumes"][archive["edge_offsets"][start]:archive["edge_offsets"][stop],1] > 0.))}
        render(artifact, directory/"bed-material-flux.png")
        render_zoom(artifact, directory/"mouth-zoom.png")
        (directory/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        reports[directory.name] = report
    publish_reports(output, reports)
    return reports


if __name__ == "__main__":
    resource_limits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", type=Path)
    parser.add_argument("--add-open-control", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit_archive(args.audit, args.expected_sha256) if args.audit else
                     refresh(args.refresh, args.add_open_control) if args.refresh else run(args.output), indent=2))
