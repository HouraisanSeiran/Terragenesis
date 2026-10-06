# Surface development readiness v1

`prepare_readiness(paths, dynamic_scope=...)` accepts explicit paths to at most five
saved bundles: `dem`, `domain`, `mosaic`, `drop`, and `dynamic`. Missing inputs remain
named blockers. `save_readiness` stores a JSON diagnostic; `load_readiness` checks every
bound file hash, each directly used module hash, existing module static loader, source
identity, and the complete derived conclusion. These module hashes do not freeze
the full transitive dependency tree or runtime environment. The fixed verifier
also records hashes for this module, its tests, verifier, and documentation.
Paths are absolute. No geography
directory scan, sampling, recovery, resampling, or time advancement is performed.
Saved conclusions are compared as sorted strict JSON: key order is irrelevant,
but booleans, integers, and floating-point values are not interchangeable.

The DEM loader uses `verify_source=False`: its offline saved candidate is checked,
but raw geography source replay and independent observational certification are not
available in this gate. This fact is an unconditional blocker. Caller declarations,
including `certified`, labels, and a zero unknown mask, cannot grant certification.
The old mosaic is loaded with `allow_unprepared=True` only to preserve its actual
600-cell gap as a diagnostic. That gap belongs to an engineered two-domain 1 m
sample and cannot be filled directly from the real 90 m DEM. Its false prepared
status never becomes acceptance.

`dynamic_scope` defaults to `lumped_storage_linear_conductance` and may be
`static_geometry`, `lumped_storage_linear_conductance`,
or `full_dynamic_wave`. Static geometry does not require Saint-Venant dynamics.
The existing dynamic graph has constant lumped wet-cell area and caller linear K;
it does not certify calibrated section hydraulics or a full dynamic wave.

This v1 component is a conservative diagnostic, not a complete 3D certification
gate. It has no independent geographic evidence validator: `ready` is fixed
`false` for every input, including future apparently complete bundles. Adding
real data alone cannot make this implementation return `true`; a separately
designed validator and revised contract are required. The fixed evidence has
33454 DEM unknown cells,
an engineered domain, synthetic coast, a 600-cell mosaic gap, and a dynamic graph
from a different saved mosaic artifact. The embedded dynamic proof set contains
only domain1, while the supplied mosaic has both domain proofs. Artifact identity
difference alone is recorded as a fact, not treated as a graph mismatch. Individual
accepted bundles and 356 baseline tests
do not establish an end-to-end natural terrain result.

Run `python -X utf8 -m unittest tests.test_surface_development_readiness -v` and
`python -X utf8 tools/verify_surface_development_readiness.py`. Verifier success
means this conservative diagnosis and its static reload passed; it does not mean
surface development is ready or that 3D work has been implemented.
