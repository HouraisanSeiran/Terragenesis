"""Experimental execution optimization only; unchanged compensated forcing and SSP-RK2."""

import math
import numpy as np
from numba import njit
from terrain_pipeline.td_basin_transport_v6 import _compiled_exchange

PROFILE = "v8-compiled-hour-loop-experimental-v1"


@njit(cache=True)
def _add(value, increment, error):
    if increment < 0 and increment == -value:
        return 0., 0.
    adjusted = increment-error
    updated = value+adjusted
    if updated < 0 or not math.isfinite(updated):
        raise ValueError("negative/nonfinite compensated inventory")
    return updated,(updated-value)-adjusted


@njit(cache=True)
def _release(storage,incoming,seconds,tau):
    ratio=seconds/tau
    fraction=-math.expm1(-ratio)
    coefficient=ratio/2-ratio**2/6+ratio**3/24 if ratio<1e-4 else 1-fraction/ratio
    return storage*fraction+incoming*coefficient


@njit(cache=True)
def _forcing(states,errors,rain,seconds,runoff,config,area,ledger,ledger_errors):
    hours=seconds/3600
    for cell in range(states.shape[1]):
        rainfall=rain[cell]*hours
        lake=rainfall if states[0,cell]>config[1] else 0.
        land=rainfall-lake
        infiltration=min(min(land,runoff[0]*hours),max(0.,runoff[1]-states[1,cell]))
        states[1,cell],errors[1,cell]=_add(states[1,cell],infiltration,errors[1,cell])
        soil_et=min(states[1,cell],runoff[2]*hours)
        states[1,cell],errors[1,cell]=_add(states[1,cell],-soil_et,errors[1,cell])
        percolation=min(states[1,cell],runoff[3]*hours)
        states[1,cell],errors[1,cell]=_add(states[1,cell],-percolation,errors[1,cell])
        fast_release=_release(states[2,cell],land-infiltration,seconds,runoff[4])
        slow_release=_release(states[3,cell],percolation,seconds,runoff[5])
        states[2,cell],errors[2,cell]=_add(states[2,cell],land-infiltration-fast_release,errors[2,cell])
        states[3,cell],errors[3,cell]=_add(states[3,cell],percolation-slow_release,errors[3,cell])
        release=fast_release+slow_release
        states[0,cell],errors[0,cell]=_add(states[0,cell],(lake+release)/1000,errors[0,cell])
        surface_et=min(states[0,cell],config[2]*hours/1000)
        states[0,cell],errors[0,cell]=_add(states[0,cell],-surface_et,errors[0,cell])
        increments=(rainfall*area/1000,lake*area/1000,land*area/1000,soil_et*area/1000,release*area/1000,surface_et*area)
        for index in range(6):
            ledger[index,cell],ledger_errors[index,cell]=_add(ledger[index,cell],increments[index],ledger_errors[index,cell])


@njit(cache=True)
def advance_hour(states,errors,rain,bed,faces,boundary,widths,receiver,spacing,seconds,subdivisions,runoff,config):
    ledger=np.zeros((8,states.shape[1]))
    ledger_errors=np.zeros((6,states.shape[1]))
    forward=np.zeros(len(faces));reverse=np.zeros(len(faces))
    forward_s=np.zeros(len(faces));reverse_s=np.zeros(len(faces))
    routed=np.zeros(states.shape[1]);duration=np.zeros(states.shape[1])
    indices=np.empty(0,np.int64)
    for substep in range(subdivisions):
        _forcing(states,errors,rain,seconds/2,runoff,config,spacing*spacing,ledger,ledger_errors)
        depth,positive,negative,exported,positive_s,negative_s=_compiled_exchange(states[0],bed,faces,boundary,widths,spacing,seconds,config[0],indices,indices)
        states[0]=depth
        errors[0]=0
        incoming=np.zeros(states.shape[1]);outgoing=np.zeros(states.shape[1])
        for index in range(len(faces)):
            first,second=faces[index,0],faces[index,1]
            signed=positive[index]-negative[index]
            incoming[second]+=signed;outgoing[first]+=signed
            forward[index]+=positive[index];reverse[index]+=negative[index]
            forward_s[index]+=positive_s[index];reverse_s[index]+=negative_s[index]
            if receiver[first]==second:
                routed[first]+=positive[index];duration[first]+=positive_s[index]
            if receiver[second]==first:
                routed[second]+=negative[index];duration[second]+=negative_s[index]
        for cell in range(states.shape[1]):
            ledger[6,cell]+=incoming[cell]-outgoing[cell]
        for index in range(len(boundary)):
            ledger[7,boundary[index]]+=exported[index]
        _forcing(states,errors,rain,seconds/2,runoff,config,spacing*spacing,ledger,ledger_errors)
    return states,errors,ledger,forward,reverse,forward_s,reverse_s,routed,duration
