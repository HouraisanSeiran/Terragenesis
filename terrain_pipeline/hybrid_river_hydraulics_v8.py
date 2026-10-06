"""Common local vertical frame adapter for the frozen v6 Radau inventory kernel."""

from dataclasses import asdict, replace
import math

from terrain_pipeline.hybrid_river_hydraulics_v6 import (
    MODEL_VERSION, HydraulicDiagnosticStop, HydraulicExecutionFailure,
    inventory_policy, jacobian_policy, run_experiment as run_local_experiment)
from terrain_pipeline.hybrid_river_sections_v2 import FastSection

SCHEMA = "td-hybrid-river-hydraulics-v8"
INTEGRATION = "Radau"
NUMERICAL_VERSION = "three_origin_local_vertical_frame_analytic_Radau_precision-v8"
ABSOLUTE_HEIGHT_FIELDS = frozenset(("head_m", "crown_m", "low_bank_m", "floor_m"))


def numerical_frame(model):
    datum = float(math.floor(min(cell.section.floor_m for cell in model.cells)))
    return {"schema": "td-hybrid-river-local-vertical-frame-v8", "datum_m": datum,
            "datum_policy": "floor_minimum_actual_section_floor_m",
            "computation": "one_common_local_frame_before_inverse_friction_flux_and_Jacobian",
            "output": "global_head_equals_datum_plus_local_head",
            "source_geometry_unchanged": True, "tiny_flux_deadband": False}


def translate_section(section, datum):
    original = section.original if isinstance(section, FastSection) else section
    translated = replace(original,
                         pieces=tuple((width, (coefficients[0] - datum, coefficients[1], coefficients[2]))
                                      for width, coefficients in original.pieces),
                         polygon=tuple((point[0], point[1] - datum) for point in original.polygon))
    return FastSection(translated)


def local_model(model, frame=None):
    frame = numerical_frame(model) if frame is None else frame
    if frame != numerical_frame(model):
        raise ValueError("common datum must be derived from actual source section floors")
    translated = replace(model, cells=tuple(replace(cell, section=translate_section(cell.section, frame["datum_m"]))
                                           for cell in model.cells))
    translated.validate()
    return translated


def local_experiment(experiment, frame):
    return replace(experiment, initial_heads_m=tuple(head - frame["datum_m"] for head in experiment.initial_heads_m),
                   tailwater_head_m=experiment.tailwater_head_m - frame["datum_m"])


def global_diagnostics(record, datum):
    if isinstance(record, list):
        return [global_diagnostics(value, datum) for value in record]
    if not isinstance(record, dict):
        return record
    restored = {}
    for key, value in record.items():
        if key in ABSOLUTE_HEIGHT_FIELDS and value is not None:
            restored["local_" + key] = value
            restored[key] = datum + value
        else:
            restored[key] = global_diagnostics(value, datum)
    return restored


def global_progress(progress, frame):
    result = global_diagnostics(progress, frame["datum_m"])
    result.update(numerical_frame=frame, absolute_height_coordinate_frame="global",
                  local_height_coordinate_frame="common_local_vertical_frame",
                  raw_state_coordinate_frame="origin_inventory_and_integrated_ledgers_not_height")
    return result


def run_experiment(model, experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    model.validate()
    experiment.validate(model)
    frame = numerical_frame(model)
    translated = local_model(model, frame)
    parameters = local_experiment(experiment, frame)
    try:
        result = run_local_experiment(translated, parameters, crown_transition_width_m, diagnostic_stop_s)
    except HydraulicExecutionFailure as error:
        progress = global_progress(error.progress, frame)
        progress["local_solver_parameters"] = asdict(parameters)
        progress["global_parameters"] = asdict(experiment)
        failure_type = HydraulicDiagnosticStop if isinstance(error, HydraulicDiagnosticStop) else HydraulicExecutionFailure
        raise failure_type(str(error), progress) from error
    result.update(schema=SCHEMA, numerical_version=NUMERICAL_VERSION, integration=INTEGRATION,
                  numerical_frame=frame, local_solver_parameters=asdict(parameters),
                  local_tailwater_head_m=parameters.tailwater_head_m,
                  local_hydraulic_head_m=result["hydraulic_head_m"],
                  execution_progress=global_progress(result["execution_progress"], frame))
    for field in ("hydraulic_head_m", "open_channel_stage_m", "pressurized_head_m"):
        result[field] = [[frame["datum_m"] + value if value is not None else None for value in row]
                         for row in result[field]]
    result["saved_section_diagnostics"] = global_diagnostics(result["saved_section_diagnostics"], frame["datum_m"])
    result["absolute_height_coordinate_frame"] = "global"
    return result
