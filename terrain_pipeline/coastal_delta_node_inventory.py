"""Conservative ownership of multi-cell channel-node sediment inventories."""
from copy import deepcopy
from dataclasses import replace
import math

import numpy as np

_FIELDS = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')


class ChannelInventory:
    """Partition each grid inventory into exclusive node parts and outer stock.

    Node parts are copied from the saved footprint; no area rescaling is applied
    to pre-existing stock. Call commit before applying external grid changes.
    """

    def __init__(self, state, progress):
        self._shape = state.base_bed_m.shape
        self._identity = state.source_identity
        self._spacing = state.spacing_m
        self._base = np.array(state.base_bed_m, copy=True)
        self._porosity = np.array(state.porosity, copy=True)
        self._parts = {}
        self._cells = {}
        self._fractions = np.zeros(self._shape, dtype=float)
        self._outer = {field: np.array(getattr(state, field), dtype=float, copy=True)
                       for field in _FIELDS}
        for r, c, entries in progress['node_footprints']:
            node = (int(r), int(c))
            if node in self._parts or not entries:
                raise ValueError('duplicate or empty node footprint')
            parts = []
            self._parts[node] = parts
            for pr, pc, fraction, bed, mobile, stranded in entries:
                cell = (int(pr), int(pc))
                values = np.array([fraction, bed, mobile, stranded], dtype=float)
                if (not (0 <= cell[0] < self._shape[0] and 0 <= cell[1] < self._shape[1])
                        or not state.valid_mask[cell] or not np.isfinite(values).all()
                        or fraction <= 0 or fraction > 1 or np.any(values[1:] < 0)):
                    raise ValueError('invalid footprint part')
                part = [cell[0], cell[1], *values.tolist()]
                parts.append(part)
                self._cells.setdefault(cell, []).append(part)
                self._fractions[cell] += fraction
                for i, field in enumerate(_FIELDS):
                    self._outer[field][cell] -= values[i + 1]
        if np.any(self._fractions > 1 + 1e-10):
            raise ValueError('overlapping footprint ownership')
        for field in _FIELDS:
            total = np.asarray(getattr(state, field))
            outer = self._outer[field]
            if np.any(outer < -np.maximum(1e-7, np.abs(total) * 1e-12)):
                raise ValueError('footprint stock exceeds grid inventory')
            outer[outer < 0] = 0.
        self.node_keys = tuple(self._parts)

    @staticmethod
    def _field_index(field):
        if field not in _FIELDS:
            raise ValueError('unknown inventory field')
        return 3 + _FIELDS.index(field)

    @staticmethod
    def _amount(value):
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError('amount must be finite and nonnegative')
        return value

    def amount(self, node, field):
        index = self._field_index(field)
        return math.fsum(part[index] for part in self._parts[tuple(node)])

    def area(self, node):
        return math.fsum(part[2] for part in self._parts[tuple(node)]) * self._spacing**2

    def take(self, node, field, amount):
        index = self._field_index(field)
        requested = self._amount(amount)
        parts = self._parts[tuple(node)]
        available = math.fsum(part[index] for part in parts)
        taken = min(requested, available)
        if available:
            remaining = max(available - taken, 0.)
            for part in parts:
                part[index] *= remaining / available
        return taken

    def add(self, node, field, amount):
        index = self._field_index(field)
        amount = self._amount(amount)
        parts = self._parts[tuple(node)]
        total_fraction = math.fsum(part[2] for part in parts)
        for part in parts:
            part[index] += amount * part[2] / total_fraction

    def section_bed(self, node):
        parts = self._parts[tuple(node)]
        weighted = 0.
        for r, c, fraction, bed, _, _ in parts:
            area = fraction * self._spacing**2
            weighted += area * (self._base[r, c] + bed / (area * (1 - self._porosity[r, c])))
        return weighted / self.area(node)

    def _totals(self):
        result = {field: value.copy() for field, value in self._outer.items()}
        for cell, parts in self._cells.items():
            for i, field in enumerate(_FIELDS):
                result[field][cell] += math.fsum(part[3+i] for part in parts)
        return result

    def _check_state(self, state):
        if (state.source_identity != self._identity or state.base_bed_m.shape != self._shape
                or state.spacing_m != self._spacing
                or not np.array_equal(state.base_bed_m, self._base)
                or not np.array_equal(state.porosity, self._porosity)):
            raise ValueError('state geometry or source mismatch')

    def commit(self, state, progress):
        self._check_state(state)
        totals = self._totals()
        out = replace(state, **totals)
        p = deepcopy(progress)
        p['node_footprints'] = [[*node, [list(part) for part in parts]]
                                for node, parts in self._parts.items()]
        owners = {tuple(row[:2]): row for row in p['integrated']['owner_cells']}
        if set(owners) != set(self._cells):
            raise ValueError('owner cells do not match footprint cells')
        for cell, parts in self._cells.items():
            row = owners[cell]
            row[2] = float(self._fractions[cell])
            for i in range(3):
                row[3+i] = math.fsum(part[3+i] for part in parts)
            # Outer stocks are represented by total grid stock minus row[3:6].
        sections = {tuple(row[:2]): row for row in p['hydraulic_sections']['nodes']}
        for node in self.node_keys:
            sections[node][2] = self.section_bed(node)
        integrated = p['integrated'].get('sections')
        if integrated and p.get('routes'):
            for i, cell in enumerate(p['routes'][0]):
                if i < len(integrated['section_bed_m']) and tuple(cell) in self._parts:
                    integrated['section_bed_m'][i] = self.section_bed(tuple(cell))
        return out, p

    def apply_grid_changes(self, before_state, after_state):
        """Repartition grid changes; caller must commit node edits first."""
        self._check_state(before_state)
        self._check_state(after_state)
        totals = self._totals()
        for field in _FIELDS:
            before = np.asarray(getattr(before_state, field))
            after = np.asarray(getattr(after_state, field))
            if (not np.allclose(before, totals[field], rtol=1e-12, atol=1e-7)
                    or not np.isfinite(after).all() or np.any(after < 0)):
                raise ValueError('uncommitted changes or invalid grid inventory')
        for field in _FIELDS:
            idx = self._field_index(field)
            before = np.asarray(getattr(before_state, field))
            after = np.asarray(getattr(after_state, field))
            delta = after - before
            self._outer[field] += delta
            for cell, parts in self._cells.items():
                change = float(delta[cell])
                self._outer[field][cell] -= change
                if change >= 0:
                    for part in parts:
                        part[idx] += change * part[2]
                    self._outer[field][cell] += change * max(0., 1. - self._fractions[cell])
                else:
                    total = float(totals[field][cell])
                    scale = float(after[cell]) / total if total > 0 else 0.
                    for part in parts:
                        part[idx] *= scale
                    self._outer[field][cell] *= scale
                # Reconcile rounding against the authoritative post-update cell.
                fine = math.fsum(part[idx] for part in parts)
                target = float(after[cell])
                if fine > target:
                    largest = max(parts, key=lambda part: part[idx])
                    largest[idx] = max(0., largest[idx] - (fine - target))
                    fine = math.fsum(part[idx] for part in parts)
                self._outer[field][cell] = max(0., target - fine)
