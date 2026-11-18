"""Current v4 carrier-bounded growth, with explicit common-step operators."""
from functools import partial

from .metric_fv_growth_core import GrowthOperators, advance_growth as advance_common, zero_wave_field
from .metric_fv_exchange_v3 import equilibrium_concentration, entrain, slope_transport
from .metric_fv_bedload_v4 import transport_bedload
from .metric_fv_incident_wave_vectorized import incident_wave_field

OPERATORS = GrowthOperators(
    transport_bedload=transport_bedload,
    calm_transport=partial(transport_bedload, wave_field=zero_wave_field),
    equilibrium_concentration=partial(equilibrium_concentration, wave_field=incident_wave_field),
    entrain=entrain,
    slope_transport=slope_transport,
)


def advance_growth(*args, **kwargs):
    result = advance_common(*args, operators=OPERATORS, **kwargs)
    result["metadata"].update(schema="FV-finite-carrier-exchange-growth-v4",
        scope="live FV water; finite same-direction net-carrier MPM bedload; v3 exchange and wet-bank slope",
        physical_limitation="net water carrier bound; no oscillatory gross or wave-driven counterflow; empirical MPM/Airy/exchange; no wave radiation stress")
    return result
