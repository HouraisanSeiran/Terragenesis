"""Certified occupancy of immutable binary64 meshes using mpmath intervals."""

from fractions import Fraction
from pathlib import Path
import platform
import sys

import mpmath
from mpmath.ctx_iv import MPIntervalContext
from mpmath.libmp import BACKEND, to_rational
import numpy as np

from tools.hybrid_cave_saved_audit import Solid
from tools.hybrid_exact_solid_saved_audit import SOLID_POLICY_SHA256, rational_cross
from tools.td_shared_channel_fine_saved_audit import check_memory, digest, file_sha256, require

TOLERANCE = Fraction.from_float(1e-7)
POLICY = {
    "version": "immutable_binary64_fraction_mpmath_interval_winding-v1",
    "inputs": "original_saved_binary64_xyz_and_original_oriented_triangles_no_motion_no_delete",
    "exact": "Fraction_offsets_dot_cross_squared_lengths_before_interval_conversion",
    "interval": "mpmath_1.3.0_python_MPIntervalContext_outward_sqrt_atan2_sum_divide_by_4pi",
    "precision_decimal_digits": [50, 100, 160],
    "acceptance": "entire_finite_interval_strictly_inside_target_0_or_1_plus_minus_original_binary64_1e-7",
    "tolerance_rational": str(TOLERANCE),
    "returned_value": "certified_target_integer_not_uncertified_float_midpoint",
    "boundary": "exact_triangle_boundary_and_original_vertex_distance_le_1e-12_refused",
    "branch": "zero_numerator_nonpositive_or_uncertain_denominator_refused",
    "maximum_queries": 512,
    "maximum_triangle_evaluations": 2000000,
    "geometry_gates": "unchanged_whole_port_material_and_source_requirements"}
POLICY_SHA256 = digest(POLICY)


def runtime_identity():
    require(mpmath.__version__ == "1.3.0" and BACKEND == "python",
            "only pinned mpmath 1.3.0 pure Python interval backend supported")
    package = Path(mpmath.__file__).resolve().parent
    sources = {str(path.relative_to(package)).replace("\\", "/"): file_sha256(path)
               for path in sorted(package.rglob("*.py"))}
    return {"mpmath_version": mpmath.__version__, "backend": BACKEND,
        "package_path": str(package), "package_source_sha256": sources,
        "package_source_manifest_sha256": digest(sources),
        "python_version": platform.python_version(), "python_binary_path": str(Path(sys.executable).resolve()),
        "python_binary_sha256": file_sha256(Path(sys.executable)),
        "interval_context": "independent_MPIntervalContext_no_global_precision_mutation"}


def exact_dot(first, second):
    return sum((own * other for own, other in zip(first, second)), Fraction(0))


def exact_bounds(interval):
    endpoints = interval._mpi_
    require(all(endpoint[3] >= 0 for endpoint in endpoints), "nonfinite interval winding")
    return tuple(Fraction(*to_rational(endpoint)) for endpoint in endpoints)


def as_interval(context, value):
    return context.mpf(value.numerator) / context.mpf(value.denominator)


class IntervalSolid(Solid):
    def __init__(self, solid, mesh_pin, queries):
        require(mpmath.__version__ == "1.3.0" and BACKEND == "python",
                "unsupported interval runtime")
        require(solid.validation_evidence["policy_identity_sha256"] == SOLID_POLICY_SHA256
                and solid.validation_evidence["all_original_faces_retained"] is True
                and solid.validation_evidence["original_vertex_triangle_identity_sha256"]
                == digest({"vertices": solid.vertices.tolist(), "triangles": solid.triangles.tolist()}),
                "interval wrapper requires original exact validated solid")
        self.source = solid
        self.mesh_pin = dict(mesh_pin)
        self.queries = queries
        self._exact_vertices = None

    def __getattr__(self, name):
        return getattr(self.source, name)

    def winding(self, point):
        query = {"schema": "td-hybrid-interval-winding-certificate-v1", "mesh_pin": self.mesh_pin,
            "solid_label": self.label, "policy_identity_sha256": POLICY_SHA256,
            "original_vertex_triangle_identity_sha256":
                self.validation_evidence["original_vertex_triangle_identity_sha256"],
            "verified": False, "attempts": []}
        self.queries.append(query)
        try:
            require(len(self.queries) <= POLICY["maximum_queries"], "interval query budget exceeded")
            own = np.asarray(point, dtype=np.float64)
            require(own.shape == (3,) and np.isfinite(own).all(), "invalid interval occupancy point")
            query["point_local_xyz_m"] = own.tolist()
            target_point = [Fraction.from_float(float(value)) for value in own]
            query["point_exact_rational_xyz_m"] = list(map(str, target_point))
            if self._exact_vertices is None:
                self._exact_vertices = [[Fraction.from_float(float(value)) for value in vertex]
                                        for vertex in self.vertices]
            terms = []
            for ordinal, triangle in enumerate(self.triangles):
                offsets = [[value - base for value, base in zip(self._exact_vertices[int(index)], target_point)]
                           for index in triangle]
                first, second, third = offsets
                squared = [exact_dot(offset, offset) for offset in offsets]
                require(min(squared) > Fraction.from_float(1e-12) ** 2,
                        "interval air probe touches saved vertex: triangle " + str(ordinal))
                numerator = exact_dot(first, rational_cross(second, third))
                if numerator == 0:
                    edge_first = [end - start for start, end in zip(first, second)]
                    edge_second = [end - start for start, end in zip(first, third)]
                    offset = [-value for value in first]
                    aa, bb, ab = exact_dot(edge_first, edge_first), exact_dot(edge_second, edge_second), exact_dot(edge_first, edge_second)
                    determinant = aa * bb - ab * ab
                    require(determinant > 0, "exact degenerate inherited triangle")
                    own_first, own_second = exact_dot(offset, edge_first), exact_dot(offset, edge_second)
                    bary_first = (own_first * bb - own_second * ab) / determinant
                    bary_second = (own_second * aa - own_first * ab) / determinant
                    require(not (bary_first >= 0 and bary_second >= 0 and bary_first + bary_second <= 1),
                            "exact triangle boundary occupancy refused: triangle " + str(ordinal))
                terms.append((numerator, squared, exact_dot(first, second),
                              exact_dot(second, third), exact_dot(third, first)))
            query["triangle_count"] = len(terms)
            prior_work = sum(item.get("triangle_interval_evaluations", 0) for item in self.queries)
            for digits in POLICY["precision_decimal_digits"]:
                used = query.get("triangle_interval_evaluations", 0)
                require(prior_work + used + len(terms) <= POLICY["maximum_triangle_evaluations"],
                        "interval triangle work budget exceeded")
                query["triangle_interval_evaluations"] = used + len(terms)
                context = MPIntervalContext()
                context.dps = digits
                total = context.mpf(0)
                for numerator, squared, first_second, second_third, third_first in terms:
                    first_length, second_length, third_length = [context.sqrt(as_interval(context, value))
                                                                for value in squared]
                    denominator = first_length * second_length * third_length
                    denominator += as_interval(context, first_second) * third_length
                    denominator += as_interval(context, second_third) * first_length
                    denominator += as_interval(context, third_first) * second_length
                    if numerator == 0 and exact_bounds(denominator)[0] <= 0:
                        query["attempts"].append({"decimal_digits": digits, "unresolved_zero_numerator_branch": True})
                        break
                    total += 2 * context.atan2(as_interval(context, numerator), denominator)
                else:
                    lower, upper = exact_bounds(total / (4 * context.pi))
                    require(lower <= upper, "reversed interval winding bounds")
                    query["attempts"].append({"decimal_digits": digits,
                        "lower_rational": str(lower), "upper_rational": str(upper)})
                    targets = [target for target in (0, 1)
                               if lower > target - TOLERANCE and upper < target + TOLERANCE]
                    if len(targets) == 1:
                        target = targets[0]
                        query.update(verified=True, decimal_digits=digits, lower_rational=str(lower),
                            upper_rational=str(upper), certified_target=target, returned_value=float(target),
                            tolerance_rational=str(TOLERANCE),
                            maximum_absolute_error_rational=str(max(abs(lower-target), abs(upper-target))),
                            whole_interval_inside_original_tolerance=True,
                            source_vertices_or_triangles_modified=False)
                        check_memory()
                        return float(target)
            raise ValueError("interval winding did not certify original tolerance within fixed precision/work budget")
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError, ArithmeticError) as error:
            query.update(error_type=type(error).__name__, error=str(error))
            raise
