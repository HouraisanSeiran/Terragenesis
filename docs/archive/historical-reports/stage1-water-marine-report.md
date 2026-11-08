# Stage 1 water marine accounting

The router treats an available ocean mask as authoritative: local runoff is restricted to valid land, and land-to-ocean edges are recorded at their source as distinct mouths. Cross-owner mouth exports use the durable packet ledger and survive send and receive checkpoints. Products without a mask retain legacy routing and report that mode. Ocean classification participates in the journal fingerprint.

Source SHA-256 (terrain_pipeline/new_world_river_lifecycle.py): 7c98f67e88040c3916fb232a17a453d3628cc5bb3d0de9d9bb707a38ea4f9b6f

Tests: `python -m pytest tests/test_new_world_river_lifecycle.py -q` (8 passed); `python -m pytest tests/test_new_world_stage1.py -q` (10 passed). Both emitted an unrelated pytest deprecation warning. The 913 saved-product numerical replay was not run; the all-false mask follows the existing land routing path.
