import gzip
import json
import pickle

from engine import SimulationEngine
from world import Tile, WorldMap


def load_save(path: str):
    with open(path, "rb") as probe:
        prefix = probe.read(2)
    if prefix == b"\x1f\x8b":
        with gzip.open(path, "rb") as handle:
            return SimulationEngine._deserialize_save_payload(handle.read())
    with open(path, "rb") as handle:
        return pickle.load(handle)


def build_summary(data):
    world = data.get("world", {})
    population = data.get("population", {})
    tile_blob = world.get("tiles_compact", {})
    return {
        "schema_version": data.get("schema_version", 1),
        "seed": data.get("seed"),
        "calendar": data.get("calendar", {}),
        "weather": data.get("weather", {}),
        "world_summary": {
            "width": world.get("width"),
            "height": world.get("height"),
            "districts": len(world.get("districts", {})),
            "buildings": len(world.get("buildings", {})),
            "companies": len(world.get("companies", {})),
            "economic_history": len(world.get("economic_history", [])),
            "tile_schema": tile_blob.get("schema"),
            "tile_cells": len(tile_blob.get("terrain", [])),
        },
        "population_summary": {
            "people": len(population.get("people", {})),
            "households": len(population.get("households", {})),
            "player_id": population.get("player_id"),
        },
        "news_items": len(data.get("news", [])),
        "journal_entries": len(data.get("journal", [])),
        "timeline_events": len(data.get("timeline", [])),
    }


def expand_tiles(world_blob):
    if "tiles_compact" in world_blob:
        width = world_blob["width"]
        height = world_blob["height"]
        tiles = WorldMap._deserialize_tiles_compact(width, height, world_blob["tiles_compact"])
        return [[tile.__dict__.copy() for tile in row] for row in tiles]
    return world_blob.get("tiles", [])


def build_full_dump(data):
    expanded = dict(data)
    world_blob = dict(expanded.get("world", {}))
    world_blob["tiles"] = expand_tiles(world_blob)
    expanded["world"] = world_blob
    return expanded


data = load_save("life_sim_save.pkl")

with open("dump.txt", "w", encoding="utf-8") as out:
    out.write(str(build_full_dump(data)))
