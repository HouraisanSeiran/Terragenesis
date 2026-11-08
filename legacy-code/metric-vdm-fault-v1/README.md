# Metric VDM fault v1 frozen replay

This directory is not on the current Python import path. It retains the original source bytes before the fault-family A-plan migration on 2026-10-22. Current generation uses `terrain_pipeline.metric_vdm_fault_v2`; its recipe and selection weights are in `metric_vdm_fault_common`.

## Trust and contents

`manifest.json` records original relative paths, byte lengths and SHA256 for eleven before files: the v1/v2 fault modules, their preparation/audit/test files, and the VDM/forms/source/JSON helper dependencies needed for full historical generation. The replay adapter pins the manifest bytes independently:

`79f5a568db4820da1f6c429f41fd2071d733db54724d40936254e7d4152d408d`

Original v1 module SHA256:

`bb367e16885450f4278f10f120a1d3d0bb41d1229e6a759cf82e779cc3f2f78a`

Changing both archived source and its manifest is rejected against that trusted manifest pin. The adapter rechecks the archive before returning a cached module set. Original archive files and historical report hashes are not rewritten.

## Explicit replay only

Run the current CLI normally to generate v2. To replay the complete original v1 algorithm, explicitly request:

```powershell
runtime/venv/Scripts/python.exe -B tools/prepare_metric_vdm_fault.py --configuration <config.json> --configuration-sha256 <sha256> --output <new-directory> --legacy-v1-replay
```

For original-v1 read-only auditing:

```powershell
runtime/venv/Scripts/python.exe -B tools/audit_metric_vdm_fault.py <fault.npz> --expected-sha256 <sha256> --expected-identity <identity> --legacy-v1-replay
```

The explicit Python API is `tools.metric_vdm_fault_legacy_v1.load_legacy_api()` / `load_legacy_fault()` / `replay_legacy_preparation()`. The original v1 validator remains separate from v2; neither decoder silently treats the other's schema as its own.

## Controlled execution adaptation

Do not directly run the archived preparation script using its new `__file__`: its original project-root calculation would be wrong. The verified replay adapter reads these unchanged bytes and transforms only local import targets, the explicit project data root, and removal of the exact archived `sys.path.insert(0, str(ROOT))` bootstrap. Modules execute in a dedicated `_terragenesis_legacy_fault_v1_*` namespace, never under the bare retired `terrain_pipeline.metric_vdm_fault` name. Current generation does not import archived code.

Full v1 replay creates the original fault bundle, OBJ/review/report outputs plus a new `legacy-replay.json` sidecar. The sidecar records the archive, manifest pin, adapter hash, declared project data root, original source hashes and execution adaptations. Original `code_sha256` labels refer to archived source bytes, not the current wrapper files. The original algorithm, formulas and validator bytes remain unchanged. Archived dependencies are isolated from future edits to the active VDM/form helpers; numerical-library/environment reproducibility remains an explicit external requirement.

Current v2 geometry, topology, certification flags and output identities were unchanged by moving its shared recipe/weights. Tests check exact identity/array equality against the archived before-v2 implementation, legacy full-generation/cold replay, current production imports with no legacy modules loaded, namespace cleanup and unchanged `sys.path` on success and failure.
