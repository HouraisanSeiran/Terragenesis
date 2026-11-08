"""Guard saved surface readers against production construction and advance."""
from contextlib import contextmanager, ExitStack
from unittest.mock import patch

def _forbidden(*args, **kwargs):
    raise RuntimeError('production construction/advance forbidden during saved surface IO')

@contextmanager
def guard_production_execution():
    from terrain_pipeline import adaptive_mesh, fine_subgrid, surface_hydraulics, shallow_water
    entries = ((adaptive_mesh, ('build_adaptive_geometry', 'initial_leaf_state', 'refine_adaptive_state', 'advance_adaptive_surface', 'adaptive_rhs', 'adaptive_drag')), (fine_subgrid, ('build_fine_geometry', 'build_fine_water_frame', '_geometry_arrays', 'prepare_subgrid_support', 'segmented_flux', 'run_fine_hydraulics', '_advance_subgrid')), (surface_hydraulics, ('prepare_surface_geometry', 'advance_inertial_surface', 'advance_accelerated_surface')), (shallow_water, tuple((name for name, value in vars(shallow_water).items() if name.startswith('advance_') and callable(value)))))
    with ExitStack() as stack:
        for module, names in entries:
            for name in names:
                stack.enter_context(patch.object(module, name, _forbidden))
        yield

def execution_isolated(record):
    return record.get('execution_modules_absent') is True or record.get('execution_functions_guarded') is True
