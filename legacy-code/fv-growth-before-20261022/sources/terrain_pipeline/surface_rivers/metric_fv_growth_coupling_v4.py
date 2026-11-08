"""v4 finite carrier bedload; frozen v3 exchange/FV sequencing retained."""
from types import FunctionType

from . import metric_fv_growth_coupling_v3 as previous
from . import metric_fv_exchange_v3 as exchange
from .metric_fv_bedload_v4 import transport_bedload
from .metric_fv_incident_wave_vectorized import incident_wave_field


_equilibrium = FunctionType(exchange.equilibrium_concentration.__code__,
    dict(exchange.equilibrium_concentration.__globals__, incident_wave_field=incident_wave_field),
    name="equilibrium_with_vectorized_waves", argdefs=exchange.equilibrium_concentration.__defaults__)
_calm = FunctionType(transport_bedload.__code__,
    dict(transport_bedload.__globals__, incident_wave_field=previous.zero_wave_field),
    name="calm_carrier_transport", argdefs=transport_bedload.__defaults__)
_advance = FunctionType(previous.advance_growth.__code__, dict(previous.advance_growth.__globals__,
    transport_bedload=transport_bedload, _calm_transport=_calm, equilibrium_concentration=_equilibrium),
    name="advance_carrier_growth")
_advance.__kwdefaults__ = previous.advance_growth.__kwdefaults__


def advance_growth(*args, **kwargs):
    result = _advance(*args, **kwargs)
    result["metadata"].update(schema="FV-finite-carrier-exchange-growth-v4",
        scope="live FV water; finite same-direction net-carrier MPM bedload; v3 exchange and wet-bank slope",
        physical_limitation="net water carrier bound; no oscillatory gross or wave-driven counterflow; empirical MPM/Airy/exchange; no wave radiation stress")
    return result
