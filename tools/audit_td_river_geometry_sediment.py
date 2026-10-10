"""Cold M5/M6 audit: source, indexed geometry, Exner and independent step ledgers."""

import argparse
import json
from pathlib import Path
import struct
from unittest.mock import patch

import numpy as np
from scipy.spatial import cKDTree

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import load_channel_geometry
from terrain_pipeline.surface_rivers.metric_channel_product import load_channel_product
from terrain_pipeline.surface_rivers.metric_sediment import load_sediment
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from tools.verify_td_river_geometry import mesh_evidence, shape_evidence, TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID
from tools.verify_td_river_sediment import sample_saved_mesh, solid_budget


DISABLED = (
    "terrain_pipeline.surface_rivers.metric_channel_geometry.build_channel_geometry",
    "terrain_pipeline.surface_rivers.metric_sediment.solve_sediment",
    "terrain_pipeline.surface_rivers.metric_channel_solver.solve_channel",
    "terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled",
    "terrain_pipeline.surface_rivers.metric_drainage.route_diagnostic",
    "terrain_pipeline.surface_rivers.metric_drainage.accumulate_local_discharge",
    "terrain_pipeline.surface_rivers.metric_runoff.runoff_from_forcing",
    "terrain_pipeline.surface_rivers.metric_large_runoff.runoff_from_forcing_large",
    "terrain_pipeline.surface_rivers.metric_product.build_diagnostic_product",
    "terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy",
)


def cold_preview(geometries, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
    for axis, name in zip(axes, ("turn_fine", "y_fine", "td_bend_fine")):
        a, m = geometries[name]["arrays"], geometries[name]["metadata"]
        if name.startswith("td_"):
            source = a["source_height_m"]
            tm = m["terrain_metadata"]
            vertices = a["vertices_xz_m"]
            r0 = max(0, int(np.floor((vertices[:, 1].min() - tm["z0_m"]) / tm["dz_m"])) - 1)
            r1 = min(len(source) - 1, int(np.ceil((vertices[:, 1].max() - tm["z0_m"]) / tm["dz_m"])) + 1)
            c0 = max(0, int(np.floor((vertices[:, 0].min() - tm["x0_m"]) / tm["dx_m"])) - 1)
            c1 = min(source.shape[1] - 1, int(np.ceil((vertices[:, 0].max() - tm["x0_m"]) / tm["dx_m"])) + 1)
            xs = tm["x0_m"] + np.arange(c0, c1 + 1) * tm["dx_m"]
            zs = tm["z0_m"] + np.arange(r0, r1 + 1) * tm["dz_m"]
            axis.pcolormesh(xs, zs, source[r0:r1 + 1, c0:c1 + 1], cmap="terrain", shading="gouraud")
            faces = a["triangles"][np.max(a["cut_depth_m"][a["triangles"]], axis=1) > 1e-10]
        else:
            faces = a["triangles"]
        axis.tripcolor(a["vertices_xz_m"][:, 0], a["vertices_xz_m"][:, 1], faces,
                       a["cut_depth_m"], cmap="Blues", shading="gouraud", alpha=.85)
        for i, j in enumerate(a["receiver"]):
            if j < 0:
                continue
            original, changed = a["original_node_xz_m"][[i, j]], a["node_xz_m"][[i, j]]
            axis.plot(original[:, 0], original[:, 1], color="#c27624", linestyle="--", linewidth=1.3)
            axis.plot(changed[:, 0], changed[:, 1], color="#14553b", linewidth=1.5)
        axis.set_title({"turn_fine": "90 degree turns | shared cut field",
                        "y_fine": "Y junction | one bed, one cut ledger",
                        "td_bend_fine": "Real TD original bed | 45 to 33.90 degrees"}[name], fontsize=10)
        axis.set_aspect("equal")
        axis.set_xlabel("X (m)")
        axis.set_ylabel("Z (m)")
        axis.ticklabel_format(useOffset=False, style="plain")
        axis.xaxis.set_major_locator(MaxNLocator(3))
        axis.tick_params(axis="x", labelrotation=25, labelsize=8)
    fig.suptitle("Cold-loaded M5 evidence | original dashed / constrained solid | blue = cut, not water")
    fig.tight_layout()
    fig.savefig(output / "geometry-cold-preview.png", dpi=160)
    plt.close(fig)


def verify_glb(path, expected_vertices, expected_faces):
    payload = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", payload)
    if magic != 0x46546C67 or version != 2 or length != len(payload):
        raise AssertionError("invalid glTF binary header")
    json_length, json_kind = struct.unpack_from("<II", payload, 12)
    if json_kind != 0x4E4F534A:
        raise AssertionError("missing glTF JSON chunk")
    document = json.loads(payload[20:20 + json_length])
    bin_length, bin_kind = struct.unpack_from("<II", payload, 20 + json_length)
    if bin_kind != 0x004E4942 or bin_length != len(payload) - 28 - json_length:
        raise AssertionError("invalid glTF binary geometry chunk")
    if document["accessors"][0]["count"] != expected_vertices or document["accessors"][1]["count"] != 3 * expected_faces:
        raise AssertionError("GLB geometry does not match saved mesh")
    return {"path": path.name, "sha256": file_sha256(path), "vertices": expected_vertices,
            "triangles": expected_faces, "structural_glTF_verified": True,
            "display_export_not_hydraulic_geometry": True}


def independent_continuous_bed(product):
    """Clip each whole centerline segment against saved triangles using barycentric halfspaces."""
    a = product["arrays"]
    triangle = a["vertices_xz_m"][a["triangles"]]
    first = triangle[:, 1] - triangle[:, 0]
    second = triangle[:, 2] - triangle[:, 0]
    determinant = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]
    bed = a["bed_elevation_m"][a["triangles"]]
    minimum_slope = np.inf
    for i, j in enumerate(a["receiver"]):
        if j < 0:
            continue
        start, end = a["node_xz_m"][[i, j]]
        relative = start - triangle[:, 0]
        delta = end - start
        u = (relative[:, 0] * second[:, 1] - relative[:, 1] * second[:, 0]) / determinant
        v = (first[:, 0] * relative[:, 1] - first[:, 1] * relative[:, 0]) / determinant
        du = (delta[0] * second[:, 1] - delta[1] * second[:, 0]) / determinant
        dv = (first[:, 0] * delta[1] - first[:, 1] * delta[0]) / determinant
        initial = np.column_stack((1. - u - v, u, v))
        derivative = np.column_stack((-du - dv, du, dv))
        lo, hi, possible = np.zeros(len(triangle)), np.ones(len(triangle)), np.ones(len(triangle), bool)
        for k in range(3):
            increasing, decreasing = derivative[:, k] > 1e-12, derivative[:, k] < -1e-12
            constant = ~(increasing | decreasing)
            possible[constant & (initial[:, k] < -1e-9)] = False
            lo[increasing] = np.maximum(lo[increasing], -initial[increasing, k] / derivative[increasing, k])
            hi[decreasing] = np.minimum(hi[decreasing], -initial[decreasing, k] / derivative[decreasing, k])
        selected = possible & (hi - lo > 1e-10)
        gradient = np.sum(derivative[selected] * (bed[selected] - bed[selected, :1]), axis=1)
        if not selected.any() or np.any(gradient >= -1e-10):
            raise AssertionError("saved PL bed has a continuously flat or uphill centerline interval")
        minimum_slope = min(minimum_slope, float((-gradient / np.linalg.norm(delta)).min()))
        covered = 0.
        for lower, upper in sorted(zip(lo[selected], hi[selected])):
            if lower > covered + 1e-8:
                raise AssertionError("canonical mesh does not cover full centerline")
            covered = max(covered, upper)
        if covered < 1. - 1e-8:
            raise AssertionError("canonical mesh omits terminal centerline interval")
    return {"continuous_PL_bed_downhill_verified": True, "minimum_PL_centerline_slope": minimum_slope}


def independent_source_and_cut(product):
    a, m = product["arrays"], product["metadata"]
    terrain = m["terrain_metadata"]
    points = a["vertices_xz_m"]
    height = a["source_height_m"]
    gx = (points[:, 0] - terrain["x0_m"]) / terrain["dx_m"]
    gz = (points[:, 1] - terrain["z0_m"]) / terrain["dz_m"]
    c = np.minimum(gx.astype(np.int64), height.shape[1] - 2)
    r = np.minimum(gz.astype(np.int64), height.shape[0] - 2)
    u, v = gx - c, gz - r
    reconstructed = ((1. - u) * (1. - v) * height[r, c] + u * (1. - v) * height[r, c + 1]
                     + (1. - u) * v * height[r + 1, c] + u * v * height[r + 1, c + 1])
    np.testing.assert_allclose(a["source_elevation_m"], reconstructed, rtol=0., atol=1e-9)
    centers = a["node_xz_m"]
    effective_depth = a["depth_m"].copy()
    effective_depth[a["lake_mask"].ravel()[a["source_node_cell_ids"]]] = 0.
    maximum_cut = np.zeros(len(points))
    for i, j in enumerate(a["receiver"]):
        if j < 0:
            continue
        delta = centers[j] - centers[i]
        fraction = np.clip((points - centers[i]) @ delta / np.dot(delta, delta), 0., 1.)
        distance = np.linalg.norm(points - centers[i] - fraction[:, None] * delta, axis=1)
        half_width = ((1. - fraction) * a["width_m"][i] + fraction * a["width_m"][j]) / 2.
        depth = (1. - fraction) * effective_depth[i] + fraction * effective_depth[j]
        expected = np.minimum(depth, np.maximum(0., (half_width + 2. * depth - distance) / 2.))
        maximum_cut = np.maximum(maximum_cut, expected)
    if a["lake_mask"].any():
        lake = a["lake_mask"]
        wet_cells = lake[:-1, :-1] | lake[:-1, 1:] | lake[1:, :-1] | lake[1:, 1:]
        wr, wc = np.nonzero(wet_cells)
        wet_centers = np.column_stack((terrain["x0_m"] + (wc + .5) * terrain["dx_m"],
                                       terrain["z0_m"] + (wr + .5) * terrain["dz_m"]))
        distance = cKDTree(wet_centers).query(points)[0]
        lower = np.maximum(0., distance - np.hypot(terrain["dx_m"], terrain["dz_m"]) / 2.)

        def sample(position):
            xx = (position[0] - terrain["x0_m"]) / terrain["dx_m"]
            zz = (position[1] - terrain["z0_m"]) / terrain["dz_m"]
            x, z = min(int(np.floor(xx)), height.shape[1] - 2), min(int(np.floor(zz)), height.shape[0] - 2)
            tx, tz = xx - x, zz - z
            return ((1. - tx) * (1. - tz) * height[z, x] + tx * (1. - tz) * height[z, x + 1]
                    + (1. - tx) * tz * height[z + 1, x] + tx * tz * height[z + 1, x + 1])

        minimum_slope = np.inf
        for i, j in enumerate(a["receiver"]):
            if j < 0:
                continue
            start, end = centers[i], centers[j]
            delta = end - start
            parameters = [0., 1.]
            for axis, origin, step in ((0, terrain["x0_m"], terrain["dx_m"]),
                                       (1, terrain["z0_m"], terrain["dz_m"])):
                if delta[axis] == 0.:
                    continue
                lo, hi = int(np.floor((min(start[axis], end[axis]) - origin) / step)), int(np.ceil((max(start[axis], end[axis]) - origin) / step))
                for k in range(lo, hi + 1):
                    t = (origin + k * step - start[axis]) / delta[axis]
                    if 1e-12 < t < 1. - 1e-12:
                        parameters.append(t)
            parameters = sorted(set(parameters))
            for first, last in zip(parameters[:-1], parameters[1:]):
                h0, hm, h1 = (sample(start + t * delta) for t in (first, (first + last) / 2., last))
                length = (last - first) * np.linalg.norm(delta)
                minimum_slope = min(minimum_slope, -(4. * hm - 3. * h0 - h1) / length,
                                    -(h0 + 3. * h1 - 4. * hm) / length)
        maximum_cut = np.minimum(maximum_cut, lower * .25 * minimum_slope)
        # Boundaries belong to both adjacent source cells, so protect either incident wet cell.
        ix, iz = np.floor(gx + 1e-10).astype(int), np.floor(gz + 1e-10).astype(int)
        protected = np.zeros(len(points), bool)
        for cx in (ix, ix - 1):
            for cz in (iz, iz - 1):
                inside = (cx >= 0) & (cx < wet_cells.shape[1]) & (cz >= 0) & (cz < wet_cells.shape[0])
                inside &= (cx == ix) | (np.abs(gx - np.round(gx)) <= 1e-10)
                inside &= (cz == iz) | (np.abs(gz - np.round(gz)) <= 1e-10)
                protected[inside] |= wet_cells[cz[inside], cx[inside]]
        maximum_cut[protected] = 0.
        if np.any(a["cut_depth_m"][protected] != 0.):
            raise AssertionError("represented cut intrudes into conservative known lake support")
    np.testing.assert_allclose(maximum_cut, a["cut_depth_m"], rtol=0., atol=1e-9)
    np.testing.assert_allclose(a["bed_elevation_m"], reconstructed - maximum_cut, rtol=0., atol=1e-9)
    return {"original_bilinear_source_verified": True, "max_envelope_no_double_cut_verified": True,
            "modified_bed_separate_from_original": True}


def independent_sediment_step(product, i, dt):
    """Recompute one simultaneous conservative step from public material laws."""
    a, m = product["arrays"], product["metadata"]
    material = m["material"]
    time = a["trace_time_seconds"][i]
    interval = min(np.searchsorted(a["forcing_time_seconds"], time, side="right") - 1,
                   len(a["forcing_time_seconds"]) - 2)
    bed0, area = a["domain_bed_elevation_m"], a["domain_bed_area_m2"]
    width, receiver = a["domain_width_m"], a["domain_receiver"]
    loose0 = a["domain_initial_alluvium_bulk_m3"] * (1. - material["porosity"])
    mobile = a["trace_mobile_solid_m3"][i]
    loose = a["trace_bed_alluvium_solid_m3"][i]
    removed = a["trace_rock_removed_m3"][i]
    q, water = a["forcing_water_outflow_m3_s"][interval], a["forcing_water_volume_m3"][interval]
    h = a["forcing_water_depth_m"][interval]
    shear = 9810. * (width * h / (width + 2. * h)) * a["forcing_friction_slope"][interval]
    shear[(q <= 0.) | a["domain_is_lake"]] = 0.
    excess = np.maximum(0., shear - material["sediment_critical_shear_pa"])
    advective = q * np.divide(mobile, water, out=np.zeros_like(mobile), where=water > 0.)
    capacity = material["transport_coefficient"] * width * excess ** 1.5
    capacity[a["domain_is_lake"]] = advective[a["domain_is_lake"]]
    outgoing = dt * np.minimum(advective, capacity)
    deposited = dt * material["settling_velocity_m_s"] * np.divide(mobile, h, out=np.zeros_like(mobile), where=h > 0.)
    deficit = np.maximum(0., capacity - outgoing / dt)
    loose_rate = np.minimum(deficit, area * material["sediment_erodibility_m_s_pa"] * excess * (1. - material["porosity"]))
    loose_rate[loose <= 0.] = 0.
    eroded_loose = np.minimum(dt * loose_rate, loose)
    rock_rate = np.minimum(np.maximum(0., deficit - loose_rate), area * material["rock_erodibility_m_s_pa"]
                           * np.maximum(0., shear - material["rock_critical_shear_pa"]))
    rock_rate[loose > 0.] = 0.
    reserve = (bed0 - a["domain_initial_alluvium_bulk_m3"] / area - a["domain_rock_floor_m"]) * area - removed
    eroded_rock = np.minimum(dt * rock_rate, np.maximum(0., reserve))
    incoming = np.zeros_like(mobile)
    for node, target in enumerate(receiver):
        if target >= 0:
            incoming[target] += outgoing[node]
    external = dt * a["forcing_external_solid_m3_s"][interval]
    final_mobile = mobile + incoming + external + eroded_loose + eroded_rock - outgoing - deposited
    final_loose = loose + deposited - eroded_loose
    final_removed = removed + eroded_rock
    final_bed = bed0 + (final_loose - loose0) / (area * (1. - material["porosity"])) - final_removed / area
    exported = np.where(a["domain_open_boundary"], outgoing, 0.)
    return {"mobile_solid_m3": final_mobile, "bed_alluvium_solid_m3": final_loose,
            "rock_removed_m3": final_removed, "bed_elevation_m": final_bed,
            "outgoing_solid_m3": outgoing, "incoming_solid_m3": incoming, "external_solid_m3": external,
            "eroded_loose_solid_m3": eroded_loose, "eroded_rock_m3": eroded_rock,
            "deposited_solid_m3": deposited, "exported_solid_m3": exported, "shear_pa": shear,
            "capacity_solid_m3_s": capacity, "bulk_deposition_m3": deposited / (1. - material["porosity"]),
            "pore_deposition_m3": deposited * material["porosity"] / (1. - material["porosity"]),
            "bulk_erosion_m3": eroded_loose / (1. - material["porosity"]) + eroded_rock}, interval


def independent_sediment(product):
    a, m = product["arrays"], product["metadata"]
    statekeys = ("mobile_solid_m3", "bed_alluvium_solid_m3", "rock_removed_m3", "bed_elevation_m")
    for i, dt in enumerate(a["step_dt_seconds"]):
        expected, interval = independent_sediment_step(product, i, float(dt))
        for key, values in expected.items():
            observed = a["trace_" + key][i + 1] if key in statekeys else a["step_" + key][i]
            np.testing.assert_allclose(observed, values, rtol=0., atol=1e-9 if key == "bed_elevation_m" else 1e-10)
        if dt > m["config"]["max_dt_seconds"] * (1. + 1e-12):
            raise AssertionError("saved step exceeds configured time limit")
    if m["status"] == "failed_prefix":
        i = len(a["step_dt_seconds"])
        now = a["trace_time_seconds"][-1]
        interval = min(np.searchsorted(a["forcing_time_seconds"], now, side="right") - 1,
                       len(a["forcing_time_seconds"]) - 2)
        dt = min(m["config"]["max_dt_seconds"], a["forcing_time_seconds"][interval + 1] - now)
        trial, _ = independent_sediment_step(product, i, dt)
        # Saved verification fixture deliberately fails the cumulative morphology gate.
        if m["failure_reason"] == "maximum cumulative bed change exceeded":
            if np.max(np.abs(trial["bed_elevation_m"] - a["domain_bed_elevation_m"])) <= m["config"]["max_bed_change_m"]:
                raise AssertionError("failed bed-change prefix has no independent witness")
        else:
            raise AssertionError("this cold verification fixture has an unexpected failure reason")
    return solid_budget(product) | {"independent_step_and_Exner_verified": True}


def audit(geometry_directory, sediment_directory, output):
    geometry_directory, sediment_directory, output = map(lambda p: Path(p).resolve(),
                                                          (geometry_directory, sediment_directory, output))
    output.mkdir(parents=True, exist_ok=False)
    gm = json.loads((geometry_directory / "acceptance.json").read_text(encoding="utf-8"))
    sm = json.loads((sediment_directory / "acceptance.json").read_text(encoding="utf-8"))
    if (gm["td_source"]["sha256"] != TD_PRODUCT_SHA or gm["td_source"]["identity_sha256"] != TD_PRODUCT_ID
            or Path(gm["td_source"]["path"]).resolve() != (TD_DIRECTORY / "product.npz").resolve()
            or gm["td_source"]["source_sha256"] != "66bb82f254af54b1fa20a886dafa766ebe345abdc481c90403f4ee197d17d9b3"):
        raise AssertionError("geometry manifest does not match external original TD pins")
    if (sm["geometry_manifest"]["sha256"] != file_sha256(geometry_directory / "acceptance.json")
            or Path(sm["geometry_manifest"]["path"]).resolve() != geometry_directory / "acceptance.json"
            or sm["td_geometry"] != gm["artifacts"]["td_fine"] | {
                "path": str(geometry_directory / gm["artifacts"]["td_fine"]["path"])}):
        raise AssertionError("sediment manifest does not bind the exact accepted M5 manifest")
    active = []
    try:
        for entry in DISABLED:
            handle = patch(entry, side_effect=AssertionError("cold audit called disabled generator: " + entry))
            handle.start()
            active.append(handle)
        geometry_cases, sediment_cases, geometries = {}, {}, {}
        for name, pin in gm["artifacts"].items():
            if pin["path"] != name + ".npz":
                raise AssertionError("geometry artifact path outside expected package")
            result = load_channel_geometry(geometry_directory / pin["path"], expected_sha256=pin["sha256"],
                                           expected_identity=pin["identity_sha256"])
            geometry_cases[name] = (mesh_evidence(result) | shape_evidence(result)
                                     | independent_source_and_cut(result) | independent_continuous_bed(result))
            geometries[name] = result
        sp = gm["td_source"]
        source = load_diagnostic_product(sp["path"], expected_sha256=sp["sha256"], expected_identity=sp["identity_sha256"])
        source_path = source["metadata"]["terrain"]["source_path"]
        if not source_path or file_sha256(source_path) != sp["source_sha256"]:
            raise AssertionError("original TD file hash mismatch")
        td = geometries["td_fine"]
        ga, sa = td["arrays"], source["arrays"]
        np.testing.assert_array_equal(ga["source_height_m"], sa["elevation_m"])
        np.testing.assert_array_equal(ga["source_valid_mask"], sa["graph_valid_mask"])
        ids, receiver = ga["source_node_cell_ids"], ga["receiver"]
        edges = receiver >= 0
        np.testing.assert_array_equal(sa["graph_receiver"][ids[edges]], ids[receiver[edges]])
        owners = np.full(len(sa["graph_receiver"]), -1, np.int64)
        for cell in sa["graph_order_downstream_first"]:
            target = sa["graph_receiver"][cell]
            owners[cell] = cell if target < 0 else owners[target]
        np.testing.assert_array_equal(ga["owner_grid"], owners.reshape(sa["elevation_m"].shape))
        for name in ("td_bend_coarse", "td_bend_fine"):
            ba = geometries[name]["arrays"]
            np.testing.assert_array_equal(ba["source_height_m"], sa["elevation_m"])
            np.testing.assert_array_equal(ba["owner_grid"], owners.reshape(sa["elevation_m"].shape))
            bid, brec = ba["source_node_cell_ids"], ba["receiver"]
            np.testing.assert_array_equal(sa["graph_receiver"][bid[brec >= 0]], bid[brec[brec >= 0]])
        pool_pin = gm["td_lake_source"]
        if (pool_pin["sha256"] != "01e7db47838aafe6028f39520895ce8f758ce3d8989e4564822bdee3388677e5"
                or pool_pin["identity_sha256"] != "d485a50daded18e08db222cd07b4c23435aceb48f7007a3e3782d3367f863d42"
                or pool_pin["hierarchy_sha256"] != "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422"
                or pool_pin["hierarchy_identity_sha256"] != "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"):
            raise AssertionError("lake manifest does not match external frozen D4 and TD pins")
        pool_source = load_diagnostic_product(pool_pin["path"], expected_sha256=pool_pin["sha256"],
                                              expected_identity=pool_pin["identity_sha256"])
        hierarchy = load_basin_hierarchy(pool_pin["hierarchy_path"], expected_sha256=pool_pin["hierarchy_sha256"],
                                         expected_identity=pool_pin["hierarchy_identity_sha256"])
        pa = geometries["td_lake_fine"]["arrays"]
        np.testing.assert_array_equal(pa["source_height_m"], pool_source["arrays"]["elevation_m"])
        np.testing.assert_array_equal(pa["source_height_m"], hierarchy["arrays"]["height_m"])
        np.testing.assert_array_equal(pa["owner_grid"], hierarchy["arrays"]["contribution_owner"])
        np.testing.assert_array_equal(np.flatnonzero(pa["lake_mask"]), pool_pin["lake_support_cell_ids"])
        if np.any(pa["source_height_m"][pa["lake_mask"]] >= geometries["td_lake_fine"]["metadata"]["lake_stage_m"]):
            raise AssertionError("declared original lake support not wet at saved stage")
        wp = sm["td_water"]
        water = load_channel_product(sediment_directory / wp["path"], expected_sha256=wp["sha256"],
                                     expected_identity=wp["identity_sha256"])
        wa = water["arrays"]
        np.testing.assert_array_equal(wa["network_receiver"], receiver)
        edge_lengths = np.linalg.norm(np.diff(ga["node_xz_m"], axis=0), axis=1)
        lengths = np.r_[edge_lengths[0] / 2., (edge_lengths[:-1] + edge_lengths[1:]) / 2., edge_lengths[-1] / 2.]
        np.testing.assert_allclose(wa["network_length_m"], lengths, rtol=0., atol=1e-9)
        np.testing.assert_allclose(lengths.sum(), edge_lengths.sum(), rtol=0., atol=1e-9)
        np.testing.assert_allclose(wa["network_bed_elevation_m"], sample_saved_mesh(td, ga["node_xz_m"]), rtol=0., atol=1e-9)
        if water["metadata"]["network_source_identity_sha256"] != td["identity_sha256"]:
            raise AssertionError("new water geometry identity mismatch")
        original_local = sa["local_q_m3_s"].reshape(len(sa["time_seconds"]) - 1, -1)[:, ids]
        np.testing.assert_array_equal(wa["forcing_local_q_m3_s"], original_local)
        for name, pin in sm["artifacts"].items():
            if pin["path"] != name + ".npz":
                raise AssertionError("sediment artifact path outside expected package")
            result = load_sediment(sediment_directory / pin["path"], expected_sha256=pin["sha256"])
            if result["identity_sha256"] != pin["identity_sha256"]:
                raise AssertionError("sediment external identity mismatch")
            sediment_cases[name] = independent_sediment(result)
            if name.startswith("td_"):
                a, m = result["arrays"], result["metadata"]
                if m["geometry_identity_sha256"] != td["identity_sha256"] or m["hydraulic_identity_sha256"] != water["identity_sha256"]:
                    raise AssertionError("TD morphology parent identity mismatch")
                for target, parent in (("domain_receiver", "network_receiver"),
                                       ("domain_width_m", "network_width_m"),
                                       ("domain_bed_elevation_m", "network_bed_elevation_m"),
                                       ("forcing_time_seconds", "trace_time_seconds"),
                                       ("forcing_water_outflow_m3_s", "trace_outflow_q_m3_s")):
                    np.testing.assert_array_equal(a[target], wa[parent])
                np.testing.assert_array_equal(a["domain_bed_area_m2"], wa["network_width_m"] * wa["network_length_m"])
                np.testing.assert_array_equal(a["forcing_water_volume_m3"], wa["trace_volume_m3"][:-1])
                np.testing.assert_array_equal(a["forcing_water_depth_m"], wa["trace_depth_m"][:-1])
                np.testing.assert_array_equal(a["forcing_friction_slope"],
                                               np.broadcast_to(wa["network_bed_slope"], a["forcing_friction_slope"].shape))
        glb = verify_glb(geometry_directory / "td-river-bed.glb", len(ga["vertices_xz_m"]), len(ga["triangles"]))
        cold_preview(geometries, output)
        report = {"schema": "td-river-m5-m6-cold-v1", "status": "passed",
                  "disabled_entrypoints": list(DISABLED), "geometry_cases": geometry_cases,
                  "sediment_cases": sediment_cases, "geometry_count": len(geometry_cases),
                  "sediment_count": len(sediment_cases), "original_TD_source_verified": True,
                  "new_geometry_water_and_sediment_mapping_verified": True,
                  "same_source_D4_lake_connection_verified": True,
                  "disjoint_longitudinal_bed_controls_verified": True,
                  "selected_local_release_once_verified": True,
                  "geometry_manifest_sha256": file_sha256(geometry_directory / "acceptance.json"),
                  "sediment_manifest_sha256": file_sha256(sediment_directory / "acceptance.json"),
                  "glb": glb,
                  "code_sha256": {str(p): file_sha256(Path(__file__).resolve().parents[1] / p) for p in (
                      "terrain_pipeline/surface_rivers/metric_channel_geometry.py",
                      "terrain_pipeline/surface_rivers/metric_sediment.py",
                      "terrain_pipeline/surface_rivers/metric_bed_update.py",
                      "tools/verify_td_river_geometry.py", "tools/verify_td_river_sediment.py",
                      "tools/audit_td_river_geometry_sediment.py")},
                  "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
        publish_bytes(output / "cold-audit.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
        return report
    finally:
        for handle in reversed(active):
            handle.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--sediment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.geometry, args.sediment, args.output)
    print(json.dumps({key: report[key] for key in ("status", "geometry_count", "sediment_count")}, indent=2))


if __name__ == "__main__":
    main()
