"""Hydraulic sediment-transport capacity for multi-cell delta channel nodes (issue 24).

Opt-in rule that replaces the legacy ``capacity = Q * 0.01 * duration`` limit.

Capacity of one channel node, solid volume per second (same leaf as
``surface_rivers.metric_sediment._rates``)::

    R     = w h / (w + 2 h)                     hydraulic radius, m
    Sf    = (n Q / (w h R^(2/3)))^2             Manning friction slope from the
                                                actual Q, depth h, width w, roughness n
    tau   = rho g R Sf                          bed shear stress, Pa
    C     = k w max(tau - tau_c, 0)^1.5         m3/s of solid volume

The slope is the *friction* slope rebuilt from the solved Q, depth and width.
The water-surface gradient of the graph solve also contains control and
acceleration terms and is deliberately not used here.

Per node and transport substep ``dt <= L / v`` (L control length, v speed)::

    advective = mobile * min(1, v dt / L)
    overloaded  (advective > C dt): carried = C dt, no erosion, the excess
                settles: deposit = min(excess, (mobile - carried)(1 - exp(-ws dt / h)), room)
    underloaded (advective <= C dt): carried = advective, the deficit entrains
                bed material: erosion = min(C dt - carried, erodibility limit,
                remaining active-layer cap, bed stock)

Material parameters are declared, uncalibrated scenario values.
"""
from dataclasses import asdict, dataclass
import math

ALGORITHM = 'excess-shear-manning-substep-v1'
BED = 'bed_solid_m3'
MOBILE = 'mobile_solid_m3'
SECONDS_PER_YEAR = 365.25 * 86400.


@dataclass(frozen=True)
class HydraulicCapacityRule:
    """Declared material identity of the excess-shear capacity rule.

    Units: shear Pa, transport coefficient m3 s-1 m-1 Pa-1.5, erodibility
    m s-1 Pa-1, settling velocity m s-1, concentration a solid-volume fraction.
    ``max_concentration`` is an optional explicit ceiling (the legacy 0.01 is
    one such choice) and never the capacity itself. ``annual_formative_seconds_per_year``
    is the declared effective seconds per equivalent year at the supplied
    representative hydraulic solution; it is required by the annual mode only.
    """
    critical_shear_pa: float = 1.
    transport_coefficient: float = 1e-5
    sediment_erodibility_m_s_pa: float = 1e-6
    settling_velocity_m_s: float = .001
    max_concentration: object = None
    annual_formative_seconds_per_year: object = None
    substep_settling_fraction: float = .1
    rho_water_kg_m3: float = 1000.
    gravity_m_s2: float = 9.81
    material_provenance: str = 'declared homogeneous scenario'
    calibration_status: str = 'declared/uncalibrated'

    def __post_init__(self):
        for name in ('critical_shear_pa', 'transport_coefficient', 'sediment_erodibility_m_s_pa',
                     'settling_velocity_m_s', 'rho_water_kg_m3', 'gravity_m_s2'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.transport_coefficient <= 0 or self.rho_water_kg_m3 <= 0 or self.gravity_m_s2 <= 0:
            raise ValueError('transport coefficient, density and gravity must be positive')
        if self.max_concentration is not None:
            if not isinstance(self.max_concentration, (int, float)) or not 0 < self.max_concentration <= 1:
                raise ValueError('max_concentration must be None or in (0, 1]')
        if self.annual_formative_seconds_per_year is not None:
            value = self.annual_formative_seconds_per_year
            if (not isinstance(value, (int, float)) or not math.isfinite(value)
                    or not 0 < value <= SECONDS_PER_YEAR):
                raise ValueError('annual_formative_seconds_per_year must be None or in (0, one year]')
        if (isinstance(self.substep_settling_fraction, bool) or not isinstance(self.substep_settling_fraction, (int, float))
                or not 0 < self.substep_settling_fraction <= 1):
            raise ValueError('substep_settling_fraction must be in (0, 1]')
        if not self.material_provenance.strip() or not self.calibration_status.strip():
            raise ValueError('material provenance and calibration status are required')

    def identity(self):
        return {'algorithm': ALGORITHM, **asdict(self),
                'friction_slope_source': 'Manning reconstruction from actual Q, depth, width and section roughness',
                'capacity_formula': 'k*w*max(tau-tau_c,0)^1.5, tau=rho*g*R*Sf',
                'deposition_substep_clock': 'v2: fraction*max(h/ws,L/v); deposition bounded by advective excess and exact settling',
                'legacy_capacity_concentration_role': 'ignored; use max_concentration for an explicit ceiling'}

    @classmethod
    def from_identity(cls, identity):
        names = cls.__dataclass_fields__
        if identity.get('algorithm') != ALGORITHM:
            raise ValueError('unknown hydraulic capacity algorithm')
        return cls(**{k: v for k, v in identity.items() if k in names})

    def inlet_solid(self, supply_m3, accepted_q_m3_s, dt):
        """Delivered inlet solid; no hidden concentration ceiling unless declared."""
        if self.max_concentration is None:
            return supply_m3
        return min(supply_m3, accepted_q_m3_s * self.max_concentration * dt)


def friction_slope(q_m3_s, width_m, depth_m, roughness):
    """Manning friction slope and hydraulic radius for a rectangular section."""
    area = width_m * depth_m
    radius = area / (width_m + 2. * depth_m)
    return (q_m3_s * roughness / (area * radius ** (2. / 3.))) ** 2, radius


def capacity_rate(rule, q_m3_s, width_m, depth_m, roughness):
    """Solid transport capacity in m3/s and the quantities it came from."""
    if not (q_m3_s > 0 and width_m > 0 and depth_m > 0 and roughness > 0):
        return {'capacity_m3_s': 0., 'tau_pa': 0., 'friction_slope': 0., 'radius_m': 0.}
    slope, radius = friction_slope(q_m3_s, width_m, depth_m, roughness)
    tau = rule.rho_water_kg_m3 * rule.gravity_m_s2 * radius * slope
    capacity = rule.transport_coefficient * width_m * max(tau - rule.critical_shear_pa, 0.) ** 1.5
    if rule.max_concentration is not None:
        capacity = min(capacity, rule.max_concentration * q_m3_s)
    return {'capacity_m3_s': capacity, 'tau_pa': tau, 'friction_slope': slope, 'radius_m': radius}


def node_exchange(rule, *, mobile_m3, advective_m3, capacity_m3, depth_m, dt_s,
                  erosion_limit_m3, erosion_cap_m3, deposit_room_m3):
    """One node/substep exchange. Returns (carried, eroded, deposited, overloaded).

    Erosion happens only when the physical capacity exceeds what is carried;
    the excess of an overloaded node settles (finite by settling and room) and
    otherwise stays in the mobile store, never discarded.
    """
    advective = min(advective_m3, mobile_m3)
    if advective > capacity_m3:
        carried = capacity_m3
        excess = advective - capacity_m3
        settle = (mobile_m3 - carried) * (1. - math.exp(-rule.settling_velocity_m_s * dt_s / depth_m))
        return carried, 0., max(0., min(excess, settle, deposit_room_m3)), True
    carried = advective
    eroded = max(0., min(capacity_m3 - carried, erosion_limit_m3, erosion_cap_m3))
    return carried, eroded, 0., False


def _new_diag(node):
    return {'node_zx': list(node), 'capacity_m3': 0., 'carried_m3': 0., 'eroded_m3': 0.,
            'deposited_m3': 0., 'seconds': 0., 'overloaded_seconds': 0.,
            'q_s': 0., 'depth_s': 0., 'width_s': 0., 'tau_s': 0., 'slope_s': 0.}


def river_transport(rule, pool, state, level, dt_s, outgoing, widths, stages, roughness,
                    length_of, caps, budgets, diag, max_velocity_m_s, inlet=None, inlet_solid_m3=0.):
    """Transport one marine step in substeps dt <= L/v with frozen hydraulics.

    Returns (ocean_delivery, moved_m3, eroded_m3). Node stocks are changed
    through ``pool`` so bed, mobile and external ledgers stay closed; grid
    marine exchange is left to the caller.
    """
    ocean_delivery = []
    moved = eroded_total = 0.
    elapsed = 0.
    porosity = state.porosity
    supplied = 0.

    def supply(until_s):
        # Inlet solid arrives uniformly in time, so its timing never depends on the marine step.
        nonlocal supplied
        if inlet is None or not inlet_solid_m3:
            return
        amount = inlet_solid_m3 * min(1., until_s / dt_s) - supplied
        if amount > 0:
            pool.add(inlet, MOBILE, amount)
            budgets[inlet]['external_solid_m3'] += amount
            supplied += amount

    while elapsed < dt_s - 1e-9:
        supply(elapsed)
        plan = []
        for node, edges in outgoing.items():
            depth = stages.get(node, level) - pool.section_bed(node)
            if depth <= 0:
                continue
            usable = [e for e in edges if tuple(e['to_zx']) not in widths or
                      stages.get(tuple(e['to_zx']), level) > pool.section_bed(tuple(e['to_zx']))]
            q = sum(e['discharge_m3_s'] for e in usable)
            if q <= 0:
                continue
            speed = min(max_velocity_m_s, q / (widths[node] * depth))
            plan.append((node, usable, q, depth, speed, length_of(node)))
        if not plan:
            break
        step = min(dt_s - elapsed, min(length / speed for *_, speed, length in plan))
        if rule.settling_velocity_m_s > 0:
            # node_exchange caps deposition by BOTH advective excess and an
            # exact exponential settling amount. Its stock-depletion rate is
            # therefore bounded by the slower process. h/ws alone creates
            # microscopic global steps at nearly dry, negligible-flow nodes.
            step = min(step, rule.substep_settling_fraction * min(
                max(depth / rule.settling_velocity_m_s, length / speed)
                for _, _, _, depth, speed, length in plan))
        incoming = {}
        for node, usable, q, depth, speed, length in plan:
            cap = capacity_rate(rule, q, widths[node], depth, roughness[node])
            mobile = pool.amount(node, MOBILE)
            solid_area = state.spacing_m ** 2 * math.fsum(
                part[2] * (1 - porosity[part[0], part[1]]) for part in pool._parts[node])
            excess = max(cap['tau_pa'] - rule.critical_shear_pa, 0.)
            capacity_m3 = cap['capacity_m3_s'] * step
            carried, eroded, deposited, overloaded = node_exchange(
                rule, mobile_m3=mobile, advective_m3=mobile * min(1., speed * step / length),
                capacity_m3=capacity_m3, depth_m=depth, dt_s=step,
                erosion_limit_m3=solid_area * rule.sediment_erodibility_m_s_pa * excess * step,
                erosion_cap_m3=max(0., caps[node]), deposit_room_m3=depth * solid_area)
            carried = pool.take(node, MOBILE, carried)
            deposited = pool.take(node, MOBILE, deposited)
            if deposited:
                pool.add(node, BED, deposited)
            eroded = pool.take(node, BED, eroded)
            caps[node] -= eroded
            moved += carried + eroded
            eroded_total += eroded
            record = budgets[node]
            record['capacity_solid_m3'] += capacity_m3
            record['eroded_solid_m3'] += eroded
            record['deposited_solid_m3'] += deposited
            row = diag.setdefault(node, _new_diag(node))
            row['capacity_m3'] += capacity_m3
            row['carried_m3'] += carried
            row['eroded_m3'] += eroded
            row['deposited_m3'] += deposited
            row['seconds'] += step
            row['overloaded_seconds'] += step if overloaded else 0.
            row['q_s'] += q * step
            row['depth_s'] += depth * step
            row['width_s'] += widths[node] * step
            row['tau_s'] += cap['tau_pa'] * step
            row['slope_s'] += cap['friction_slope'] * step
            for edge in usable:
                destination = tuple(edge['to_zx'])
                amount = (carried + eroded) * edge['discharge_m3_s'] / q
                if destination in widths:
                    incoming[destination] = incoming.get(destination, 0.) + amount
                else:
                    ocean_delivery.append((node, destination, amount))
        for node, amount in incoming.items():
            pool.add(node, MOBILE, amount)
            budgets[node]['incoming_solid_m3'] += amount
        elapsed += step
        supply(elapsed)
    supply(dt_s)
    return ocean_delivery, moved, eroded_total


def summarize(diag):
    """Per-node report with time-weighted means; nodes sorted by key."""
    rows = []
    for node in sorted(diag):
        row = diag[node]
        seconds = row['seconds'] or 1.
        rows.append({'node_zx': row['node_zx'], 'seconds': row['seconds'],
            'overloaded_seconds': row['overloaded_seconds'],
            'mean_q_m3_s': row['q_s'] / seconds, 'mean_depth_m': row['depth_s'] / seconds,
            'mean_width_m': row['width_s'] / seconds, 'mean_tau_pa': row['tau_s'] / seconds,
            'mean_friction_slope': row['slope_s'] / seconds, 'capacity_m3': row['capacity_m3'],
            'carried_m3': row['carried_m3'], 'eroded_m3': row['eroded_m3'], 'deposited_m3': row['deposited_m3']})
    return rows


def annual_node_capacity(rule, years, q_m3_s, width_m, depth_m, roughness):
    """Annual capacity = capacity rate at the supplied representative solution
    times ``years * annual_formative_seconds_per_year`` (declared, bounded)."""
    if rule.annual_formative_seconds_per_year is None:
        raise ValueError('annual hydraulic capacity requires annual_formative_seconds_per_year')
    cap = capacity_rate(rule, q_m3_s, width_m, depth_m, roughness)
    return cap['capacity_m3_s'] * years * rule.annual_formative_seconds_per_year, cap
