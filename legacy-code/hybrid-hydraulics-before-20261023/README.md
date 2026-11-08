# Frozen Hybrid Hydraulics Before VC-04

Status: partial consolidation; old active kernel deletion is BLOCKED.

`manifest.json` describes 33 original files captured byte-for-byte before edits. Its trusted SHA256 is fixed in the active `tools/hybrid_hydraulics_legacy.py`, outside this archive:

`8bea4e029f8625c0f8ed8e163877cd1e1d9d60bd02735fcef9e43f17a1665209`

The archive includes the complete v1/v3-v7 algorithms, original v8 baseline, model/section dependencies, prepare/audit helpers, and direct original tests. It is not added to `sys.path`. Current v8 executes the explicit shared model and Radau modules, not these historical modules. v7 remains a BDF historical branch, not a numerically equivalent Radau replacement.

## Explicit Historical Access

From the project root:

```text
runtime/venv/Scripts/python.exe -B -m tools.replay_hybrid_hydraulics_legacy --module tools.prepare_hybrid_river_hydraulics_v7 -- --help
runtime/venv/Scripts/python.exe -B -m tools.replay_hybrid_hydraulics_legacy --module tools.audit_hybrid_river_hydraulics_v8 -- --help
runtime/venv/Scripts/python.exe -B -m unittest tests.test_hybrid_hydraulics_frozen_replay -q
```

For bounded in-memory replay, explicitly construct `HydraulicsLegacyReplay(source_root=..., data_root=...)` and call `load(original_module_name)`. All repository-local imports are restricted to the verified allowlist. The adapter binds `SOURCE_ROOT` to these verified bytes and `DATA_ROOT`/`ROOT` to immutable original data. Historical `file_sha`/source `checked_path` and physical-AST comparisons resolve only verified frozen sources. Path-bootstrap statements are removed from the execution AST, not from archived bytes. Physical equations and order are not transformed. This is trusted-code replay, not a sandbox.

## Source Identity and Blocker

Current preparations record actually executed sources under `code_sha256`, archive references separately under `frozen_reference_code_sha256`, and an explicit `source_layout`. Physical/numerical rules remain unchanged; source identities are intentionally different. Old results and their source pins are never rewritten.

`historical-package-pin-audit.json` is read-only evidence, not an executable allowlist. Its SHA256 is `0494f1c72c1a63e58ee28f87fad716138f84fbf9faf85929597263de45578b1b`. It records the actual saved 02-09 and diagnostic-04 packages. All are `failed_partial`. Source-pin mismatch counts against the editing-before baseline are respectively 0, 2, 3, 4, 5, 6, 7 and 3. The explicit real diagnostic cold-read of 07 is correctly refused: its expected v3 source hash begins `472f3114`, whereas the available original baseline begins `8ef6cf10`. Historical preparation source variants also differ. This predates VC-04; the captured source cannot truthfully reproduce those missing byte variants.

Therefore six old active kernels and the old v2-v7 preparation scripts are retained. Historical test paths now explicitly load these original archived test suites so that live source edits do not silently change their historical pin meaning. The suite exercises actual small original algorithms and audits; it does not certify unavailable old source variants or accept unfinished saved real cases. See `.scratch/module-version-consolidation-20261022/hydraulics-consolidation-20261023.md` for commands and final scope.
