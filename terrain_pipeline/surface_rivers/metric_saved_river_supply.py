from __future__ import annotations

from typing import Any, Dict

import numpy as np

from terrain_pipeline.runoff import MONTH_DAYS as MONTH_DAYS
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import _shore_segment as _shore_segment
from terrain_pipeline.lake import contribution_mask as contribution_mask
from terrain_pipeline.lake import terminal_ownership as terminal_ownership


def _as_int_id(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be integer, not bool")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, int):
        return value
    raise TypeError(f"{name} must be integer, got {type(value)!r}")


def partition_saved_supply(
    parent_plan: Dict[str, Any],
    column_plan: Dict[str, Any],
    *,
    source_node: int = 8470,
    receiver_node: int = 8600,
) -> Dict[str, Any]:
    source_node = _as_int_id(source_node, "source_node")
    receiver_node = _as_int_id(receiver_node, "receiver_node")

    receiver = np.asarray(parent_plan["receiver"])
    if receiver.dtype != np.int64 or receiver.ndim != 2:
        raise TypeError("parent receiver must be int64 2D")
    parent_owner = np.asarray(parent_plan["owner_domain_id"])
    ocean_mask = np.asarray(parent_plan["ocean_mask"])
    shape = receiver.shape

    if parent_owner.shape != shape:
        raise ValueError(f"parent_owner shape {parent_owner.shape} != expected {shape}")
    if ocean_mask.shape != shape:
        raise ValueError(f"ocean_mask shape {ocean_mask.shape} != expected {shape}")
    if parent_owner.ndim != 2:
        raise ValueError("parent_owner must be 2D")
    if parent_owner.dtype.kind not in "iu":
        raise TypeError("parent_owner must have integer dtype")
    if ocean_mask.dtype != np.bool_:
        raise TypeError("ocean_mask must have bool dtype")

    spacing = float(parent_plan["spacing_m"])
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("spacing_m must be positive finite")

    col_owner = np.asarray(column_plan["owner_domain_id"])
    col_parent = np.asarray(column_plan["seasonal_parent_cell_id"])
    col_area = np.asarray(column_plan["seasonal_column_area_m2"], dtype=float)
    if col_owner.ndim != 2:
        raise ValueError("col_owner must be 2D")
    if col_parent.shape != col_owner.shape:
        raise ValueError(f"col_parent shape {col_parent.shape} != col_owner shape {col_owner.shape}")
    if col_area.shape != col_owner.shape:
        raise ValueError(f"col_area shape {col_area.shape} != col_owner shape {col_owner.shape}")
    if col_owner.dtype.kind not in "iu":
        raise TypeError("col_owner must have integer dtype")
    if col_parent.dtype.kind not in "iu":
        raise TypeError("col_parent must have integer dtype")
    if not np.all(np.isfinite(col_area)) or np.any(col_area <= 0.0):
        raise ValueError("column area must be positive finite")

    valid_ids = np.unique(col_parent)
    if valid_ids.size and (valid_ids[0] < 0 or valid_ids[-1] >= receiver.size):
        raise ValueError("column parent ids out of bounds")
    owner_at_col_parent = parent_owner.ravel()[col_parent.ravel()]
    if not np.array_equal(owner_at_col_parent, col_owner.ravel()):
        raise ValueError("column owner differs from parent owner at parent cell")

    source_flat = int(source_node)
    if not (0 <= source_flat < receiver.size):
        raise ValueError("source node out of bounds")
    source_domain = int(parent_owner.ravel()[source_flat])

    domains = parent_plan["domains"]
    coastal = [d for d in domains
               if int(d["domain_id"]) == source_domain and d["kind"] == "coastal"]
    if len(coastal) != 1:
        raise ValueError("expected exactly one coastal domain matching source owner")
    domain = coastal[0]
    domain_id = int(domain["domain_id"])
    terminals = np.asarray(domain["terminal_indices"])
    if terminals.ndim != 1:
        raise ValueError("terminal_indices must be 1D")
    if terminals.dtype.kind not in "iu":
        raise TypeError("terminal_indices must have integer dtype")
    if terminals.size == 0:
        raise ValueError("coastal domain has no terminals")
    if np.unique(terminals).size != terminals.size:
        raise ValueError("terminal ids must be unique")
    terminals = terminals.astype(np.int64)
    if np.any(terminals < 0) or np.any(terminals >= receiver.size):
        raise ValueError("terminal id out of bounds")
    if not np.all(ocean_mask.ravel()[terminals]):
        raise ValueError("all terminals must be ocean")
    if np.any(parent_owner.ravel()[terminals] >= 0):
        raise ValueError("terminal cells must have owner < 0")
    if np.any(receiver.ravel()[terminals] != -1):
        raise ValueError("terminal cells must have receiver -1")
    if bool(ocean_mask.ravel()[source_flat]):
        raise ValueError("source must not be ocean")
    if int(parent_owner.ravel()[source_flat]) < 0:
        raise ValueError("source must belong to a coastal domain")
    if not (0 <= receiver_node < receiver.size):
        raise ValueError("receiver_node out of bounds")
    if not np.any(terminals == receiver_node):
        raise ValueError("receiver_node must be a declared terminal")
    if int(receiver.ravel()[source_flat]) != receiver_node:
        raise ValueError("source receiver link does not match receiver_node")

    land = parent_owner == domain_id
    if np.any(land & ocean_mask):
        raise ValueError("land and ocean overlap")
    active = land.copy()
    active.ravel()[terminals] = True

    partition = terminal_ownership(receiver, active)
    terminal_parent_owner = np.asarray(partition["terminal_owner"])
    flat_owner = terminal_parent_owner.ravel()
    actual_terminals = np.asarray(partition["terminal_flat"], dtype=np.int64)
    if set(actual_terminals.tolist()) != set(terminals.tolist()):
        raise ValueError("terminal ids mismatch")
    if int(flat_owner[source_flat]) != receiver_node:
        raise ValueError("source terminal_owner mismatch")

    cut = receiver.copy()
    cut.ravel()[source_flat] = -1
    selected, _unused_audit = contribution_mask(cut, active, int(source_node))
    if not bool(np.any(selected)):
        raise ValueError("source contributes to no cells")
    if not bool(np.all(land[selected])):
        raise ValueError("selected cells must be land")
    if not bool(np.all(flat_owner[selected.ravel()] == receiver_node)):
        raise ValueError("selected cells must reach receiver terminal")

    coastal_cols = col_owner.ravel() == domain_id
    parent_ids = col_parent.ravel()
    area_flat = col_area.ravel()
    coastal_parents = np.unique(parent_ids[coastal_cols])
    if not np.array_equal(coastal_parents, np.flatnonzero(land.ravel())):
        raise ValueError("coastal coverage incomplete or extraneous")
    agg = np.bincount(parent_ids[coastal_cols], weights=area_flat[coastal_cols],
                      minlength=receiver.size)
    if not np.allclose(agg[land.ravel()], spacing * spacing, rtol=1e-12, atol=1e-7):
        raise ValueError("saved column areas do not match cell area")

    column_terminal = flat_owner[parent_ids]
    terminal_masks = np.stack([coastal_cols & (column_terminal == t) for t in terminals])
    if not bool(np.all(terminal_masks.sum(axis=0, dtype=np.int64) == coastal_cols.astype(np.int64))):
        raise ValueError("terminal masks must partition coastal columns")
    selected_cols = coastal_cols & selected.ravel()[parent_ids]
    receiver_index = int(np.flatnonzero(terminals == receiver_node)[0])
    if bool(np.any(selected_cols & ~terminal_masks[receiver_index])):
        raise ValueError("selected columns must reach receiver terminal")

    return {
        "terminal_ids": terminals.copy(),
        "terminal_parent_owner": terminal_parent_owner.copy(),
        "selected_parent_mask": selected.reshape(shape).copy(),
        "coastal_column_mask": coastal_cols.copy(),
        "terminal_column_masks": terminal_masks.copy(),
        "selected_column_mask": selected_cols.copy(),
        "other_receiver_column_mask": terminal_masks[receiver_index] & ~selected_cols,
        "coastal_domain_id": domain_id,
        "receiver_terminal_column": receiver_index,
        "source_node": source_node,
        "receiver_node": receiver_node,
    }


def replay_saved_supply(partition, column_plan, climate, saved, config):
    coast = partition["coastal_column_mask"]
    area = column_plan["seasonal_column_area_m2"].ravel()[coast]
    rainmonths = climate["precipitation_mm"].reshape(12, -1)[:, coast]
    petmonths = climate["potential_et_mm"].reshape(12, -1)[:, coast]
    savedsoil = saved["soil_mm"].reshape(13, -1)[:, coast]
    masks = partition["terminal_column_masks"][:, coast]
    selected = partition["selected_column_mask"][coast]
    dcol = saved["domain_ids"].index(partition["coastal_domain_id"])
    substeps = int(config.substeps_per_day)
    dt_days = 1.0 / substeps
    dt_s = dt_days * 86400.0
    nstep = int(sum(MONTH_DAYS)) * substeps
    rtol = 1e-9
    soil_atol = 1e-9
    ledger_base = saved["steps"]["land_rain_m3"] + saved["steps"]["lake_rain_m3"]
    ledger_atol = max(1e-7, float(np.max(ledger_base)) * 1e-9)
    T, ncoast = masks.shape
    if not (np.all(np.isfinite(rainmonths)) and np.all(rainmonths >= 0.0)):
        raise ValueError("rainmonths must be finite and nonnegative")
    if not (np.all(np.isfinite(petmonths)) and np.all(petmonths >= 0.0)):
        raise ValueError("petmonths must be finite and nonnegative")
    if not (np.all(np.isfinite(savedsoil)) and np.all(savedsoil >= 0.0) and np.all(savedsoil <= config.soil_capacity_mm + 1e-9)):
        raise ValueError("savedsoil must be finite and within [0, soil_capacity_mm]")
    if not (np.all(np.isfinite(area)) and np.all(area > 0.0)):
        raise ValueError("area must be finite and positive")
    if not np.any(selected):
        raise ValueError("selected must contain at least one True value")
    terminalsoil = savedsoil[0].copy()
    selectedsoil = terminalsoil[selected].copy()
    terminalvol = np.zeros((nstep, T), dtype=float)
    selectedvol = np.zeros(nstep, dtype=float)
    monthterminal = np.zeros((12, T), dtype=float)
    monthselected = np.zeros(12, dtype=float)
    soilmonth = np.zeros((13, ncoast), dtype=float)
    soilmonth[0] = terminalsoil
    max_step_res = 0.0
    max_month_soil_res = 0.0
    max_month_outflow_res = 0.0
    k = 0
    for month, days in enumerate(MONTH_DAYS):
        start = k
        rain = rainmonths[month] / float(days)
        pet = petmonths[month] / float(days)
        substep_count = int(days) * substeps

        for _ in range(substep_count):
            for j in range(T):
                mask = masks[j]
                nm = int(np.sum(mask))
                if nm == 0:
                    terminalvol[k, j] = 0.0
                    continue
                after, unused_volume, ledger = _shore_segment(
                    terminalsoil[mask],
                    0.0,
                    rain[mask],
                    pet[mask],
                    area[mask],
                    np.zeros(nm, dtype=float),
                    dt_days,
                    config,
                )
                terminalsoil[mask] = after
                terminalvol[k, j] = float(ledger["runoff_to_terminal_m3"])
            nm_sel = int(np.sum(selected))
            if nm_sel > 0:
                after_s, unused_s, ledger_s = _shore_segment(
                    selectedsoil,
                    0.0,
                    rain[selected],
                    pet[selected],
                    area[selected],
                    np.zeros(nm_sel, dtype=float),
                    dt_days,
                    config,
                )
                selectedsoil = after_s
                selectedvol[k] = float(ledger_s["runoff_to_terminal_m3"])
            else:
                selectedvol[k] = 0.0
            k += 1
        soilmonth[month + 1] = terminalsoil
        ref = savedsoil[month + 1]
        if not np.allclose(terminalsoil, ref, rtol=rtol, atol=soil_atol):
            raise ValueError("coastal soil mismatch at month %d" % (month + 1,))
        if nm_sel > 0 and not np.allclose(selectedsoil, terminalsoil[selected], rtol=rtol, atol=soil_atol):
            raise ValueError("selected soil mismatch at month %d" % (month + 1,))
        resid = float(np.max(np.abs(terminalsoil - ref)))
        if resid > max_month_soil_res:
            max_month_soil_res = resid
        monthterminal[month] = terminalvol[start:k].sum(axis=0)
        monthselected[month] = float(selectedvol[start:k].sum())
    saved_out = saved["steps"]["coastal_outflow_m3"][:, dcol]
    saved_run = saved["steps"]["runoff_to_terminal_m3"][:, dcol]
    col_out = terminalvol.sum(axis=1)
    if not np.allclose(col_out, saved_out, rtol=rtol, atol=ledger_atol):
        raise ValueError("coastal_outflow step mismatch")
    if not np.allclose(col_out, saved_run, rtol=rtol, atol=ledger_atol):
        raise ValueError("runoff_to_terminal step mismatch")
    max_step_res = float(np.max(np.abs(col_out - saved_out)))
    m_out = monthterminal.sum(axis=1)
    m_run = monthterminal.sum(axis=1)
    sm_out = saved["monthly"]["coastal_outflow_m3"][:, dcol]
    sm_run = saved["monthly"]["runoff_to_terminal_m3"][:, dcol]
    if not np.allclose(m_out, sm_out, rtol=rtol, atol=ledger_atol):
        raise ValueError("coastal_outflow monthly mismatch")
    if not np.allclose(m_run, sm_run, rtol=rtol, atol=ledger_atol):
        raise ValueError("runoff_to_terminal monthly mismatch")
    max_month_outflow_res = float(np.max(np.abs(m_out - sm_out)))
    receiverindex = int(partition["receiver_terminal_column"])
    othervol = terminalvol[:, receiverindex] - selectedvol
    otherlim = ledger_atol + rtol * np.abs(terminalvol[:, receiverindex])
    if np.any(othervol < -otherlim):
        raise ValueError("other receiver volume deficit")
    monthother = monthterminal[:, receiverindex] - monthselected
    annual_terminal = monthterminal.sum(axis=0)
    annual_selected = np.array(monthselected.sum())
    annual_other = np.array(monthother.sum())
    step_start_s = np.arange(nstep, dtype=float) * dt_s
    step_end_s = step_start_s + dt_s
    terminal_q = terminalvol / dt_s
    selected_q = selectedvol / dt_s
    other_q = othervol / dt_s
    audit = {
        "rtol": rtol,
        "ledger_atol_m3": ledger_atol,
        "soil_atol_mm": soil_atol,
        "max_step_outflow_residual_m3": max_step_res,
        "max_month_soil_residual_mm": max_month_soil_res,
        "max_month_outflow_residual_m3": max_month_outflow_res,
    }
    return {
        "step_start_s": step_start_s,
        "step_end_s": step_end_s,
        "terminal_volume_m3": terminalvol,
        "terminal_q_m3_s": terminal_q,
        "selected_volume_m3": selectedvol,
        "selected_q_m3_s": selected_q,
        "other_receiver_volume_m3": othervol,
        "other_receiver_q_m3_s": other_q,
        "monthly_terminal_volume_m3": monthterminal,
        "monthly_selected_volume_m3": monthselected,
        "monthly_other_receiver_volume_m3": monthother,
        "annual_terminal_volume_m3": annual_terminal,
        "annual_selected_volume_m3": annual_selected,
        "annual_other_receiver_volume_m3": annual_other,
        "coastal_soil_month_mm": soilmonth,
        "audit": audit,
    }

