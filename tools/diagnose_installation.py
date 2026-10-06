"""Read game metadata; write only an explicit report within this workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from struct import error as struct_error
from pathlib import Path

from nbt_reader import NbtReader

ROOT = Path(__file__).resolve().parents[1]


def inspect_world(path: Path) -> dict:
    data = NbtReader.read_file(path).get("Data", {})
    settings = data.get("WorldGenSettings", {})
    settings_path = path.parent / "data/minecraft/world_gen_settings.dat"
    if settings_path.exists():
        settings = NbtReader.read_file(settings_path).get("data", {})
    dimensions = settings.get("dimensions", {})
    generators = {
        key: value.get("generator", {}).get("type")
        for key, value in dimensions.items()
    }
    return {
        "directory": path.parent.name,
        "level_name": data.get("LevelName"),
        "version": data.get("Version"),
        "generators": generators,
        "overworld_generator": generators.get("minecraft:overworld"),
        "terrain_source": dimensions.get("minecraft:overworld", {}).get("generator", {}).get("terrain_source", "legacy_auto"),
        "remote_terrain_active": generators.get("minecraft:overworld") == "remotemountains:landforms",
        "settings_file": str(settings_path.relative_to(path.parent)) if settings_path.exists() else "level.dat",
        "spawn": data.get("spawn"),
        "worldgen_keys": sorted(settings),
        "enabled_datapacks": data.get("DataPacks", {}).get("Enabled", []),
        "player_position": data.get("Player", {}).get("Pos"),
    }


def inspect_installation(game: Path) -> dict:
    mods = []
    for jar in sorted((game / "mods").glob("*RemoteMountains*.jar")):
        with zipfile.ZipFile(jar) as archive:
            mods.append({
                "file": jar.name,
                "sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
                "metadata": json.loads(archive.read("fabric.mod.json")),
                "preset_menu": json.loads(archive.read(
                    "data/minecraft/tags/worldgen/world_preset/normal.json")),
            })
    worlds = []
    for level in sorted((game / "saves").glob("*/level.dat")):
        try:
            worlds.append(inspect_world(level))
        except (OSError, ValueError, struct_error) as exc:
            worlds.append({"directory": level.parent.name, "error": str(exc)})
    log = game / "logs/latest.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    return {
        "game_directory": str(game),
        "read_only_game_inspection": True,
        "mods": mods,
        "worlds": worlds,
        "mod_load_log": [line for line in lines if re.search(r"^\s*- remotemountains ", line)],
        "relevant_errors": [line for line in lines if "remotemountains" in line.lower() and re.search(r"ERROR|Exception|Failed", line)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("game", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Report must remain inside this workspace")
    report = inspect_installation(args.game)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
