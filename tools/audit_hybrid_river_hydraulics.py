"""Cold-read actual-section storage and paired water/tracer ledgers; no solver."""

import argparse
import ast
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, checked_path, check_identity, check_memory, digest, file_sha256,
    read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-river-hydraulics-independent-audit-v1"
LEDGER_COLUMNS = ["source_in_m3", "outlet_water_out_m3", "tailwater_water_in_m3",
                  "source_tracer_out_m3", "tailwater_tracer_in_m3", "tailwater_tracer_out_m3"]
ARRAY_KEYS = ("water_volume_m3", "source_tracer_mass_m3", "tailwater_tracer_mass_m3")
LINK_KEYS = ("paired_link_water_integral_m3", "paired_link_source_integral_m3",
             "paired_link_tailwater_integral_m3")


def check_same_physics(include_bdf=False):
    names = ("physical", "flows", "rhs_for", "guard", "capacity_for", "inventory_policy",
             "friction_state", "effective_conveyance", "validate_transition", "roof_contact_length")
    signatures = []
    class SolverLabels(ast.NodeTransformer):
        def visit_Constant(self, node):
            replacements = {
                "BDF_rhs_trial": "Radau_rhs_trial",
                "reject_entire_BDF_step_and_halve_retry": "reject_entire_Radau_step_and_halve_retry",
                "no_interpolated_inventory_output_saved_times_are_BDF_endpoints": "no_interpolated_inventory_output_saved_times_are_Radau_endpoints",
            }
            if isinstance(node.value, str) and node.value in replacements:
                node.value = replacements[node.value]
            return node

    for version in (("v5", "v6", "v7") if include_bdf else ("v5", "v6")):
        tree = ast.parse((ROOT / ("terrain_pipeline/hybrid_river_hydraulics_" + version + ".py")).read_text(encoding="utf-8"))
        tree = SolverLabels().visit(tree)
        methods = {}
        for name in names:
            found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
            require(len(found) == 1, "ambiguous shared physics implementation: " + name)
            methods[name] = ast.dump(found[0], include_attributes=False)
        signatures.append(methods)
    require(all(methods == signatures[0] for methods in signatures[1:]),
            "numerical revisions do not share frozen physics")


def check_accuracy_policy(index, model):
    expected = {"schema": "td-hybrid-river-accuracy-policy-v7", "integration": "BDF",
                "forcing_configuration_pin_unchanged": True,
                "parameter_transform": {
                    "base": {"relative_tolerance_divisor": 64, "absolute_tolerance_divisor": 64, "max_step_divisor": 4},
                    "refined": {"relative_tolerance_divisor": 256, "absolute_tolerance_divisor": 256, "max_step_divisor": 8}},
                "unchanged_scope": "all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards",
                "comparison_gates_unchanged": {"volume_absolute_tolerance_m3": 1e-4,
                                              "head_absolute_tolerance_m": 1e-3, "volume_relative_tolerance": .01,
                                              "paired_and_origin_absolute_tolerance_m3": 1e-4},
                "reused_cases_allowed": False, "precision_change_not_physical_change": True}
    require(index["integration"] == model["integration"] == "BDF"
            and index["accuracy_policy"] == model["accuracy_policy"] == expected
            and index["reused_cases"] == {}
            and set(index["generated_cases"]) == set(index["completed_cases"])
            and index["physical_model_identity_sha256"] == model["physical_model_identity_sha256"] == physical_identity(model),
            "undeclared/changed BDF accuracy policy or reused inaccurate cases")


def accuracy_parameters(original, level):
    tolerance_divisor, step_divisor = (64, 4) if level == "base" else (256, 8)
    return {**original, "max_step_s": original["max_step_s"] / step_divisor,
            "relative_tolerance": original["relative_tolerance"] / tolerance_divisor,
            "absolute_tolerance": original["absolute_tolerance"] / tolerance_divisor}


def physical_identity(model):
    fields = ("model_version", "model_parameters", "friction_policy", "inventory_policy",
              "forcing_configuration_pin", "graph_identity_sha256", "geometry_identity_sha256")
    return digest({key: model[key] for key in fields})


def check_case_binding(record, index, model, name):
    own_model = read(record["hydraulic_model_parameters"])
    own_version = record["schema"].rsplit("-", 1)[-1]
    require(own_model["schema"] == "td-hybrid-river-hydraulic-model-parameters-" + own_version
            and record["hydraulic_model_parameters_identity_sha256"] == own_model["identity_sha256"]
            and own_model["code_sha256"] == record["code_sha256"]
            and record["model_parameters"] == own_model["model_parameters"]
            and record["friction_policy"] == own_model["friction_policy"]
            and record["model_version"] == own_model["model_version"]
            and record["numerical_version"] == own_model["numerical_version"]
            and all(record["jacobian_policy"][key] == value for key, value in own_model["jacobian_policy"].items()),
            "unbound saved case/model/code policy")
    if index["schema"].endswith("v6"):
        require(physical_identity(own_model) == physical_identity(model)
                and record["inventory_policy"] == own_model["inventory_policy"], "changed reused physical model")
        if name == "pulse-base":
            provenance = index["reused_cases"][name]
            parent = read(provenance["source_index_pin"])
            require(parent["schema"] == "td-hybrid-river-hydraulics-preparation-v5"
                    and parent["status"] in ("failed_partial", "diagnostic_accepted", "refused_diagnostic_evidence")
                    and name in parent["completed_cases"]
                    and parent["artifacts"][name + ".json"] == index["artifacts"][name + ".json"] == provenance["source_result_pin"]
                    and parent["hydraulic_model_parameters"] == record["hydraulic_model_parameters"] == provenance["source_model_pin"]
                    and parent["inputs"] == index["inputs"]
                    and parent["numerical_version"] == record["numerical_version"]
                    and parent["model_version"] == own_model["model_version"]
                    and parent["friction_policy"] == own_model["friction_policy"]
                    and parent["jacobian_policy"] == own_model["jacobian_policy"]
                    and len(parent["code_sha256"]) == 17
                    and parent["code_sha256"] == record["code_sha256"] == provenance["code_sha256"]
                    and record["schema"] == "td-hybrid-river-hydraulics-v5"
                    and provenance["result_unmodified"] is True
                    and index["reused_case_work"] == record["work"]
                    and provenance["physical_model_identity_sha256"] == physical_identity(model)
                    and all(index["code_sha256"].get(key) == value for key, value in record["code_sha256"].items()),
                    "unfinished/changed baseline improperly reused")
        else:
            require(record["schema"] == "td-hybrid-river-hydraulics-v6"
                    and record["code_sha256"] == index["code_sha256"]
                    and record["hydraulic_model_parameters"] == index["hydraulic_model_parameters"]
                    and record["physical_model_identity_sha256"] == index["physical_model_identity_sha256"],
                    "wrong generated analytic case binding")
    else:
        require(record["code_sha256"] == index["code_sha256"]
                and record["hydraulic_model_parameters"] == index["hydraulic_model_parameters"], "wrong saved friction revision")
        if index["schema"].endswith("v7"):
            require(record["schema"] == "td-hybrid-river-hydraulics-v7"
                    and record["integration"] == own_model["integration"] == "BDF"
                    and record["accuracy_policy"] == index["accuracy_policy"]
                    and record["accuracy_level"] == name.rsplit("-", 1)[-1]
                    and record["input_parameters_identity_sha256"] == index["input_parameter_identities"][record["scenario"]]
                    and record["physical_model_identity_sha256"] == physical_identity(model),
                    "unbound BDF case accuracy/physical identity")
    for path, sha in record["code_sha256"].items():
        require(file_sha256(ROOT / path) == sha, "case frozen code changed: " + path)


def section_area(section, head):
    if section["kind"] == "open_polyline":
        area = 0.0
        points = section["polyline_transverse_elevation_m"]
        for first, second in zip(points[:-1], points[1:]):
            width = second[0] - first[0]
            require(width > 0, "unordered actual surface section")
            first_depth, second_depth = head - first[1], head - second[1]
            if min(first_depth, second_depth) >= 0:
                area += width * (first_depth + second_depth) / 2
            elif max(first_depth, second_depth) > 0:
                positive_depth = max(first_depth, second_depth)
                area += width * positive_depth**2 / (2 * abs(first_depth - second_depth))
        return area
    require(section["kind"] == "closed_polygon", "unexpected actual section kind")
    points = np.asarray(section["polygon_transverse_elevation_m"], dtype=float)
    origin = points[0]
    polygon = Polygon(points - origin)
    require(polygon.is_valid and polygon.area > 0, "invalid final VDM polygon")
    floor, crown = points[:, 1].min(), points[:, 1].max()
    if head <= floor:
        return 0.0
    if head >= crown:
        return polygon.area + section["pressure_slot_width_m"] * (head - crown)
    lower_x, lower_y, upper_x, upper_y = polygon.bounds
    return polygon.intersection(box(lower_x - 1, lower_y - 1, upper_x + 1, head - origin[1])).area


def array(record, key, shape):
    result = np.asarray(record[key], dtype=float)
    require(result.shape == shape and np.isfinite(result).all(), "invalid saved array: " + key)
    return result


def section_friction(cell, head, width):
    section = cell["section"]
    closed = section["kind"] == "closed_polygon"
    points = section["polygon_transverse_elevation_m" if closed else "polyline_transverse_elevation_m"]
    edges = list(zip(points, points[1:] + points[:1])) if closed else list(zip(points[:-1], points[1:]))
    perimeter = 0.0
    floor = min(point[1] for point in points)
    for first, second in edges:
        lower, upper = sorted((first[1], second[1]))
        length = math.dist(first, second)
        if head <= floor:
            continue
        if head >= upper and (closed or lower < upper or head > upper):
            perimeter += length
        elif head > lower:
            perimeter += length * (head - lower) / (upper - lower)
    roof = 0.0
    effective = perimeter
    if closed:
        crown = max(point[1] for point in points)
        roof = math.fsum(math.dist(first, second) for first, second in edges
                         if first[1] == crown and second[1] == crown)
        if width > 0 and head >= crown:
            fraction = min(1.0, (head - crown) / width)
            effective -= roof * (1 - fraction**2 * (3 - 2 * fraction))
    else:
        perimeter += max(0.0, head - points[0][1]) + max(0.0, head - points[-1][1])
        effective = perimeter
    area = section_area(section, head)
    require(area == 0 or perimeter > 0 and effective > 0, "nonpositive wet friction perimeter")
    def capacity(value):
        return area * (area / value)**(2 / 3) / cell["roughness_manning"] if area > 0 else 0.0
    return {"area_m2": area, "actual_wetted_perimeter_m": perimeter,
            "effective_friction_perimeter_m": effective, "actual_horizontal_roof_length_m": roof,
            "actual_geometry_manning_conveyance": capacity(perimeter),
            "effective_manning_conveyance": capacity(effective)}


def check_friction_probes(record, geometry, parameters):
    policy = record["friction_policy"]
    width = policy["width_m"]
    require(isinstance(width, (int, float)) and math.isfinite(width) and 0 < width <= .05
            and policy["transition_start"] == "crown" and policy["transition_end"] == "crown+width_m"
            and policy["actual_perimeter_unchanged"] is True and policy["storage_area_unchanged"] is True
            and policy["pressure_slot_width_unchanged"] is True
            and policy["roof_length_source"] == "sum_actual_polygon_edges_with_both_endpoints_at_crown"
            and policy["constitutive_kind"] == "C1_effective_roof_contact_friction"
            and policy["contact_polynomial"] == "u*u*(3-2*u)_for_0<=u<=1",
            "unknown/undeclared effective roof friction model")
    cells, links = geometry["hydraulic_cells"], geometry["hydraulic_links"]
    snapshots, probes = record["saved_section_diagnostics"], record["instantaneous_flux_probes"]
    times = record["times_s"]
    require(len(snapshots) == len(probes) == len(times), "incomplete actual section/flux probes")
    maximum = 0.0
    def matched(actual, expected):
        nonlocal maximum
        require(isinstance(actual, (int, float)) and math.isfinite(actual), "nonfinite section/flux diagnostic")
        error = abs(actual - expected)
        maximum = max(maximum, error)
        require(error <= 1e-8 + 1e-10 * abs(expected), "independent section friction/flux mismatch")
    def discharge(capacity, difference, length):
        return capacity * difference / ((difference**2 + 1e-8)**.25 * math.sqrt(length))
    for ordinal, seconds in enumerate(times):
        snapshot, probe = snapshots[ordinal], probes[ordinal]
        require(snapshot["time_s"] == probe["time_s"] == seconds and len(snapshot["cells"]) == len(cells)
                and len(probe["links"]) == len(links), "misaligned section/flux probes")
        heads = record["hydraulic_head_m"][ordinal]
        volumes = record["water_volume_m3"][ordinal]
        source = record["source_tracer_mass_m3"][ordinal]
        tailwater = record["tailwater_tracer_mass_m3"][ordinal]
        capacities = []
        for cell_index, (cell, saved) in enumerate(zip(cells, snapshot["cells"])):
            require(saved["cell_id"] == cell["cell_id"] and saved["kind"] == cell["kind"], "probe ownership mismatch")
            friction = section_friction(cell, heads[cell_index], width)
            for key, expected in friction.items():
                matched(saved[key], expected)
            for key, expected in (("head_m", heads[cell_index]), ("volume_m3", volumes[cell_index]),
                                  ("source_tracer_mass_m3", source[cell_index]), ("tailwater_tracer_mass_m3", tailwater[cell_index])):
                matched(saved[key], expected)
            if "untraced_water_volume_m3" in record:
                matched(saved["untraced_water_volume_m3"], record["untraced_water_volume_m3"][ordinal][cell_index])
            capacities.append(friction["effective_manning_conveyance"])
        matched(snapshot["total_water_m3"], sum(volumes))
        matched(probe["source_q_m3_s"], parameters["pulse_q_m3_s"] if seconds < parameters["pulse_duration_s"] else 0.0)
        for link_index, (link, saved) in enumerate(zip(links, probe["links"])):
            flow = discharge(min(capacities[link_index:link_index + 2]), heads[link_index] - heads[link_index + 1], link["length_m"])
            donor = link_index if flow >= 0 else link_index + 1
            flow *= volumes[donor] / (volumes[donor] + 1e-6)
            require(saved["link_id"] == link["link_id"] and saved["donor_cell_id"] == cells[donor]["cell_id"], "flux donor mismatch")
            matched(saved["water_q_m3_s"], flow)
            matched(saved["source_tracer_q_m3_s"], flow * source[donor] / volumes[donor])
            matched(saved["tailwater_tracer_q_m3_s"], flow * tailwater[donor] / volumes[donor])
        tail_capacity = section_friction(cells[-1], parameters["tailwater_head_m"], width)["effective_manning_conveyance"]
        flow = discharge(min(capacities[-1], tail_capacity), heads[-1] - parameters["tailwater_head_m"], cells[-1]["length_m"] / 2)
        if flow >= 0:
            flow *= volumes[-1] / (volumes[-1] + 1e-6)
            source_flow, tailwater_flow = flow * source[-1] / volumes[-1], flow * tailwater[-1] / volumes[-1]
        else:
            source_flow, tailwater_flow = 0.0, flow
        matched(probe["outlet_signed_water_q_m3_s"], flow)
        matched(probe["outlet_signed_source_tracer_q_m3_s"], source_flow)
        matched(probe["outlet_signed_tailwater_tracer_q_m3_s"], tailwater_flow)
    return {"effective_roof_friction_independently_verified": True, "transition_width_m": width,
            "max_section_and_flux_diagnostic_difference": maximum}


def check_three_origins(record, volumes, source, tailwater, initial, ledgers):
    untraced = array(record, "untraced_water_volume_m3", volumes.shape)
    require(np.all(untraced >= 0) and np.max(abs(untraced[0] - initial)) <= 1e-9,
            "invalid explicit initial-origin inventory")
    composition = float(np.max(abs(volumes - (untraced + source + tailwater))))
    require(composition <= 1e-10, "water is not the sum of its three explicit origins")
    integral = array(record, "paired_link_untraced_integral_m3", (len(volumes), volumes.shape[1] - 1))
    outgoing = array(record, "outlet_untraced_out_m3", (len(volumes),))
    require(np.max(abs(integral[0])) == 0 and outgoing[0] == 0 and np.all(outgoing >= -1e-9)
            and np.all(np.diff(outgoing) >= -1e-9), "invalid initial-origin cumulative exchange")
    expected = np.tile(initial, (len(volumes), 1))
    expected[:, :-1] -= integral
    expected[:, 1:] += integral
    expected[:, -1] -= outgoing
    residual = float(np.max(abs(untraced - expected)))
    require(residual <= 1e-4, "per-cell initial-origin conservation failed")
    link_error = float(np.max(abs(np.asarray(record["paired_link_water_integral_m3"]) - integral
                                 - record["paired_link_source_integral_m3"] - record["paired_link_tailwater_integral_m3"])))
    require(link_error <= 1e-4 and np.max(abs(ledgers[:, 1] - outgoing - ledgers[:, 3] - ledgers[:, 5])) <= 1e-4,
            "three origins do not exhaust the water exchange ledger")
    return {"three_origin_inventory_verified": True, "max_three_origin_composition_difference_m3": composition,
            "max_per_cell_untraced_residual_m3": residual, "max_three_origin_link_difference_m3": link_error,
            "initial_origin_remaining_m3": float(untraced[-1].sum()), "initial_origin_exported_m3": float(outgoing[-1])}


def check_result(record, geometry, parameters):
    check_identity(record)
    require(record["status"] == "diagnostic_completed", "partial/refused case cannot be accepted")
    require(record["parameters"] == parameters and record["parameters_identity_sha256"] == digest(parameters),
            "saved experiment differs from explicit configuration")
    cells, links = geometry["hydraulic_cells"], geometry["hydraulic_links"]
    count, times = len(cells), np.asarray(record["times_s"], dtype=float)
    require(3 <= count <= 64 and len(links) == count - 1, "invalid bounded physical chain")
    require(record["cell_ids"] == [cell["cell_id"] for cell in cells]
            and record["link_ids"] == [link["link_id"] for link in links], "actual geometry ownership mismatch")
    require(times.tolist() == parameters["saved_times_s"] and 2 <= len(times) <= 4096
            and np.isfinite(times).all() and times[0] == 0 and times[-1] == parameters["duration_s"]
            and np.all(np.diff(times) > 0), "physical saved-time mismatch")
    shape = (len(times), count)
    volumes, source, tailwater = [array(record, key, shape) for key in ARRAY_KEYS]
    heads = array(record, "hydraulic_head_m", shape)
    initial = array(record, "initial_untraced_water_m3", (count,))
    configured_heads = np.asarray(parameters["initial_heads_m"], dtype=float)
    require(configured_heads.shape == (count,) and np.isfinite(configured_heads).all()
            and np.max(abs(heads[0] - configured_heads)) <= 1e-9,
            "initial saved head differs from explicit configuration")
    configured_volumes = np.asarray([section_area(cell["section"], head) * cell["length_m"]
                                    for cell, head in zip(cells, configured_heads)])
    require(np.max(abs(initial - configured_volumes)) <= 1e-7,
            "initial untraced inventory differs from actual configured geometry")
    require(np.all(volumes > 0) and np.all(source >= 0) and np.all(tailwater >= 0)
            and np.all(source + tailwater <= volumes + 1e-7), "positivity/tracer composition mismatch")
    require(np.max(abs(volumes[0] - initial)) <= 1e-9 and np.max(abs(source[0])) == 0
            and np.max(abs(tailwater[0])) == 0, "initial storage/tracer origin mismatch")
    ledgers = array(record, "boundary_ledger_m3", (len(times), 6))
    require(record["ledger_columns"] == LEDGER_COLUMNS and np.max(abs(ledgers[0])) == 0
            and np.all(ledgers >= -1e-9) and np.all(np.diff(ledgers, axis=0) >= -1e-9),
            "invalid cumulative boundary ledger")
    link_integrals = [array(record, key, (len(times), count - 1)) for key in LINK_KEYS]
    require(all(np.max(abs(integral[0])) == 0 for integral in link_integrals), "nonzero initial internal exchange")
    require(np.max(abs(ledgers[:, 2] - ledgers[:, 4])) <= 1e-9, "tailwater inlet attribution mismatch")
    expected_source = np.minimum(times, parameters["pulse_duration_s"]) * parameters["pulse_q_m3_s"]
    require(np.max(abs(ledgers[:, 0] - expected_source)) <= 1e-6, "duplicate/missing prescribed pulse source")
    tolerance = 1e-4
    residuals = []
    for stored, initial_storage, integral, incoming, outgoing in (
            (volumes, initial, link_integrals[0], ledgers[:, 0], ledgers[:, 1] - ledgers[:, 2]),
            (source, np.zeros(count), link_integrals[1], ledgers[:, 0], ledgers[:, 3]),
            (tailwater, np.zeros(count), link_integrals[2], np.zeros(len(times)), ledgers[:, 5] - ledgers[:, 4])):
        expected = np.tile(initial_storage, (len(times), 1))
        expected[:, 0] += incoming
        expected[:, -1] -= outgoing
        expected[:, :-1] -= integral
        expected[:, 1:] += integral
        residuals.append(float(np.max(abs(stored - expected))))
    require(max(residuals) <= tolerance, "per-cell paired water/tracer conservation failed")
    area_error = 0.0
    pressure_count = 0
    compliance_volume = np.zeros(len(times))
    max_pressure_excess = 0.0
    max_engineered_bank_excess = 0.0
    overbank_count = 0
    for ordinal, cell in enumerate(cells):
        require(cell["length_m"] > 0, "invalid actual storage length")
        section = cell["section"]
        for row, head in enumerate(heads[:, ordinal]):
            area_error = max(area_error, abs(section_area(section, head) * cell["length_m"] - volumes[row, ordinal]))
            closed = section["kind"] == "closed_polygon"
            crown = max(point[1] for point in section["polygon_transverse_elevation_m"]) if closed else math.inf
            pressurized = closed and head > crown
            if closed:
                excess = max(0.0, head - crown)
                max_pressure_excess = max(max_pressure_excess, excess)
                compliance_volume[row] += section["pressure_slot_width_m"] * excess * cell["length_m"]
            else:
                points = section["polyline_transverse_elevation_m"]
                bank = min(points[0][1], points[-1][1])
                bank_excess = max(0.0, head - bank)
                max_engineered_bank_excess = max(max_engineered_bank_excess, bank_excess)
                overbank_count += int(bank_excess > 0)
            actual_stage = record["open_channel_stage_m"][row][ordinal]
            actual_pressure = record["pressurized_head_m"][row][ordinal]
            require((actual_stage is None) == pressurized and (actual_pressure is not None) == pressurized,
                    "pressure head mislabeled as open water surface")
            value = actual_pressure if pressurized else actual_stage
            require(abs(value - head) <= 1e-9, "stage/head value mismatch")
            pressure_count += int(pressurized)
    require(area_error <= 1e-7, "saved inventory does not match actual VDM/open-section geometry")
    threshold = parameters["source_arrival_threshold_m3"]
    arrival_indices = np.flatnonzero(source[:, -1] >= threshold)
    arrival_time = float(times[arrival_indices[0]]) if len(arrival_indices) else None
    sink_index = next(ordinal for ordinal, link in enumerate(links) if link["kind"] == "sink_exchange")
    reached_outlet = bool(ledgers[-1, 3] >= threshold)
    reverse_sink = bool(-link_integrals[0][-1, sink_index] > threshold and tailwater[-1, 0] >= threshold)
    require(record["source_arrival_time_s"] == arrival_time and record["source_reached_engineered_outlet"] == reached_outlet
            and record["reverse_reached_sink"] == reverse_sink, "source/return arrival claim mismatch")
    require(record["boundary_scope"] == "positively_wet_prescribed_tailwater_only_no_dry_free_outfall",
            "unsupported hydraulic boundary scope")
    for flag in ("natural_outlet_certified", "full_network_verified", "finite_speed_front_verified", "three_dimensional_flow_solved"):
        require(record[flag] is False, "unjustified promotion: " + flag)
    for segment in record["integration_segments"]:
        require(0 < segment["max_adaptive_step_s"] <= parameters["max_step_s"] + 1e-9
                and segment["accepted_steps"] > 0, "saved integrator step contract mismatch")
    work = record["work"]
    jacobian_count = work.get("jacobian_evaluations", 0)
    friction_report = {}
    if record.get("numerical_version"):
        policy = record["jacobian_policy"]
        require(policy["ledger_feedback_columns"] == "exact_zero"
                and record["jacobian_policy"]["scipy_adaptive_difference_factor_used"] is False
                and work["jacobian_rhs_evaluations"] == (0 if record["schema"].endswith(("v6", "v7")) else jacobian_count * (count + 1)),
                "explicit Jacobian policy/work mismatch")
        if record["schema"] in ("td-hybrid-river-hydraulics-v4", "td-hybrid-river-hydraulics-v5", "td-hybrid-river-hydraulics-v6", "td-hybrid-river-hydraulics-v7"):
            version = record["schema"].rsplit("-", 1)[-1]
            width = record["friction_policy"]["width_m"]
            cap = min(1e-6, record["model_parameters"]["head_regularization_m"] * .01, width * .01)
            numerical = {"v4": "head_bounded_log_difference_Radau_step_diagnostics-v4",
                         "v5": "three_origin_direct_inventory_Radau_positivity_rejection-v5",
                         "v6": "three_origin_analytic_native_chain_Radau-v6",
                         "v7": "three_origin_analytic_native_chain_BDF_precision-v7"}[version]
            require(record["numerical_version"] == numerical
                    and record["model_version"] == "explicit_roof_friction_contact_transition-" + ("v5" if version in ("v6", "v7") else version),
                    "unknown instrumented numerical/physical version")
            if version not in ("v6", "v7"):
                require(policy["max_head_step_m"] == cap and policy["nominal_head_ceiling_m"] == 1e-6
                    and policy["head_step_target_fraction_of_cap"] == .5
                    and policy["head_step_fraction_of_friction_transition"] == .01
                    and policy["head_step_float_margin"] == "16_ulp_of_base_head"
                    and policy["head_cap_rule"] == "min(nominal_head_ceiling_m,head_regularization_m*0.01,width_m*0.01_if_positive)"
                    and policy["observed_max_head_step_m"] == work["jacobian_max_observed_head_step_m"]
                    and 0 <= work["jacobian_max_observed_head_step_m"] <= cap + 16 * max(math.ulp(float(head)) for head in heads.ravel()),
                        "head-bounded Jacobian policy/work mismatch")
            if version == "v4":
                require(policy["log_volume_nominal_absolute_step"] == 1e-6 and policy["tracer_columns"] == "analytic_donor_transport"
                        and 0 < work["jacobian_min_log_step"] <= work["jacobian_max_log_step"] <= 1e-6 + 1e-14,
                        "log-volume Jacobian policy mismatch")
            elif version == "v5":
                require(policy["total_inventory_nominal_relative_step"] == 1e-6
                        and policy["tracer_columns"] == "all_three_origin_columns_share_total_inventory_feedback_plus_analytic_composition"
                        and policy["step_units"] == "m3_total_inventory_constant_composition_forward_difference_bounded_by_head"
                        and 0 < work["jacobian_min_volume_step_m3"] <= work["jacobian_max_volume_step_m3"],
                        "three-origin Jacobian policy mismatch")
            else:
                require(policy["method"] == "native_piecewise_section_and_signed_Manning_full_chain_analytic"
                        and policy["inventory_columns"] == "all_three_origins_share_dV_dM_equal_one_plus_exact_donor_composition"
                        and policy["section_breakpoint_branch"] == "right_height_band"
                        and policy["min_capacity_tie_branch"] == "left_or_cell_at_boundary"
                        and policy["zero_signed_flow_donor_branch"] == "left_or_cell_outlet"
                        and policy["jacobian_rhs_evaluations_per_call"] == 0
                        and policy["jacobian_link_evaluations_per_call"] == 2 * count
                        and work["jacobian_link_evaluations"] == 2 * count * jacobian_count
                        and work["jacobian_flow_evaluations"] == count * jacobian_count
                        and work["jacobian_link_derivative_evaluations"] == count * jacobian_count
                        and work["jacobian_native_section_derivatives"] == count * jacobian_count
                        and work["jacobian_section_fallback_evaluations"] == 0,
                        "unknown/miscounted analytic actual-section Jacobian")
            progress = record["execution_progress"]
            require(progress["physical_event_complete"] is True and progress["diagnostic_stop_s"] is None
                    and progress["last_accepted_physical_time_s"] == parameters["duration_s"]
                    and progress["triggered_guard"] is None
                    and progress["accepted_steps"] == sum(segment["accepted_steps"] for segment in record["integration_segments"])
                    and progress["work"]["rhs_evaluations"] == work["rhs_evaluations"],
                    "partial/guarded run masquerading as complete event")
            friction_report = check_friction_probes(record, geometry, parameters)
            if version in ("v5", "v6", "v7"):
                friction_report.update(check_three_origins(record, volumes, source, tailwater, initial, ledgers))
                inventory = record["inventory_policy"]
                solver = "BDF" if version == "v7" else "Radau"
                require(inventory["origins"] == ["untraced", "source", "tailwater"]
                        and inventory["water_definition"] == "sum_three_origin_inventories" and inventory["state_units"] == "m3"
                        and inventory["negative_inventory_action"] == "reject_entire_" + solver + "_step_and_halve_retry"
                        and inventory["output_clamp"] is False and inventory["posthoc_normalization"] is False
                        and inventory["positivity_tolerance_m3"] == 0 and inventory["initial_origin"] == "untraced"
                        and inventory["pulse_origin"] == "source" and inventory["reverse_boundary_origin"] == "tailwater"
                        and inventory["retry_budget"] == "one_original_event_work_wall_RSS_budget_never_reset"
                        and inventory["dense_inventory_check"] == "no_interpolated_inventory_output_saved_times_are_" + solver + "_endpoints",
                        "unknown/nonconservative three-origin policy")
                witness = record["dense_positivity_witness"]
                require(witness["policy"] == "no_dense_inventory_output_saved_times_are_" + solver + "_endpoints"
                        and witness["interpolated_inventory_samples"] == 0
                        and witness["accepted_steps"] == progress["accepted_steps"]
                        and witness["negative_inventory_tolerance_m3"] == 0, "unsupported dense positivity claim")
                segments = record["integration_segments"]
                expected_breaks = sorted(set(times.tolist() + [parameters["pulse_duration_s"]]))
                require([segment["start_s"] for segment in segments] == expected_breaks[:-1]
                        and [segment["end_s"] for segment in segments] == expected_breaks[1:]
                        and work["observation_segment_initializations"] == len(segments)
                        and work[solver.lower() + "_constructor_attempts"] == len(segments) + work["solver_reinitializations"]
                        and work["solver_reinitializations"] == work["positivity_rejected_steps"] + work["constructor_nonpositive_retries"]
                        and work["accepted_endpoint_inventory_checks"] >= progress["accepted_steps"],
                        "hidden reset or miscounted endpoint/positivity retries")
                if version == "v7":
                    orders = progress["accepted_BDF_order_after_step_counts"]
                    require(record["integration"] == progress["integration"] == "BDF"
                            and set(orders) <= {"1", "2", "3", "4", "5"}
                            and all(isinstance(value, int) and value >= 0 for value in orders.values())
                            and sum(orders.values()) == progress["accepted_steps"],
                            "wrong BDF integrator/order evidence")
            require(work["diagnostic_flux_link_evaluations"] == len(times) * count,
                    "saved flux-probe work mismatch")
        else:
            require(record["numerical_version"] == "fixed_log_volume_difference_analytic_tracer_jacobian-v3"
                    and policy["log_volume_absolute_step"] == 1e-6, "unknown numerical revision")
    require(work["rhs_evaluations"] <= parameters["max_rhs_evaluations"]
            and work["link_evaluations"] == (work["rhs_evaluations"] + (2 if record["schema"].endswith(("v6", "v7")) else 1) * jacobian_count) * count + work.get("diagnostic_flux_link_evaluations", 0)
            and work["link_evaluations"] <= parameters["max_link_evaluations"]
            and work["actual_peak_rss_bytes"] <= 1024**3
            and work["wall_seconds"] <= parameters["max_wall_seconds"]
            and work["old_hll_face_work"] == 0 and work["old_hll_face_budget_remaining_unchanged"] == 2_949_448_968,
            "saved resource/work contract failed")
    return {**friction_report, "max_per_cell_water_residual_m3": residuals[0], "max_per_cell_source_residual_m3": residuals[1],
            "max_per_cell_tailwater_residual_m3": residuals[2], "conservation_tolerance_m3": tolerance,
            "max_actual_section_volume_difference_m3": area_error, "pressurized_saved_cell_count": pressure_count,
            "max_pressure_above_actual_crown_m": max_pressure_excess,
            "max_engineered_stage_above_section_bank_m": max_engineered_bank_excess,
            "overbank_saved_cell_count": overbank_count,
            "pressure_slot_compliance_volume_m3": compliance_volume.tolist(),
            "max_pressure_slot_compliance_volume_m3": float(compliance_volume.max()),
            "initial_untraced_water_m3": float(initial.sum()), "source_in_m3": float(ledgers[-1, 0]),
            "source_arrival_time_s": arrival_time, "source_outlet_m3": float(ledgers[-1, 3]),
            "source_export_fraction": float(ledgers[-1, 3] / ledgers[-1, 0]) if ledgers[-1, 0] else None,
            "outlet_water_out_m3": float(ledgers[-1, 1]), "tailwater_water_in_m3": float(ledgers[-1, 2]),
            "tailwater_arrived_first_surface_m3": float(tailwater[-1, 0]),
            "source_reached_engineered_outlet": reached_outlet, "reverse_reached_sink": reverse_sink}


def compare_saved(base, refined):
    require(base["cell_ids"] == refined["cell_ids"] and base["times_s"] == refined["times_s"], "unaligned refinement")
    head_error = float(np.max(abs(np.asarray(base["hydraulic_head_m"]) - refined["hydraulic_head_m"])))
    volume_error = float(np.max(abs(np.asarray(base["water_volume_m3"]) - refined["water_volume_m3"])))
    relative_error = float(np.max(abs(np.asarray(base["water_volume_m3"]) - refined["water_volume_m3"]) / refined["water_volume_m3"]))
    tracer_error = max(float(np.max(abs(np.asarray(base[key]) - refined[key]))) for key in ARRAY_KEYS[1:] + ("boundary_ledger_m3",))
    link_l1 = {}
    link_absolute = {}
    extra_links = ("paired_link_untraced_integral_m3",) if "untraced_water_volume_m3" in base else ()
    for key in LINK_KEYS + extra_links:
        first, second = np.asarray(base[key]), np.asarray(refined[key])
        maximum = float(np.max(abs(first - second)))
        absolute = float(np.sum(abs(first - second)))
        denominator = float(np.sum(abs(second)))
        require(maximum <= 1e-4 and absolute <= 1e-4 + .01 * denominator,
                "paired link refinement failed: " + key)
        link_absolute[key] = maximum
        link_l1[key] = absolute / denominator if denominator else None
    require(head_error <= .001 and volume_error <= 1e-4 and relative_error <= .01 and tracer_error <= 1e-4,
            "saved 1mm/1percent refinement failed")
    if extra_links:
        require(max(float(np.max(abs(np.asarray(base[key]) - refined[key]))) for key in
                    ("untraced_water_volume_m3", "outlet_untraced_out_m3")) <= 1e-4,
                "explicit initial-origin refinement failed")
    return {"max_head_difference_m": head_error, "max_volume_difference_m3": volume_error,
            "max_relative_volume_difference": relative_error, "max_tracer_ledger_difference_m3": tracer_error,
            "paired_link_relative_l1": link_l1, "paired_link_max_absolute_difference_m3": link_absolute}


def audit(index_pin):
    index = read(index_pin)
    inputs = index["inputs"]
    graph = read(inputs["graph"])
    geometry = read(inputs["geometry"])
    geometry_audit = read_audit(inputs["geometry_audit"])
    configuration = read(inputs["experiments"])
    require(index["schema"] in ("td-hybrid-river-hydraulics-preparation-v1", "td-hybrid-river-hydraulics-preparation-v2",
                                "td-hybrid-river-hydraulics-preparation-v3", "td-hybrid-river-hydraulics-preparation-v4",
                                "td-hybrid-river-hydraulics-preparation-v5", "td-hybrid-river-hydraulics-preparation-v6",
                                "td-hybrid-river-hydraulics-preparation-v7"),
            "wrong saved hydraulics schema")
    require(index["status"] == "diagnostic_accepted" and set(index["artifacts"]) == {
        "pulse-base.json", "pulse-refined.json", "reverse_tailwater-base.json", "reverse_tailwater-refined.json"},
        "unfinished or refused engineering events cannot be accepted")
    if index["schema"] != "td-hybrid-river-hydraulics-preparation-v1":
        require(set(index["completed_cases"]) == {"pulse-base", "pulse-refined", "reverse_tailwater-base", "reverse_tailwater-refined"}
                and len(index["completed_cases"]) == 4 and index["section_adapter_schema"] == "td-hybrid-river-fast-sections-v2",
                "incomplete/unknown optimized-section checkpoint")
    if index["schema"].endswith("v3"):
        require(index["numerical_version"] == "fixed_log_volume_difference_analytic_tracer_jacobian-v3"
                and len(index["code_sha256"]) == 11, "unknown explicit-Jacobian solver revision")
    if index["schema"].endswith(("v4", "v5", "v6", "v7")):
        version = index["schema"].rsplit("-", 1)[-1]
        numerical = {"v4": "head_bounded_log_difference_Radau_step_diagnostics-v4",
                     "v5": "three_origin_direct_inventory_Radau_positivity_rejection-v5",
                     "v6": "three_origin_analytic_native_chain_Radau-v6",
                     "v7": "three_origin_analytic_native_chain_BDF_precision-v7"}[version]
        require(index["numerical_version"] == numerical
                and len(index["code_sha256"]) == {"v4": 14, "v5": 17, "v6": 20, "v7": 23}[version],
                "unknown instrumented solver revision")
        hydraulic_model = read(index["hydraulic_model_parameters"])
        require(index["diagnostic_stop_s"] is None and not index["diagnostic_artifacts"]
                and hydraulic_model["schema"] == "td-hybrid-river-hydraulic-model-parameters-" + version
                and hydraulic_model["graph_identity_sha256"] == graph["identity_sha256"]
                and hydraulic_model["geometry_identity_sha256"] == geometry["identity_sha256"]
                and hydraulic_model["forcing_configuration_pin"] == inputs["experiments"]
                and hydraulic_model["model_version"] == index["model_version"] == "explicit_roof_friction_contact_transition-" + ("v5" if version in ("v6", "v7") else version)
                and hydraulic_model["numerical_version"] == index["numerical_version"]
                and hydraulic_model["friction_policy"] == index["friction_policy"]
                and hydraulic_model["jacobian_policy"] == index["jacobian_policy"],
                "unbound/partial/changed declared hydraulic model")
        require(hydraulic_model["code_sha256"] == index["code_sha256"], "model/code binding mismatch")
        if version in ("v5", "v6", "v7"):
            resource = index["resource"]
            solver = "BDF" if version == "v7" else "Radau"
            require(resource["whole_event_not_split_or_restarted"] is False
                    and resource["one_complete_forcing_event_budget_no_work_or_wall_reset"] is True
                    and resource["observation_times_reinitialize_" + solver] is True
                    and resource["negative_inventory_rollback_reinitializes_" + solver + "_with_same_event_budget"] is True,
                    "hidden observation segmentation/work reset")
        if version == "v7":
            check_same_physics(include_bdf=True)
            check_accuracy_policy(index, hydraulic_model)
        if version == "v6":
            check_same_physics()
            require(set(index["reused_cases"]) == {"pulse-base"}
                    and set(index["generated_cases"]) == {"pulse-refined", "reverse_tailwater-base", "reverse_tailwater-refined"}
                    and index["physical_model_identity_sha256"] == hydraulic_model["physical_model_identity_sha256"] == physical_identity(hydraulic_model)
                    and index["reuse_contract"]["reused_result_rewritten"] is False
                    and index["reuse_contract"]["reused_work_not_counted_as_new"] is True,
                    "invalid complete-case reuse/physical identity")
    require(geometry_audit["status"] == "passed" and not geometry_audit.get("errors")
            and geometry_audit["geometry_sha256"] == inputs["geometry"]["sha256"]
            and geometry_audit["actual_hydraulic_sections_verified"] and geometry_audit["actual_portal_connections_verified"],
            "unverified actual geometry input")
    for record in (index, geometry, configuration):
        require(record["graph_identity_sha256"] == graph["identity_sha256"], "parent graph mismatch")
    require(index["geometry_identity_sha256"] == geometry["identity_sha256"]
            and configuration["geometry_identity_sha256"] == geometry["identity_sha256"], "parent geometry mismatch")
    for pin in graph["inputs"].values():
        checked_path(pin)
    for pin in geometry["inputs"].values():
        checked_path(pin)
    for parent in (geometry, geometry_audit):
        for field in ("code_sha256", "audit_code_sha256", "readonly_dependency_code_sha256"):
            for name, sha in parent.get(field, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen geometry/audit dependency changed: " + name)
    for name, sha in index["code_sha256"].items():
        require(file_sha256(ROOT / name) == sha, "frozen solver code changed: " + name)
    scenarios = {row["scenario"]: row for row in configuration["scenarios"]}
    require(set(scenarios) == {"pulse", "reverse_tailwater"}, "wrong engineering scenarios")
    reports = {}
    new_rhs = 0
    new_links = 0
    for scenario, parameters in scenarios.items():
        base = read(index["artifacts"][scenario + "-base.json"])
        refined = read(index["artifacts"][scenario + "-refined.json"])
        for record in (base, refined):
            require(record["inputs"] == inputs and record["graph_identity_sha256"] == graph["identity_sha256"]
                    and record["geometry_identity_sha256"] == geometry["identity_sha256"], "result/input binding mismatch")
            require(record["model_parameters"] == {"head_regularization_m": 1e-4, "donor_regularization_m3": 1e-6},
                    "hidden hydraulic regularization change")
            if index["schema"] not in ("td-hybrid-river-hydraulics-preparation-v1", "td-hybrid-river-hydraulics-preparation-v6"):
                require(record["code_sha256"] == index["code_sha256"] and record["section_adapter_schema"] == index["section_adapter_schema"],
                        "optimized-section result code binding mismatch")
            if index["schema"].endswith("v3"):
                require(record["schema"] == "td-hybrid-river-hydraulics-v3"
                        and record["numerical_version"] == index["numerical_version"], "wrong saved Jacobian revision")
            if index["schema"].endswith(("v4", "v5", "v6", "v7")):
                case_name = scenario + ("-base" if record is base else "-refined")
                check_case_binding(record, index, hydraulic_model, case_name)
                if version == "v7" or version == "v6" and case_name != "pulse-base":
                    new_rhs += record["work"]["rhs_evaluations"]
                    new_links += record["work"]["link_evaluations"]
                require(record["section_adapter_schema"] == index["section_adapter_schema"], "changed actual section adapter")
                if version in ("v5", "v6", "v7"):
                    require(record["inventory_policy"] == hydraulic_model["inventory_policy"], "unbound inventory model")
        if index["schema"].endswith(("v4", "v5", "v6", "v7")):
            require(base["friction_policy"] == refined["friction_policy"], "refinement changed constitutive physics")
        refined_parameters = {**parameters, "max_step_s": parameters["max_step_s"] / 2,
                              "relative_tolerance": parameters["relative_tolerance"] / 4,
                              "absolute_tolerance": parameters["absolute_tolerance"] / 4}
        if index["schema"].endswith("v7"):
            require(index["input_parameter_identities"][scenario] == digest(parameters),
                    "BDF accuracy transform changed original event identity")
            refined_parameters = accuracy_parameters(parameters, "refined")
            parameters = accuracy_parameters(parameters, "base")
        base_report = check_result(base, geometry, parameters)
        refined_report = check_result(refined, geometry, refined_parameters)
        refinement = compare_saved(base, refined)
        required = "source_reached_engineered_outlet" if scenario == "pulse" else "reverse_reached_sink"
        require(base_report[required] and refined_report[required], "missing actual arrival evidence: " + scenario)
        meaningful_key = "source_outlet_m3" if scenario == "pulse" else "tailwater_arrived_first_surface_m3"
        meaningful_minimum = max(1.0, base_report["source_in_m3"] * .001) if scenario == "pulse" else 1.0
        require(base_report[meaningful_key] >= meaningful_minimum and refined_report[meaningful_key] >= meaningful_minimum,
                "threshold arrival is insufficient meaningful transported volume: " + scenario)
        for record, report in ((base, base_report), (refined, refined_report)):
            times = np.asarray(record["times_s"])
            ledgers = np.asarray(record["boundary_ledger_m3"])
            late_index = int(np.searchsorted(times, times[-1] - 100, side="left"))
            report["late_100s_source_export_m3"] = float(ledgers[-1, 3] - ledgers[late_index, 3])
            if scenario == "pulse":
                require(report["late_100s_source_export_m3"] >= .5, "no meaningful late-window source transport")
        refined_report["meaningful_transport_minimum_m3"] = meaningful_minimum
        reports[scenario] = {"base": base_report, "refined": refined_report, "refinement": refinement}
        check_memory()
    if index["schema"].endswith(("v6", "v7")):
        require(index["work"]["new_1d_rhs_evaluations"] == new_rhs
                and index["work"]["new_1d_link_evaluations"] == new_links,
                "reused/unfinished work mixed with new complete-case work")
    return {"schema": AUDIT_SCHEMA, "status": "passed", "errors": [], "index_sha256": index_pin["sha256"],
            "inputs": inputs, "reports": reports, "actual_section_storage_verified": True,
            "paired_per_cell_water_and_tracers_verified": True, "time_refinement_verified": True,
            "scope": "saved_finite_1d_diffusive_storage_and_two_engineering_events_not_independent_momentum_solver",
            "continuous_between_steps_positivity_certified": False,
            "numerical_version": index.get("numerical_version"),
            "accuracy_policy": index.get("accuracy_policy"),
            "natural_outlet_certified": False, "full_network_verified": False, "three_dimensional_flow_solved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "new independent audit output required")
    started = time.monotonic()
    index_pin = {"path": str(args.input.resolve()), "sha256": args.sha256}
    try:
        report = audit(index_pin)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "index_sha256": args.sha256,
                  "errors": [str(error)], "natural_outlet_certified": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory()}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_hydraulics.py", "tools/td_shared_channel_fine_saved_audit.py",
        "tests/test_hybrid_river_hydraulics_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "independent audit exceeds file limit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(json.dumps(report, ensure_ascii=True))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
