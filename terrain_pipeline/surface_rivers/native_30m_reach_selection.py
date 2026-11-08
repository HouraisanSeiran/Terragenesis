import numpy as np
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge


def select_from_topology(elevation_m, topology, *, origin_native_xz, min_stem_m=2000.0, min_catchment_cells=256, contact_margin_cells=6, max_nodes=120, max_stride=8, max_catchment_cells=13000, max_subwindow_cells=250000, terminal_native_xz=None):
    mesh = _validate_selection(elevation_m, topology, origin_native_xz, min_stem_m, (min_catchment_cells, contact_margin_cells, max_nodes, max_stride, max_catchment_cells, max_subwindow_cells))
    rec = topology['receiver']
    valid = topology['valid_mask']
    rows, cols = rec.shape
    cell_size_m = 30.0
    local = np.where(valid, 1.0, 0.0).astype(np.float64)
    seed = topology['upstream_unknown_mask'].copy()
    seed[:contact_margin_cells, :] |= valid[:contact_margin_cells, :]
    seed[-contact_margin_cells:, :] |= valid[-contact_margin_cells:, :]
    seed[:, :contact_margin_cells] |= valid[:, :contact_margin_cells]
    seed[:, -contact_margin_cells:] |= valid[:, -contact_margin_cells:]
    ledger = accumulate_network_discharge(
        rec, local, valid,
        terminal_kind=topology['terminal_kind'],
        upstream_unknown_mask=seed,
    )
    counts = ledger['known_routed_q_m3_s']
    complete = ledger['complete_mask']
    src = np.flatnonzero((rec.ravel() >= 0) & valid.ravel())
    targets = rec.ravel()[src]
    order = np.argsort(targets, kind='stable')
    donors = src[order]
    targets_sorted = targets[order]
    indptr = np.searchsorted(targets_sorted, np.arange(rec.size + 1))

    terminals = np.flatnonzero(valid.ravel() & (rec.ravel() < 0))
    candidates = []
    for tf in terminals:
        members = []
        stack = [int(tf)]
        seen_local = set()
        while stack:
            cur = stack.pop()
            if cur in seen_local:
                continue
            seen_local.add(cur)
            members.append(cur)
            lo, hi = int(indptr[cur]), int(indptr[cur + 1])
            for d in donors[lo:hi]:
                stack.append(int(d))
        if not members:
            continue
        if any((not complete.ravel()[m]) for m in members):
            candidates.append({'terminal': int(tf), 'count': int(counts.ravel()[tf]), 'accepted': False, 'reason': 'catchment_not_complete'})
            continue
        c = int(counts.ravel()[tf])
        # 6-cell clearance check via bbox dilation
        mr = np.array([m // cols for m in members], dtype=np.int64)
        mc = np.array([m % cols for m in members], dtype=np.int64)
        r0 = max(0, int(mr.min()) - contact_margin_cells)
        r1 = min(rows, int(mr.max()) + contact_margin_cells + 1)
        c0 = max(0, int(mc.min()) - contact_margin_cells)
        c1 = min(cols, int(mc.max()) + contact_margin_cells + 1)
        if (r1 - r0) < contact_margin_cells or (c1 - c0) < contact_margin_cells:
            candidates.append({'terminal': int(tf), 'count': c, 'accepted': False, 'reason': 'catchment_not_complete'})
            continue
        if c < min_catchment_cells or c > max_catchment_cells:
            candidates.append({'terminal': int(tf), 'count': c, 'accepted': False, 'reason': 'small_or_budget'})
            continue
        # main stem path from terminal via donors, choose max counts, tie min id
        path = [int(tf)]
        cur = int(tf)
        while True:
            lo, hi = int(indptr[cur]), int(indptr[cur + 1])
            ups = donors[lo:hi]
            ups = ups[(rec.ravel()[ups] == cur) & valid.ravel()[ups]]
            if ups.size == 0:
                break
            best = None
            best_count = -1
            best_id = None
            for u in ups:
                ui = int(u)
                uc = int(counts.ravel()[ui])
                if uc > best_count or (uc == best_count and (best_id is None or ui < best_id)):
                    best_count = uc
                    best_id = ui
                    best = ui
            if best is None:
                break
            path.append(best)
            cur = best
        path = path[::-1]
        plen = 0.0
        for i in range(len(path) - 1):
            r_a, c_a = divmod(path[i], cols)
            r_b, c_b = divmod(path[i + 1], cols)
            plen += float(np.hypot(mesh.node_x_m[path[i]] - mesh.node_x_m[path[i + 1]],
                                   mesh.node_z_m[path[i]] - mesh.node_z_m[path[i + 1]]))
        if plen < min_stem_m:
            candidates.append({'terminal': int(tf), 'count': c, 'accepted': False, 'reason': 'stem_too_short'})
            continue
        stride_ok = None
        for s in range(1, max_stride + 1):
            idx = np.r_[np.arange(0, len(path) - 1, s), len(path) - 1]
            if len(np.unique(idx)) <= max_nodes:
                stride_ok = int(s)
                break
        if stride_ok is None:
            candidates.append({'terminal': int(tf), 'count': c, 'accepted': False, 'reason': 'nodes_over_budget'})
            continue
        sub_r0 = max(0, r0 - 12)
        sub_r1 = min(rows, r1 + 12)
        sub_c0 = max(0, c0 - 12)
        sub_c1 = min(cols, c1 + 12)
        sub_area = int((sub_r1 - sub_r0) * (sub_c1 - sub_c0))
        if sub_area > max_subwindow_cells:
            candidates.append({'terminal': int(tf), 'count': c, 'accepted': False, 'reason': 'subwindow_over_budget'})
            continue
        candidates.append({'terminal': int(tf), 'count': c, 'accepted': True, 'reason': None})
    if not candidates:
        raise ValueError('no_complete_reach')
    accepted = [x for x in candidates if x['accepted']]
    if not accepted:
        raise ValueError('no_complete_reach')
    accepted.sort(key=lambda x: (-x['count'], x['terminal']))
    if terminal_native_xz is None:
        chosen = accepted[0]
    else:
        if not isinstance(terminal_native_xz, (list, tuple)) or len(terminal_native_xz) != 2:
            raise ValueError('terminal_native_xz_must_be_2_sequence')
        tx, tz = terminal_native_xz
        if (not isinstance(tx, (int, np.integer)) or isinstance(tx, (bool, np.bool_))
                or not isinstance(tz, (int, np.integer)) or isinstance(tz, (bool, np.bool_))):
            raise ValueError('terminal_native_xz_must_be_int_pair')
        cc = int(tx) - int(origin_native_xz[0])
        rr = int(tz) - int(origin_native_xz[1])
        if rr < 0 or rr >= rows or cc < 0 or cc >= cols:
            raise ValueError('terminal_outside_window')
        flat = rr * cols + cc
        matched = None
        for candidate in candidates:
            if int(candidate['terminal']) == int(flat):
                matched = candidate
                break
        if matched is None:
            raise ValueError('requested_terminal_not_candidate')
        if not matched.get('accepted'):
            raise ValueError('requested_terminal_rejected:' + str(matched.get('reason')))
        chosen = matched
    tf = int(chosen['terminal'])
    # rebuild catchment members for chosen
    members = []
    stack = [tf]
    seen_local = set()
    while stack:
        cur = stack.pop()
        if cur in seen_local:
            continue
        seen_local.add(cur)
        members.append(cur)
        lo, hi = int(indptr[cur]), int(indptr[cur + 1])
        for d in donors[lo:hi]:
            stack.append(int(d))
    members = np.array(members, dtype=np.int64)
    # stem path
    path = [tf]
    cur = tf
    while True:
        lo, hi = int(indptr[cur]), int(indptr[cur + 1])
        ups = donors[lo:hi]
        ups = ups[(rec.ravel()[ups] == cur) & valid.ravel()[ups]]
        if ups.size == 0:
            break
        best = None
        best_count = -1
        best_id = None
        for u in ups:
            ui = int(u)
            uc = int(counts.ravel()[ui])
            if uc > best_count or (uc == best_count and (best_id is None or ui < best_id)):
                best_count = uc
                best_id = ui
                best = ui
        if best is None:
            break
        path.append(best)
        cur = best
    path = path[::-1]
    plen_m = 0.0
    for i in range(len(path) - 1):
        r_a, c_a = divmod(path[i], cols)
        r_b, c_b = divmod(path[i + 1], cols)
        plen_m += float(np.hypot(mesh.node_x_m[path[i]] - mesh.node_x_m[path[i + 1]],
                                 mesh.node_z_m[path[i]] - mesh.node_z_m[path[i + 1]]))
    mr = np.array([m // cols for m in members], dtype=np.int64)
    mc = np.array([m % cols for m in members], dtype=np.int64)
    r0 = max(0, int(mr.min()) - contact_margin_cells)
    r1 = min(rows, int(mr.max()) + contact_margin_cells + 1)
    c0 = max(0, int(mc.min()) - contact_margin_cells)
    c1 = min(cols, int(mc.max()) + contact_margin_cells + 1)
    sub_r0 = max(0, r0 - 12)
    sub_r1 = min(rows, r1 + 12)
    sub_c0 = max(0, c0 - 12)
    sub_c1 = min(cols, c1 + 12)
    sub_window = np.zeros((rows, cols), dtype=bool)
    sub_window[sub_r0:sub_r1, sub_c0:sub_c1] = True
    catchment_mask = np.zeros((rows, cols), dtype=bool)
    for m in members:
        catchment_mask[m // cols, m % cols] = True
    flowline_mask = np.zeros((rows, cols), dtype=bool)
    for p in path:
        flowline_mask[p // cols, p % cols] = True
    final_stride = None
    for s in range(1, max_stride + 1):
        idx = np.r_[np.arange(0, len(path) - 1, s), len(path) - 1]
        if len(np.unique(idx)) <= max_nodes:
            final_stride = int(s)
            break
    if final_stride is None:
        final_stride = max_stride
    terminal_r, terminal_c = divmod(tf, cols)
    terminal_native_xz = (
        int(origin_native_xz[0]) + terminal_c,
        int(origin_native_xz[1]) + terminal_r,
    )
    return {
        'candidates': candidates,
        'selection_policy': 'largest_complete_catchment_then_smallest_terminal_flat',
        'chosen': {
            'terminal_flat_cell': tf,
            'terminal_native_xz': terminal_native_xz,
            'catchment_cells': int(len(members)),
            'catchment_area_m2': float(len(members) * cell_size_m * cell_size_m),
            'stem_flat_cells': np.array(path, dtype=np.int64),
            'stem_length_m': float(plen_m),
            'suggested_stride': int(final_stride),
            'catchment_mask': catchment_mask,
            'flowline_mask': flowline_mask,
            'subwindow_rc': (int(sub_r0), int(sub_r1), int(sub_c0), int(sub_c1)),
        },
    }


def _validate_selection(elevation_m, topology, origin, min_stem_m, integers):
    if not isinstance(elevation_m, np.ndarray) or elevation_m.dtype != np.float64 or elevation_m.ndim != 2:
        raise ValueError
    rows, cols = elevation_m.shape
    if rows < 3 or cols < 3 or elevation_m.size > 1787569:
        raise ValueError
    if not isinstance(topology, dict) or not {"receiver", "valid_mask", "upstream_unknown_mask", "terminal_kind"}.issubset(topology):
        raise ValueError
    rec = topology["receiver"]; valid = topology["valid_mask"]; unknown = topology["upstream_unknown_mask"]; tk = topology["terminal_kind"]
    if not (isinstance(rec, np.ndarray) and rec.dtype == np.int64 and rec.shape == (rows, cols)):
        raise ValueError
    if not (isinstance(valid, np.ndarray) and valid.dtype == np.bool_ and valid.shape == (rows, cols)):
        raise ValueError
    if not (isinstance(unknown, np.ndarray) and unknown.dtype == np.bool_ and unknown.shape == (rows, cols)):
        raise ValueError
    if not (isinstance(tk, np.ndarray) and tk.dtype.kind == "U" and tk.shape == (rows, cols)):
        raise ValueError
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError
    for v in origin:
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)):
            raise ValueError
    if isinstance(min_stem_m, (bool, np.bool_)) or not isinstance(min_stem_m, (int, float, np.integer, np.floating)):
        raise ValueError
    if isinstance(min_stem_m, complex) or not np.isfinite(min_stem_m) or min_stem_m <= 0:
        raise ValueError
    if not isinstance(integers, (list, tuple)) or len(integers) != 6:
        raise ValueError
    for v in integers:
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) or v < 1:
            raise ValueError
    if not valid.any():
        raise ValueError('empty_valid')
    vf = valid.ravel()
    rf = rec.ravel()
    ef = elevation_m.ravel()
    if not np.isfinite(ef[vf]).all():
        raise ValueError('nonfinite_height')
    if np.any((rf < -1) | (rf >= rf.size)):
        raise ValueError('receiver_range')
    if np.any(rf[~vf] != -1):
        raise ValueError('invalid_receiver')
    if np.any(unknown.ravel()[~vf]):
        raise ValueError('invalid_unknown_seed')
    src = np.flatnonzero(vf & (rf >= 0))
    dst = rf[src]
    if not vf[dst].all():
        raise ValueError('invalid_target')
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
    mesh = masked_mesh(grid_mesh(rec.shape, x0_m=origin[0] * 30., z0_m=origin[1] * 30.,
                                 dx_m=30., world_seed=20261020), valid)
    if not receiver_edges_valid(rec, mesh):
        raise ValueError('receiver_not_irregular_graph_edge')
    if not np.all(ef[dst] < ef[src]):
        raise ValueError('not_downhill')
    return mesh
