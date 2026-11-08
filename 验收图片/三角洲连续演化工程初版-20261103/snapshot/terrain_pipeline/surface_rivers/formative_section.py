from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FormativeSection:
    width_m: np.ndarray
    baseline_width_m: np.ndarray
    deposited_solid_m3: np.ndarray | None
    eroded_solid_m3: np.ndarray | None


def formative_section(formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion,
                      *, reference_discharge_m3_s=1., reference_width_m=4.,
                      min_width_m=0., max_width_m=120., width_exponent=.45,
                      sediment_supply_solid_m3=None, transport_capacity_solid_m3=None,
                      erodible_solid_m3=None):
    """Formative incision width and bounded interval exchange; volumes are solid m³.

    Resistance may already include fracture: in that case pass fracture=0 to
    avoid counting it twice. Exchange is a scenario estimate, not a routed ledger.
    """
    q, bed, bank, frac, cohesion = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in
        (formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion)])
    if not np.isfinite(q).all() or np.any(q < 0):
        raise ValueError('formative discharge must be finite and nonnegative')
    for value in (bed, bank, frac, cohesion):
        if not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
            raise ValueError('material indices must be finite and in [0, 1]')
    params = np.asarray([reference_discharge_m3_s, reference_width_m, min_width_m,
                         max_width_m, width_exponent], dtype=float)
    if not np.isfinite(params).all() or params[0] <= 0 or params[1] <= 0 or params[2] < 0 or params[3] < params[2] or params[4] <= 0:
        raise ValueError('invalid width parameters')
    # Existing discharge geometry's lateral rule; fracture weakens the bank,
    # while cohesion reduces lateral failure. No sediment density multiplier.
    effective_bank = bank * (1 - .5 * frac)
    raw = (reference_width_m * (q / reference_discharge_m3_s) ** width_exponent
           * (1 + 1.5 * bed) * (.5 + 1.5 * (1 - effective_bank))
           * (1 - .35 * cohesion))
    baseline = np.where(q > 0, np.clip(raw, min_width_m, max_width_m), 0.)
    supplied = (sediment_supply_solid_m3, transport_capacity_solid_m3, erodible_solid_m3)
    if all(v is None for v in supplied):
        return FormativeSection(baseline, baseline, None, None)
    if any(v is None for v in supplied):
        raise ValueError('supply, capacity and inventory must be known together')
    supply, capacity, inventory, _ = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in supplied], q)
    for value in (supply, capacity, inventory):
        if not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError('sediment volumes must be finite and nonnegative')
    deposited = np.maximum(supply - capacity, 0.)
    eroded = np.minimum(np.maximum(capacity - supply, 0.), inventory)
    # Saturating finite feedback relative to interval capacity and inventory.
    scale = capacity + supply + inventory
    feedback = np.divide(eroded - deposited, scale, out=np.zeros_like(scale), where=scale > 0)
    width = np.where(q > 0, np.clip(raw * (1 + .4 * feedback), min_width_m, max_width_m), 0.)
    return FormativeSection(width, baseline, deposited, eroded)


def section_from_routed_budget(formative_q_m3_s, bed_resistance, bank_resistance, fracture,
                               bank_cohesion, *, incoming_solid_m3, external_solid_m3,
                               capacity_solid_m3, eroded_loose_solid_m3, eroded_rock_m3,
                               deposited_solid_m3, initial_mobile_solid_m3=0., **width_parameters):
    """Apply already committed routed exchange to a *next* formative section.

    All volumes refer to one solver interval; no stock is changed or charged here.
    The solver remains authoritative for mass balance. This lagged update is not a
    re-solve of the hydraulics or sediment under the resulting new section.
    """
    base = formative_section(formative_q_m3_s, bed_resistance, bank_resistance,
                             fracture, bank_cohesion, **width_parameters)
    values = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in
        (base.baseline_width_m, incoming_solid_m3, external_solid_m3, capacity_solid_m3,
         eroded_loose_solid_m3, eroded_rock_m3, deposited_solid_m3, initial_mobile_solid_m3)])
    baseline, incoming, external, capacity, loose, rock, deposited, mobile = values
    for value in values[1:]:
        if not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError('routed interval volumes must be finite and nonnegative')
    eroded = loose + rock
    # Transport and supply normalise the committed net exchange, with stock
    # mobilised in this interval included so zero-capacity deposition is bounded.
    scale = incoming + external + mobile + capacity + eroded + deposited
    feedback = np.divide(eroded - deposited, scale, out=np.zeros_like(scale), where=scale > 0)
    low = width_parameters.get('min_width_m', 0.)
    high = width_parameters.get('max_width_m', 120.)
    width = np.where(baseline > 0, np.clip(baseline * (1 + .4 * feedback), low, high), 0.)
    return FormativeSection(width, baseline, deposited.copy(), eroded.copy())
