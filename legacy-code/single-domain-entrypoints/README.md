# Explicit shallow-water v4/v8 replay archive

This directory is not on the default Python import path and is not a production
backend. The two retired thin entrypoints have been removed from active
`terrain_pipeline/`. Their exact source and the 19-file reachable local Python
dependency closure are retained here. Active support/execution/reconstruction
modules are not removed by this batch because current callers still use them.

## Integrity

`manifest.json` records original paths, SHA256 hashes and local dependency edges.
Its trusted SHA256 is pinned in `tools/single_domain_legacy_entrypoints.py`:

`dfeb5383b63daf1e87e6c57fe1fb9b40a95b47964dc1eb472f78c0f478d1e0de`

Retired entrypoint hashes:

- v4: `2fe792295590fffbbe29b9e9ef4441bf76d2ea764245de9663f2fc633721de5e`
- v8: `3c708dd14113f2349d86de6f259fd7973e0a9b840ac6110982d97eb951dc72fa`

The loader verifies the trusted manifest and every archived source before any
execution. Rewriting both source and its manifest hash is rejected. Local
imports are resolved inside this frozen closure under private module names;
active `terrain_pipeline`/`diffusion` modules and `sys.path` are not replaced.
NumPy, SciPy and the Python runtime remain environment dependencies. This is
trusted local-code replay, not an untrusted-code sandbox or a fully frozen
runtime distribution.

## Explicit use

From the project root in the existing numerical environment:

```python
from tools.single_domain_legacy_entrypoints import load_legacy_entrypoint

legacy = load_legacy_entrypoint("v4")  # or the explicit string "v8"
surface = legacy.replay_dependencies["surface"]
geometry = legacy.replay_dependencies["geometry"]
# Build geometry using the matching archived helpers and use the matching budget:
budget = surface.SurfaceBudget()
# legacy.advance_shallow_water(geometry_record, budget=budget, ...)
```

For v8, `legacy.replay_dependencies["reconstruction"]` provides the matching
`prepare_support` helper. Do not pass an active `SurfaceBudget` class instance:
replay uses an independently loaded historical type and retains its original
strict type check. No v4/v8 fallback is added to production dispatch.

## Bounded replay evidence

`tests/test_single_domain_legacy_entrypoints.py` evolves a deterministic 4x4
coarse closed-wall domain from a nonuniform water state for two 0.05s intervals.
It asserts nonnegative depth, actual redistribution and momentum, physical time,
and volume conservation for both archived entrypoints. Before source retirement,
all saved arrays matched the original active entrypoints bitwise: 9 arrays for
v4 and 15 arrays for v8. The v8 final residual was approximately -3.55e-15 m3;
v4 was 0.0. This is not certification of arbitrary historical cases, natural
boundaries or full-world hydraulics.

The corresponding existing v4/v8 support and v9 tests remain intact. No default
fine backend, solver formula, profile or source-pin validation was changed.
