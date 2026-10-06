# Terrain artifact v1

This is a portable surface data contract. It does not certify terrain naturalness, river continuity, water budgets, a Houdini/Blender consumer, or Minecraft export.

## Coordinates and payload

- Local Cartesian metres, right handed: X east, Y up, Z south. This is not a geodetic CRS. `vertical_datum` names the chosen elevation reference and `sea_level_elevation_m` records sea level in that datum.
- `reference_elevation_m[z,x]` samples nodes of a regular grid. Node coordinates are `origin_x_m + x * spacing_x_m` and `origin_z_m + z * spacing_z_m`; spacing is in metres. Rectangular grids are supported.
- Optional `displacement_m[3,z,x]` has components `(dx,dy,dz)` in metres. Reconstructed positions are `(x,h,z) + d`. `vertical` requires zero `dx,dz`; `xyz` allows lateral movement but does not prove a nonfolding surface or topology. `reference_surface_id` hashes the grid geometry, datum and reference samples.
- A base artifact has no source and no nonzero displacement. A derived artifact names its source content ID. `verify_source(source)` checks that supplied source ID; loading a derived artifact alone cannot prove that the source package exists.
- Optional surface water has a boolean wet mask, water surface elevation in metres and discharge in cubic metres per physical second. All arrays are finite. Dry samples use a finite elevation placeholder and zero discharge; wet water surface cannot lie below the reconstructed bed. Discharge does not encode an offline iteration interval, and its averaging period is not inferred by this format.

## Storage and identity

`save_artifact(artifact, directory)` writes `manifest.json` and `arrays.npz` to a sibling temporary directory, validates it, then publishes a new directory. It refuses to overwrite a destination. `load_artifact(directory)` only reads and validates an existing complete package; missing data never triggers generation. The caller owns version selection, cancellation and lifecycle management.

The format version is separate from backend, algorithm and algorithm version. The algorithm identity hashes backend, algorithm, version, integer seed and canonical JSON parameters. The content ID hashes that identity, source ID, geometry, semantic fields and uncompressed array bytes; ZIP timestamps do not affect it. Loading rejects unknown versions, unexpected fields/files, duplicate JSON keys, unsafe array types, shape or hash mismatch and invalid physical values. NPZ loading sets `allow_pickle=False`.

The current `surface_rivers` output is not automatically accepted: its spacing may be in blocks, dry water samples may be NaN and runoff timing is not fixed in physical seconds. A future adapter must map units explicitly and diagnose failed constraints before constructing this artifact. Materials, volumes, caves, topology changes and multiple resolution layers require later versioned extensions; their absence here is not implicit support.

Run `python tools/verify_terrain_artifacts.py` for the fixed contract gate. Its machine readable result is `verification/terrain-artifacts/report.json`.
