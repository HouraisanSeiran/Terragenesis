"""One init/step protocol over the finite environment processes (G9-G20).

``init(process, ctx, params, forcing) -> State`` and
``step(state, ctx, forcing, dt_s) -> (State, Ledger)``.

This is a thin adapter layer. Every number comes from the existing process module, called
with the same arguments as before; nothing is recomputed except one derived residual for
radiation (which has no residual of its own). Internal units are SI (m, m3, kg, J, W, s);
each Ledger entry carries a unit string derived from its legacy key suffix.

``params`` is ``{"init": {...kwargs of the legacy initializer...},
"step": {...legacy ``parameters`` argument, only for processes that take one...}}``.
Process modules are imported lazily so that importing this module does not pull the
whole environment family.
"""
from dataclasses import dataclass, field as dc_field
from importlib import import_module

PROTOCOL_ID = "environment-process-protocol-v1"

# process -> (module, initializer, stepper, step takes `parameters`)
PROCESSES = {
    "radiation": ("environment_radiation", "initialize", "step", True),
    "frozen_ground": ("environment_frozen_ground", "initialize", "step", True),
    "volcanism": ("environment_volcanism", "initialize", "step", True),
    "aeolian": ("environment_aeolian", "initialize", "step", True),
    "groundwater": ("environment_groundwater", "initial_state", "step", False),
    "mass": ("environment_mass_processes", "initial_state", "step", False),
    "network_transition": ("environment_network_transition", "initial_state", "step", False),
    "coastal_exchange": ("environment_coastal_exchange", "initialize_coastal_exchange",
                         "advance_coastal_exchange", False),
    "habitat": ("environment_habitat", "initialize_habitat", "advance_habitat", False),
    "soil_chemistry": ("environment_soil_chemistry", "initialize_soil_chemistry",
                       "advance_soil_chemistry", False),
    "succession": ("environment_succession", "initialize_succession", "advance_succession", False),
}

# Ledger classification by legacy key. Keys not listed under a role go to fluxes_in/out
# by the rule in _classify (residual by suffix, stocks by name list, rest by direction).
_STOCKS_BEFORE = {"initial_solid_m3", "water_before_m3", "initial_population", "initial_carbon_kg"}
_STOCKS_AFTER = {"final_solid_m3", "water_after_m3", "final_population", "final_carbon_kg",
                 "current_total_solid_m3"}
_OUT_WORDS = ("export", "pumping", "drainage", "evaporation", "leached", "respired", "deaths",
              "reflected", "fire_atmosphere", "cooling", "snow_latent", "uptake", "soil_water_export",
              "soil_salt_export")
_UNITS = (("_m3", "m3"), ("_kg", "kg"), ("_j", "J"), ("_individuals", "individuals"),
          ("_population", "individuals"), ("_s", "s"))


def _unit(key):
    for suffix, unit in _UNITS:
        if key.endswith(suffix):
            return unit
    if key in ("initial_population", "final_population"):
        return "individuals"
    return "1"


@dataclass(frozen=True)
class State:
    process: str
    arrays: dict
    params: dict = dc_field(default_factory=dict)
    last_fluxes: dict = dc_field(default_factory=dict)
    last_metadata: dict = dc_field(default_factory=dict)


@dataclass(frozen=True)
class Ledger:
    process: str
    stocks_before: dict
    stocks_after: dict
    fluxes_in: dict
    fluxes_out: dict
    residual: dict
    units: dict
    derived: tuple = ()  # keys computed here, not by the legacy module

    def max_abs_residual(self):
        return max((abs(v) for v in self.residual.values()), default=0.)


def _classify(process, legacy):
    before, after, fin, fout, residual, units, derived = {}, {}, {}, {}, {}, {}, []
    data = dict(legacy)
    if process == "radiation" and not any(k.endswith("_residual_j") for k in data):
        data["energy_residual_j"] = data["incident_j"] - data["reflected_j"] - data["absorbed_j"]
        derived.append("energy_residual_j")
    for key, value in data.items():
        value = float(value)
        units[key] = _unit(key)
        if "residual" in key:
            residual[key] = value
        elif key in _STOCKS_BEFORE:
            before[key] = value
        elif key in _STOCKS_AFTER:
            after[key] = value
        elif any(word in key for word in _OUT_WORDS):
            fout[key] = value
        else:
            fin[key] = value
    return Ledger(process, before, after, fin, fout, residual, units, tuple(derived))


def _entry(process):
    if process not in PROCESSES:
        raise ValueError("unknown environment process " + repr(process))
    module, initializer, stepper, takes_parameters = PROCESSES[process]
    mod = import_module("terrain_pipeline." + module)
    return getattr(mod, initializer), getattr(mod, stepper), takes_parameters


def init(process, ctx, params=None, forcing=None):
    """Create a State. ``forcing`` is accepted for protocol symmetry; no legacy initializer uses it."""
    initializer, _, _ = _entry(process)
    params = params or {}
    unknown = set(params) - {"init", "step"}
    if unknown:
        raise ValueError("params may only contain 'init' and 'step'")
    arrays = initializer(ctx, **params.get("init", {}))
    return State(process, arrays, {"init": dict(params.get("init", {})), "step": params.get("step")})


def step(state, ctx, forcing, dt_s):
    _, stepper, takes_parameters = _entry(state.process)
    if takes_parameters:
        result = stepper(state.arrays, forcing, ctx, dt_s, state.params.get("step"))
    else:
        if state.params.get("step"):
            raise ValueError(state.process + " takes no step parameters")
        result = stepper(state.arrays, forcing, ctx, dt_s)
    new = State(state.process, result["state"], state.params, result.get("fluxes", {}),
                result.get("metadata", {}))
    return new, _classify(state.process, result["ledger"])
