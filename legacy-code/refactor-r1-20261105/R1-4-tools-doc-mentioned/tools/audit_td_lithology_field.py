"""Independent acceptance probe for the phase-1 lithology field.

Deliberately does NOT import the module's own validators; it re-derives every
check from the documented rule so a wrong implementation cannot certify itself.
Writes .scratch/lithology-01/acceptance.json and exits nonzero on any failure.

Run:  runtime\\venv\\Scripts\\python.exe tools/audit_td_lithology_field.py
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import td_lithology_field as L

WORLD_SEED = L.DEFAULT_WORLD_SEED
OUT_DIR = ROOT / ".scratch" / "lithology-01"


def check(record, name, passed, detail):
    record.append({"check": name, "passed": bool(passed), "detail": detail})
    print(("PASS " if passed else "FAIL ") + name + ": " + str(detail))
    return bool(passed)


def sha_unit(lattice_x, lattice_z, seed):
    """Scalar reimplementation of the lattice hash, for cross-checking."""
    mask = 2 ** 64 - 1
    value = ((lattice_x & mask) * 0x9E3779B185EBCA87) & mask
    value ^= ((lattice_z & mask) * 0xC2B2AE3D27D4EB4F) & mask
    value ^= seed
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    return (value >> 11) / 2 ** 53


def derive_expected_subseed(world_seed, purpose):
    payload = "terragenesis-lithology-v1|" + str(int(world_seed)) + "|" + purpose
    return int.from_bytes(hashlib.sha256(payload.encode("ascii")).digest()[:8], "big")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUT_DIR / "acceptance.json"))
    arguments = parser.parse_args(argv)
    record = []

    # -- 1. Attribute table shape and magnitudes ---------------------------
    identifiers = [entry["id"] for entry in L.ROCK_TABLE]
    check(record, "table_row_count", 15 <= len(identifiers) <= 20,
          "%d rocks" % len(identifiers))
    check(record, "table_ids_unique", len(set(identifiers)) == len(identifiers), sorted(identifiers))
    class_sizes = {c: sum(1 for e in L.ROCK_TABLE if e["class"] == c) for c in L.CLASS_IDS}
    check(record, "each_class_4_to_6_rocks", all(4 <= v <= 6 for v in class_sizes.values()), class_sizes)
    check(record, "all_three_classes_present",
          set(e["class"] for e in L.ROCK_TABLE) == set(L.CLASS_IDS), list(L.CLASS_IDS))

    field_failures = []
    for entry in L.ROCK_TABLE:
        for name in ("erodibility_index", "bed_hardness", "bank_hardness", "layering",
                     "fracture_density", "solubility", "porosity", "mohs_hardness"):
            value = entry[name]
            if not isinstance(value, float) or not math.isfinite(value):
                field_failures.append((entry["id"], name, "not finite float"))
        if not 0.0 <= entry["erodibility_index"] <= 1.0:
            field_failures.append((entry["id"], "erodibility_index", entry["erodibility_index"]))
        if not 0.0 <= entry["bed_hardness"] <= 1.0:
            field_failures.append((entry["id"], "bed_hardness", entry["bed_hardness"]))
        if not 0.0 <= entry["bank_hardness"] <= 1.0:
            field_failures.append((entry["id"], "bank_hardness", entry["bank_hardness"]))
        if entry["bank_hardness"] > entry["bed_hardness"]:
            field_failures.append((entry["id"], "bank_above_bed", entry["bank_hardness"]))
        if entry["value_status"] != L.PROVENANCE:
            field_failures.append((entry["id"], "value_status", entry["value_status"]))
    check(record, "attribute_ranges_and_bank_le_bed", not field_failures, field_failures[:8])

    # Independent re-derivation of the documented 0-1 rule.
    derive_mismatch = []
    for entry in L.ROCK_TABLE:
        h = min(max((entry["mohs_hardness"] - 1.0) / 6.0, 0.0), 1.0)
        p = min(max(entry["porosity"] / 0.40, 0.0), 1.0)
        erodibility = (0.45 * (1.0 - h) + 0.20 * entry["fracture_density"]
                       + 0.15 * entry["layering"] + 0.10 * entry["solubility"] + 0.10 * p)
        erodibility = min(max(erodibility, 0.0), 1.0)
        bed = min(max(1.0 - erodibility, 0.02), 0.98)
        bank = min(max(bed - 0.25 * entry["layering"] - 0.12 * entry["solubility"], 0.02), bed)
        for name, expected in (("erodibility_index", erodibility), ("bed_hardness", bed),
                               ("bank_hardness", bank)):
            if abs(entry[name] - expected) > 1e-12:
                derive_mismatch.append((entry["id"], name, entry[name], expected))
    check(record, "independent_derivation_matches_table", not derive_mismatch, derive_mismatch[:8])

    # Reference magnitudes: Mohs is a real scale, not a normalised 0-1 number.
    expectations = {"granite": (6.0, 7.0), "quartzite": (7.0, 7.0), "limestone": (2.5, 3.5),
                    "shale": (2.0, 3.0), "basalt": (5.5, 6.5), "marble": (3.0, 4.0),
                    "gneiss": (6.0, 7.0), "slate": (2.5, 4.0)}
    magnitude = [(rock, L.ROCK_BY_ID[rock]["mohs_hardness"], bounds) for rock, bounds in expectations.items()
                 if not bounds[0] <= L.ROCK_BY_ID[rock]["mohs_hardness"] <= bounds[1]]
    check(record, "mohs_reference_magnitudes", not magnitude, magnitude)
    check(record, "solubility_carbonate_high_silicate_low",
          all(L.ROCK_BY_ID[rock]["solubility"] >= 0.5 for rock in ("limestone", "dolomite", "marble"))
          and all(L.ROCK_BY_ID[rock]["solubility"] < 0.1 for rock in ("granite", "quartzite", "gabbro")),
          {rock: L.ROCK_BY_ID[rock]["solubility"]
           for rock in ("limestone", "dolomite", "marble", "granite", "quartzite", "gabbro")})

    # -- 2. Seeds ---------------------------------------------------------
    expected_subseeds = {purpose: derive_expected_subseed(WORLD_SEED, purpose)
                         for purpose in L.SEED_PURPOSES}
    check(record, "subseeds_match_documented_derivation",
          L.lithology_subseeds(WORLD_SEED) == expected_subseeds, expected_subseeds)
    check(record, "subseeds_are_distinct",
          len(set(expected_subseeds.values())) == len(expected_subseeds), expected_subseeds)

    # -- 3. Sampler stability against a scalar reimplementation ------------
    probe = L.sample_lithology((64, 64), origin_m_xz=(-64000., 32000.), spacing_m=1000.)
    arrays = probe["arrays"]
    # Compare the vectorised hash to the scalar one at exact lattice points
    # (fraction 0), where the quintic interpolation collapses to a corner value.
    hash_ok = True
    hash_detail = "64 probes"
    for index in range(64):
        generator_x = np.random.default_rng(1000 + index)
        generator_z = np.random.default_rng(2000 + index)
        lattice_x = int(generator_x.integers(-5000, 5000))
        lattice_z = int(generator_z.integers(-5000, 5000))
        scalar = sha_unit(lattice_x, lattice_z, 0x1234567)
        vector = float(L._value_noise(np.array([[float(lattice_x)]]),
                                      np.array([[float(lattice_z)]]),
                                      1.0, 0x1234567)[0, 0])
        if abs(scalar - vector) > 1e-15:
            hash_ok = False
            hash_detail = {"lattice_xz": [lattice_x, lattice_z],
                           "scalar": scalar, "vector": vector}
            break
    check(record, "lattice_hash_matches_scalar_reimplementation", hash_ok, hash_detail)

    repeat = L.sample_lithology((64, 64), origin_m_xz=(-64000., 32000.), spacing_m=1000.)
    bitwise = all(arrays[name].tobytes() == repeat["arrays"][name].tobytes()
                  for name in ("class_index", "rock_index", "bed_hardness", "bank_hardness"))
    check(record, "repeat_sampling_bitwise_identical", bitwise,
          probe["identity_sha256"][:16])

    spacing = 1000.0
    big = L.sample_lithology((80, 80), origin_m_xz=(0., 0.), spacing_m=spacing)
    rows = np.repeat(np.arange(80), 80)
    columns = np.tile(np.arange(80), 80)
    order = np.random.default_rng(WORLD_SEED).permutation(rows.size)
    x = (columns + 0.5) * spacing
    z = (rows + 0.5) * spacing
    points = L.sample_lithology_points(x[order], z[order])
    shuffled_ok = np.array_equal(points["rock_index"], big["arrays"]["rock_index"].ravel()[order])
    check(record, "shuffled_point_queries_agree_with_grid", shuffled_ok, "6400 points")

    sub = L.sample_lithology((20, 20), origin_m_xz=(30 * spacing, 40 * spacing), spacing_m=spacing)
    window_ok = all(np.array_equal(big["arrays"][name][40:60, 30:50], sub["arrays"][name])
                    for name in ("class_index", "rock_index", "bed_hardness", "bank_hardness"))
    check(record, "offset_window_agrees_with_large_window", window_ok, "20x20 sub-window")

    reversed_tiles = [L.sample_lithology((8, 8), origin_m_xz=origin, spacing_m=500.)["identity_sha256"]
                      for origin in [(0., 0.), (4000., 0.), (0., 4000.)]]
    forward_tiles = [L.sample_lithology((8, 8), origin_m_xz=origin, spacing_m=500.)["identity_sha256"]
                     for origin in [(0., 4000.), (4000., 0.), (0., 0.)]]
    check(record, "load_order_independent", reversed_tiles == list(reversed(forward_tiles)),
          [value[:8] for value in forward_tiles])

    # -- 4. Distribution coverage and proportions --------------------------
    class_counts = np.zeros(len(L.CLASS_IDS), np.int64)
    rock_counts = np.zeros(len(L.ROCK_ORDER), np.int64)
    windows = []
    for origin in [(-4000e3, -4000e3), (-1000e3, 3000e3), (2500e3, -1500e3), (5000e3, 5000e3)]:
        bundle = L.sample_lithology((400, 400), origin_m_xz=origin, spacing_m=4000.)
        report = L.compose_report(bundle)
        class_counts += np.bincount(bundle["arrays"]["class_index"].ravel(),
                                    minlength=len(L.CLASS_IDS))
        rock_counts += np.bincount(bundle["arrays"]["rock_index"].ravel(),
                                   minlength=len(L.ROCK_ORDER))
        windows.append({"origin_m_xz": list(origin), "identity_sha256": bundle["identity_sha256"],
                        "class_fractions": {k: v["fraction"] for k, v in report["classes"].items()},
                        "distinct_rocks": report["distinct_rocks"]})
    total = int(class_counts.sum())
    class_fractions = {c: float(class_counts[i] / total) for i, c in enumerate(L.CLASS_IDS)}
    declared = L.DEFAULT_PARAMETERS["class_weights"]
    check(record, "every_class_well_represented",
          all(class_counts[i] / total > 0.10 for i in range(len(L.CLASS_IDS))), class_fractions)
    check(record, "class_fractions_track_declared_within_0p07",
          all(abs(class_fractions[c] - declared[c]) < 0.07 for c in L.CLASS_IDS),
          {"observed": class_fractions, "declared": declared})
    check(record, "all_18_rocks_occur", int((rock_counts > 0).sum()) == len(L.ROCK_ORDER),
          "%d of %d" % (int((rock_counts > 0).sum()), len(L.ROCK_ORDER)))

    within_class = {}
    for class_id in L.CLASS_IDS:
        members = L.ROCK_ORDER_BY_CLASS[class_id]
        subtotal = sum(int(rock_counts[L.ROCK_POSITION[rock]]) for rock in members)
        within_class[class_id] = {rock: rock_counts[L.ROCK_POSITION[rock]] / subtotal for rock in members}
    deviations = [(rock, round(value, 4), L.DEFAULT_PARAMETERS["rock_weights"][class_id][rock])
                  for class_id, table in within_class.items() for rock, value in table.items()
                  if abs(value - L.DEFAULT_PARAMETERS["rock_weights"][class_id][rock]) > 0.06]
    check(record, "within_class_rock_fractions_track_declared", not deviations, deviations[:8])

    # -- 5. Bundle honesty and tamper rejection ---------------------------
    metadata = probe["metadata"]
    honesty = (metadata["synthetic_lithology"] is True and metadata["measured_lithology"] is False
               and metadata["tectonic_context"] is False
               and metadata["distribution_model"] == "simplified_two_level_value_noise"
               and metadata["value_status"] == L.PROVENANCE)
    check(record, "metadata_declares_simplified_unmeasured", honesty,
          {"synthetic_lithology": metadata["synthetic_lithology"],
           "measured_lithology": metadata["measured_lithology"],
           "tectonic_context": metadata["tectonic_context"],
           "value_status": metadata["value_status"]})
    check(record, "metadata_records_seed_and_subseeds",
          metadata["world_seed"] == WORLD_SEED and metadata["subseeds"] == expected_subseeds,
          metadata["subseeds"])

    check(record, "validation_accepts_valid_bundle", L.validate_lithology_field(probe) is True, "ok")

    tampered = L.sample_lithology((16, 16), origin_m_xz=(0., 0.), spacing_m=500.)
    tampered["arrays"]["bed_hardness"] = tampered["arrays"]["bed_hardness"] + 0.01
    try:
        L.validate_lithology_field(tampered)
        rejected = False
    except ValueError:
        rejected = True
    check(record, "validation_rejects_edited_hardness", rejected, "nonzero offset rejected")

    relabelled = L.sample_lithology((16, 16), origin_m_xz=(0., 0.), spacing_m=500.)
    relabelled["metadata"] = dict(relabelled["metadata"], measured_lithology=True)
    try:
        L.validate_lithology_field(relabelled)
        rejected = False
    except ValueError:
        rejected = True
    check(record, "validation_rejects_measured_claim", rejected, "measured_lithology=True rejected")

    # -- 6. Interface to the existing discharge rule ----------------------
    load = L.sample_lithology((32, 32), origin_m_xz=(0., 0.), spacing_m=1000.)
    bed, bank = L.discharge_geometry_inputs(load)
    interface_ok = (bed.shape == bank.shape == (32, 32) and bed.dtype == bank.dtype == np.float64
                    and bool(np.all((bed >= 0.) & (bed <= 1.)))
                    and bool(np.all((bank >= 0.) & (bank <= 1.))))
    check(record, "discharge_geometry_inputs_in_range", interface_ok,
          {"bed_min": float(bed.min()), "bed_max": float(bed.max()),
           "bank_min": float(bank.min()), "bank_max": float(bank.max())})

    from terrain_pipeline.surface_rivers.metric_discharge_geometry import build_discharge_geometry
    source = np.full((16, 16), 100.)
    channel = np.zeros(source.shape, bool)
    channel[8, :] = True
    monthly = np.ones((12, *source.shape))
    small = load["arrays"]
    geometry = build_discharge_geometry(source, monthly, channel, 1000.,
                                       bed_hardness=float(small["bed_hardness"].mean()),
                                       bank_hardness=float(small["bank_hardness"].mean()))
    solid = geometry["arrays"]["channel_width_m"][8, 8] > 0.
    check(record, "discharge_geometry_accepts_derived_hardness", solid,
          {"width_m": float(geometry["arrays"]["channel_width_m"][8, 8]),
           "depth_m": float(geometry["arrays"]["channel_depth_m"][8, 8])})

    passed = sum(1 for entry in record if entry["passed"])
    summary = {"checks_total": len(record), "checks_passed": passed,
               "checks_failed": len(record) - passed,
               "world_seed": WORLD_SEED, "subseeds": expected_subseeds,
               "rock_table_sha256": L.rock_table_identity(),
               "class_fractions": class_fractions,
               "rock_counts": {rock: int(rock_counts[L.ROCK_POSITION[rock]]) for rock in L.ROCK_ORDER},
               "windows": windows,
               "provenance": L.PROVENANCE,
               "distribution_model": "simplified_two_level_value_noise",
               "tectonic_context": False, "checks": record}
    target = Path(arguments.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print("")
    print("%d/%d checks passed" % (passed, len(record)))
    print("report:", target)
    return 0 if passed == len(record) else 1


if __name__ == "__main__":
    sys.exit(main())
