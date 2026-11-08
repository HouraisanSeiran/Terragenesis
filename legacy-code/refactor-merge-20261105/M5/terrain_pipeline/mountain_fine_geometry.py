"""Independent fine transverse sections on original TD bilinear height samples."""

import math

import numpy as np

from terrain_pipeline.lake import GeometryBudget as GeometryBudget


FINE_SPACING_M = 1.0
WIDTH_M = 10.0
MAX_ATTEMPTS = 64
MAX_FINE_CELLS = 250000
MAX_CHAIN_SEGMENTS = 16
MIN_CHAIN_SEGMENTS = 3


def _sample(height, column, row):
    left = np.floor(column).astype(np.int64)
    top = np.floor(row).astype(np.int64)
    right = np.minimum(left + 1, height.shape[1] - 1)
    bottom = np.minimum(top + 1, height.shape[0] - 1)
    fraction_x = column - left
    fraction_z = row - top
    return ((1 - fraction_z) * ((1 - fraction_x) * height[top, left] + fraction_x * height[top, right])
            + fraction_z * ((1 - fraction_x) * height[bottom, left] + fraction_x * height[bottom, right]))


def prepare_fine_segment(result, donor, *, fine_spacing_m=FINE_SPACING_M, width_m=WIDTH_M):
    """Return complete strip evidence or refusal, not a whole-network certification."""
    arrays, metadata = result["arrays"], result["metadata"]
    height = arrays["H0_m"]
    if type(donor) is not int or not 0 <= donor < height.size:
        raise ValueError("invalid donor")
    if fine_spacing_m != FINE_SPACING_M or width_m != WIDTH_M:
        raise ValueError("fixed fine budget cannot be retuned after trial")
    receiver = int(arrays["receiver"][donor])
    if receiver < 0 or not arrays["accepted_mask"].flat[donor] or not arrays["accepted_mask"].flat[receiver]:
        raise ValueError("accepted connected segment required")
    if arrays["lake_mask"].flat[donor] or arrays["lake_mask"].flat[receiver]:
        raise ValueError("lake/spill requires separate fine seam design")
    spacing = metadata["spacing_m"]
    donor_row, donor_column = divmod(donor, height.shape[1])
    receiver_row, receiver_column = divmod(receiver, height.shape[1])
    delta_row = receiver_row - donor_row
    delta_column = receiver_column - donor_column
    if abs(delta_row) + abs(delta_column) != 1:
        raise ValueError("fine strip requires D4 full-edge segment")
    if spacing / fine_spacing_m % 1 or width_m / fine_spacing_m % 1:
        raise ValueError("strip dimensions must contain whole fine intervals")
    along = np.arange(int(spacing / fine_spacing_m) + 1) * fine_spacing_m
    across = np.arange(int(width_m / fine_spacing_m) + 1) * fine_spacing_m - width_m / 2
    if along.size * across.size > MAX_FINE_CELLS:
        raise ValueError("fine strip allocation resource limit")
    columns = donor_column + along[:, None] / spacing * delta_column - across[None, :] / spacing * delta_row
    rows = donor_row + along[:, None] / spacing * delta_row + across[None, :] / spacing * delta_column
    if (columns < 0).any() or (columns > height.shape[1] - 1).any() or (rows < 0).any() or (rows > height.shape[0] - 1).any():
        return {"status": "refused", "reason": "fine_strip_leaves_original_window", "donor": donor, "receiver": receiver}
    original = _sample(height, columns, rows)
    nearest_rows = np.floor(rows + .5).astype(np.int64)
    nearest_columns = np.floor(columns + .5).astype(np.int64)
    if (arrays["protected_mask"][nearest_rows, nearest_columns] | arrays["lake_mask"][nearest_rows, nearest_columns] | ~arrays["accepted_mask"][nearest_rows, nearest_columns]).any():
        return {"status": "refused", "reason": "fine_strip_crosses_protection_lake_or_unaccepted_group", "donor": donor, "receiver": receiver}
    donor_cut = float(arrays["cut_depth_m"].flat[donor])
    receiver_cut = float(arrays["cut_depth_m"].flat[receiver])
    center_cut = donor_cut + along / spacing * (receiver_cut - donor_cut)
    taper = .5 * (1 + np.cos(np.pi * across / (width_m / 2)))
    cut = center_cut[:, None] * taper[None, :]
    bed = original - cut
    center = across.size // 2
    center_bed = bed[:, center]
    flags = []
    budget = GeometryBudget(**metadata["budget"])
    if np.min(center_cut) <= 0:
        flags.append("zero_depth_endpoint")
    if (np.diff(center_bed) > 1e-9).any():
        flags.append("fine_center_bed_uphill")
    if (bed < center_bed[:, None] - 1e-9).any():
        flags.append("cross_section_not_valley_minimum")
    if cut.max() > budget.max_total_cut_m + 1e-9:
        flags.append("fine_cut_depth_budget")
    weights = np.ones(cut.shape)
    weights[0, :] *= .5
    weights[-1, :] *= .5
    weights[:, 0] *= .5
    weights[:, -1] *= .5
    volume = float((cut * weights).sum() * fine_spacing_m ** 2)
    remaining = budget.max_cut_volume_m3
    if volume > remaining + 1e-9:
        flags.append("independent_fine_volume_budget")
    origin_x, origin_z = metadata["origin_m_xz"]
    return {"status": "accepted_fine_local_geometry" if not flags else "refused", "reason_flags": flags,
            "donor": donor, "receiver": receiver, "width_m": width_m, "fine_spacing_m": fine_spacing_m,
            "fine_cells": int(cut.size), "cut_volume_m3": volume, "remaining_coarse_budget_m3": remaining,
            "scope": "independent_alternative_local_strip_not_added_to_or_merged_into_coarse_surface",
            "arrays": {"along_m": along, "across_m": across,
                       "world_x_m": origin_x + columns * spacing, "world_z_m": origin_z + rows * spacing,
                       "H0_m": original, "H1_m": original.copy(), "H2_m": bed,
                       "cut_depth_m": cut, "quadrature_area_m2": weights * fine_spacing_m ** 2,
                       "center_bed_m": center_bed}}


def select_fine_geometry(result):
    """Deterministic depth-first ranking; retain all failed attempted segments."""
    arrays = result["arrays"]
    receiver = arrays["receiver"]
    donors = np.flatnonzero(arrays["accepted_mask"].ravel() & arrays["dry_channel_mask"].ravel()
                            & (arrays["cut_depth_m"].ravel() > 0) & (receiver >= 0))
    targets = receiver[donors]
    eligible = ~arrays["lake_mask"].ravel()[targets] & (arrays["cut_depth_m"].ravel()[targets] > 0)
    donors = donors[eligible]
    ranking = np.lexsort((donors, -arrays["contributing_area_m2"].ravel()[donors]))
    evidence = []
    spent = 0
    accepted = None
    for donor in donors[ranking][:MAX_ATTEMPTS]:
        trial = prepare_fine_segment(result, int(donor))
        spent += trial.get("fine_cells", 0)
        if spent > MAX_FINE_CELLS:
            raise ValueError("fine attempt resource budget exceeded")
        evidence.append({key: value for key, value in trial.items() if key != "arrays"})
        if trial["status"] == "accepted_fine_local_geometry":
            accepted = trial
            break
    return {"attempts": evidence, "fine_cells": spent, "max_attempts": MAX_ATTEMPTS,
            "max_fine_cells": MAX_FINE_CELLS, "accepted": accepted}


def select_continuous_fine_geometry(result):
    """Straight D4 chain, exact shared cross sections and explicit local receiving seam."""
    arrays = result["arrays"]
    receiver = arrays["receiver"]
    donors = np.flatnonzero(arrays["accepted_mask"].ravel() & arrays["dry_channel_mask"].ravel()
                            & (arrays["cut_depth_m"].ravel() > 0) & (receiver >= 0))
    ranking = np.lexsort((donors, -arrays["contributing_area_m2"].ravel()[donors]))
    candidates = []
    for start in donors[ranking]:
        chain = [int(start)]
        direction = int(receiver[start] - start)
        while len(chain) <= MAX_CHAIN_SEGMENTS:
            target = int(receiver[chain[-1]])
            if (target < 0 or target - chain[-1] != direction or arrays["lake_mask"].flat[target]
                    or not arrays["accepted_mask"].flat[target] or arrays["cut_depth_m"].flat[target] <= 0):
                break
            chain.append(target)
        if len(chain) - 1 >= MIN_CHAIN_SEGMENTS:
            candidates.append(chain)
        if len(candidates) >= MAX_ATTEMPTS:
            break
    attempts = []
    spent = 0
    for chain in candidates:
        strips = []
        flags = []
        for cell in chain[:-1]:
            trial = prepare_fine_segment(result, cell)
            spent += trial.get("fine_cells", 0)
            if spent > MAX_FINE_CELLS:
                flags.append("total_fine_resource_limit")
                break
            if trial["status"] != "accepted_fine_local_geometry":
                flags.extend(trial.get("reason_flags", [trial.get("reason", "refused")]))
                break
            strips.append(trial)
        if flags:
            attempts.append({"chain_cells": chain, "status": "refused", "reason_flags": flags})
            if "total_fine_resource_limit" in flags:
                break
            continue
        for before, after in zip(strips[:-1], strips[1:]):
            for key in ("world_x_m", "world_z_m", "H0_m", "H1_m", "H2_m"):
                if not np.allclose(before["arrays"][key][-1], after["arrays"][key][0], rtol=0., atol=1e-10):
                    raise ValueError("continuous chain shared section mismatch")
        fields = {}
        for key in ("world_x_m", "world_z_m", "H0_m", "H1_m", "H2_m", "cut_depth_m"):
            fields[key] = np.concatenate([strip["arrays"][key][:-1] for strip in strips] + [strips[-1]["arrays"][key][-1:]], axis=0)
        fields["across_m"] = strips[0]["arrays"]["across_m"].copy()
        fields["along_m"] = np.arange(fields["H0_m"].shape[0]) * FINE_SPACING_M
        fields["chain_cells"] = np.asarray(chain, dtype=np.int64)
        weights = np.ones(fields["H0_m"].shape)
        weights[0] *= .5
        weights[-1] *= .5
        weights[:, 0] *= .5
        weights[:, -1] *= .5
        fields["quadrature_area_m2"] = weights * FINE_SPACING_M ** 2
        volume = float((fields["cut_depth_m"] * fields["quadrature_area_m2"]).sum())
        fields["shared_node_section_rows"] = np.arange(1, len(chain) - 1, dtype=np.int64) * int(result["metadata"]["spacing_m"] / FINE_SPACING_M)
        accepted = {"status": "accepted_continuous_local_fine_chain", "arrays": fields,
                    "segments": len(chain) - 1, "length_m": float(fields["along_m"][-1]),
                    "cut_volume_m3": volume, "width_m": WIDTH_M, "fine_spacing_m": FINE_SPACING_M,
                    "receiving_cell": chain[-1], "receiving_type": "explicit_local_geometry_seam_not_hydrologic_outlet",
                    "scope": "independent_fine_alternative_not_added_to_coarse_or_certified_as_full_forest",
                    "full_window_upstream_area_m2": float(arrays["contributing_area_m2"].flat[chain[0]])}
        attempts.append({"chain_cells": chain, "status": accepted["status"], "reason_flags": []})
        return {"accepted": accepted, "attempts": attempts, "fine_cells": spent,
                "max_attempts": MAX_ATTEMPTS, "max_chain_segments": MAX_CHAIN_SEGMENTS}
    return {"accepted": None, "attempts": attempts, "fine_cells": spent,
            "max_attempts": MAX_ATTEMPTS, "max_chain_segments": MAX_CHAIN_SEGMENTS}


def validate_fine_chain(chain, geometry):
    """Static original-source sampling and cut equations; never select or prepare."""
    source, metadata = geometry["arrays"], geometry["metadata"]
    arrays = chain["arrays"]
    expected_keys = {"world_x_m", "world_z_m", "H0_m", "H1_m", "H2_m", "cut_depth_m",
                     "across_m", "along_m", "chain_cells", "quadrature_area_m2", "shared_node_section_rows"}
    if set(arrays) != expected_keys or chain["fine_spacing_m"] != FINE_SPACING_M or chain["width_m"] != WIDTH_M:
        raise ValueError("fixed fine chain schema")
    cells = arrays["chain_cells"]
    if cells.dtype != np.dtype("int64") or cells.ndim != 1 or not MIN_CHAIN_SEGMENTS <= cells.size - 1 <= MAX_CHAIN_SEGMENTS:
        raise ValueError("bounded chain node identities")
    if chain["segments"] != cells.size - 1 or chain["length_m"] != (cells.size - 1) * metadata["spacing_m"] or chain["receiving_cell"] != int(cells[-1]):
        raise ValueError("fine metadata segment/length/receiver identity")
    if (cells < 0).any() or (cells >= source["H0_m"].size).any() or not np.array_equal(source["receiver"][cells[:-1]], cells[1:]):
        raise ValueError("fine chain source topology")
    width = source["H0_m"].shape[1]
    delta_rows = np.diff(cells // width)
    delta_columns = np.diff(cells % width)
    if (np.abs(delta_rows) + np.abs(delta_columns) != 1).any() or np.ptp(delta_rows) or np.ptp(delta_columns):
        raise ValueError("straight full-D4 chain required")
    if (source["lake_mask"].ravel()[cells] | source["protected_mask"].ravel()[cells] | ~source["accepted_mask"].ravel()[cells]).any():
        raise ValueError("fine chain source acceptance/protection")
    spacing = metadata["spacing_m"]
    along = np.arange(int((cells.size - 1) * spacing / FINE_SPACING_M) + 1) * FINE_SPACING_M
    across = np.arange(int(WIDTH_M / FINE_SPACING_M) + 1) * FINE_SPACING_M - WIDTH_M / 2
    if along.size * across.size > MAX_FINE_CELLS:
        raise ValueError("fine chain resource limit")
    def equal(actual, expected, name):
        if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0., atol=1e-10):
            raise ValueError("static fine chain mismatch: " + name)
    equal(arrays["along_m"], along, "longitudinal coordinates")
    equal(arrays["across_m"], across, "transverse coordinates")
    start_row, start_column = divmod(int(cells[0]), width)
    columns = start_column + along[:, None] / spacing * delta_columns[0] - across[None, :] / spacing * delta_rows[0]
    rows = start_row + along[:, None] / spacing * delta_rows[0] + across[None, :] / spacing * delta_columns[0]
    if (columns < 0).any() or (columns > width - 1).any() or (rows < 0).any() or (rows > source["H0_m"].shape[0] - 1).any():
        raise ValueError("fine chain leaves original sample")
    equal(arrays["world_x_m"], metadata["origin_m_xz"][0] + columns * spacing, "source X")
    equal(arrays["world_z_m"], metadata["origin_m_xz"][1] + rows * spacing, "source Z")
    nearest_rows = np.floor(rows + .5).astype(np.int64)
    nearest_columns = np.floor(columns + .5).astype(np.int64)
    if (source["protected_mask"][nearest_rows, nearest_columns] | source["lake_mask"][nearest_rows, nearest_columns] | ~source["accepted_mask"][nearest_rows, nearest_columns]).any():
        raise ValueError("full strip source protection/lake/acceptance mask")
    original = _sample(source["H0_m"], columns, rows)
    equal(arrays["H0_m"], original, "true bilinear H0")
    equal(arrays["H1_m"], original, "unchanged fine H1")
    center_cut = np.interp(along, np.arange(cells.size) * spacing, source["cut_depth_m"].ravel()[cells])
    taper = .5 * (1 + np.cos(np.pi * across / (WIDTH_M / 2)))
    expected_cut = center_cut[:, None] * taper[None, :]
    equal(arrays["cut_depth_m"], expected_cut, "cosine cut and shared node endpoints")
    equal(arrays["H2_m"], original - expected_cut, "source-linked bed")
    weights = np.ones(original.shape)
    weights[0] *= .5
    weights[-1] *= .5
    weights[:, 0] *= .5
    weights[:, -1] *= .5
    equal(arrays["quadrature_area_m2"], weights * FINE_SPACING_M ** 2, "unique quadrature")
    equal(arrays["shared_node_section_rows"], np.arange(1, cells.size - 1) * int(spacing / FINE_SPACING_M), "shared section identities")
    center = original.shape[1] // 2
    if (np.diff(arrays["H2_m"][:, center]) > 1e-9).any() or (arrays["H2_m"] < arrays["H2_m"][:, center:center + 1] - 1e-9).any():
        raise ValueError("fine longitudinal or transverse geometry failure")
    volume = float((expected_cut * arrays["quadrature_area_m2"]).sum())
    if abs(volume - chain["cut_volume_m3"]) > 1e-9 or volume > metadata["budget"]["max_cut_volume_m3"] or expected_cut.max() > metadata["budget"]["max_total_cut_m"]:
        raise ValueError("fine independent budget failure")
    return {"cut_volume_m3": volume, "length_m": float(along[-1]),
            "minimum_endpoint_bank_margin_m": float(np.min(np.minimum(arrays["H2_m"][:, 0], arrays["H2_m"][:, -1]) - arrays["H2_m"][:, center]))}
