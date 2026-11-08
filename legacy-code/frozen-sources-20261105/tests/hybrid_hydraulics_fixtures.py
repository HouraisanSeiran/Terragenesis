"""Fixed synthetic hydraulics fixture using the current shared model types."""

from terrain_pipeline.hybrid_river_hydraulics_common import Cell, Link, Model, Section


def tiny_model():
    surface = Section.from_record({"kind": "open_polyline", "polyline_transverse_elevation_m": [[0, 0], [1, 0]], "sidewall_extension": "explicit_engineering_vertical"})
    conduit = Section.from_record({"kind": "closed_polygon", "polygon_transverse_elevation_m": [[0, 0], [1, 0], [1, 1], [0, 1]], "pressure_slot_width_m": 0.01})
    return Model((Cell("sink", "surface", 1, 0.2, surface), Cell("cave", "underground", 1, 0.2, conduit), Cell("spring", "surface", 1, 0.2, surface)),
                 (Link("entry", "sink", "cave", 1, "sink_exchange"), Link("exit", "cave", "spring", 1, "spring_exchange")))
