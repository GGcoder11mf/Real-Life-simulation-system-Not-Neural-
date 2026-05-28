"""
engine.py

Main simulation engine. This file coordinates time, weather, events,
schedules, save/load, and ties together the world, entities, systems,
and UI layers. The architecture is intentionally explicit and verbose
so the simulation can be expanded rather than treated like a toy.
"""

from __future__ import annotations

import curses
import gzip
import importlib.util
import json
import math
import os
import pickle
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from entities import Person, Population
from systems import SimulationSystems
from world import WorldMap, clamp


SAVE_FILE = "life_sim_save.pkl"
SAVE_CONTAINER_MAGIC = b"RLS_SAVE_V2"
MSGPACK_AVAILABLE = importlib.util.find_spec("msgpack") is not None

if MSGPACK_AVAILABLE:
    import msgpack

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

SEASON_NAMES = ["Winter", "Spring", "Summer", "Autumn"]

WEATHER_TYPES = [
    "clear",
    "cloudy",
    "rain",
    "storm",
    "fog",
    "heatwave",
    "cold_snap",
]


@dataclass
class CalendarState:
    year: int = 2026
    month: int = 1
    day: int = 1
    hour: int = 6
    minute: int = 0
    day_index: int = 0

    def advance_hour(self) -> None:
        self.hour += 1
        if self.hour >= 24:
            self.hour = 0
            self.day += 1
            self.day_index += 1
            days_in_month = self.days_in_month()
            if self.day > days_in_month:
                self.day = 1
                self.month += 1
                if self.month > 12:
                    self.month = 1
                    self.year += 1

    def season(self) -> str:
        if self.month in (12, 1, 2):
            return "Winter"
        if self.month in (3, 4, 5):
            return "Spring"
        if self.month in (6, 7, 8):
            return "Summer"
        return "Autumn"

    def days_in_month(self) -> int:
        return {
            1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
            7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
        }[self.month]

    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]} {self.day}, {self.year} {self.hour:02d}:00"


@dataclass
class WeatherState:
    condition: str
    temperature_c: float
    wind_kph: float
    precipitation: float
    cloud_cover: float
    severity: float

    def summary(self) -> str:
        return (
            f"{self.condition.title()} "
            f"{self.temperature_c:0.1f}C "
            f"wind {self.wind_kph:0.0f}kph "
            f"rain {self.precipitation:0.2f}"
        )


@dataclass
class NewsItem:
    timestamp: str
    category: str
    headline: str
    detail: str
    importance: float


@dataclass
class TimelineEvent:
    timestamp: str
    event_type: str
    title: str
    payload: Dict[str, Any] = field(default_factory=dict)


class EventEngine:
    """
    Combines cross-system state into world-changing events.

    The event engine is intentionally not a story script. It watches
    stress, weather, local crime, economics, relationships, and karma
    and injects consequences back into the simulation state.
    """

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed + 999)

    def tick(self, engine: "SimulationEngine") -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        calendar = engine.calendar
        weather = engine.weather
        snapshot = engine.world.economic_history[-1] if engine.world.economic_history else None

        if snapshot and snapshot.unemployment_rate > 0.22 and self.rng.random() < 0.08:
            for company in engine.world.companies.values():
                company.bankruptcy_risk = clamp(company.bankruptcy_risk + 0.03, 0.0, 1.0)
            events.append(
                TimelineEvent(
                    timestamp=calendar.label(),
                    event_type="economy",
                    title="Local recession pressure increased across the city.",
                )
            )
        if weather.condition in {"storm", "heatwave", "cold_snap"} and self.rng.random() < 0.12:
            affected = self.rng.choice(list(engine.world.districts.values()))
            affected.crime_heat = clamp(affected.crime_heat + 0.03, 0.0, 1.0)
            affected.desirability = clamp(affected.desirability - 0.02, 0.0, 1.0)
            events.append(
                TimelineEvent(
                    timestamp=calendar.label(),
                    event_type="weather",
                    title=f"{weather.condition.title()} disrupted life in {affected.name}.",
                    payload={"district_id": affected.district_id},
                )
            )
        high_stress_people = [person for person in engine.population.people.values() if person.stress > 0.88]
        if high_stress_people and self.rng.random() < 0.08:
            person = self.rng.choice(high_stress_people)
            person.add_memory("personal", "Had a severe stress spiral.", -0.12, timestamp=calendar.label())
            person.motivation = clamp(person.motivation - 0.06, 0.0, 1.0)
            events.append(
                TimelineEvent(
                    timestamp=calendar.label(),
                    event_type="personal",
                    title=f"{person.full_name} hit a critical stress threshold.",
                )
            )
        goodwill_people = [
            person for person in engine.population.people.values()
            if person.hidden_karma > 0.78 and person.reputation_public > 0.68
        ]
        if goodwill_people and self.rng.random() < 0.05:
            person = self.rng.choice(goodwill_people)
            person.add_memory("social", "Received unexpected goodwill from the community.", 0.08, timestamp=calendar.label())
            person.bank_balance += 120.0
            events.append(
                TimelineEvent(
                    timestamp=calendar.label(),
                    event_type="social",
                    title=f"Community goodwill lifted {person.full_name}'s standing.",
                )
            )
        if calendar.hour == 8 and engine.world.companies and self.rng.random() < 0.06:
            company = self.rng.choice(list(engine.world.companies.values()))
            company.expansion_desire = clamp(company.expansion_desire + 0.1, 0.0, 1.0)
            events.append(
                TimelineEvent(
                    timestamp=calendar.label(),
                    event_type="company",
                    title=f"{company.name} signaled a new expansion push.",
                    payload={"company_id": company.company_id},
                )
            )
        return events


class SimulationEngine:
    """Full-life simulator runtime."""

    def __init__(self, seed: Optional[int] = None, world_seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else self.generate_seed()
        self.rng = random.Random(self.seed)
        self.world_seed = world_seed if world_seed is not None else random.SystemRandom().randrange(1, 1_000_000_007)
        self.world = WorldMap(self.world_seed)
        self.population = Population(self.seed, self.world, size=self.world.recommended_population_size())
        self.systems = SimulationSystems(self.seed, self.world)
        self._bootstrap_employment()
        self.calendar = CalendarState()
        self.weather = self.generate_weather()
        self.event_engine = EventEngine(self.seed)
        self.news: List[NewsItem] = []
        self.timeline: List[TimelineEvent] = []
        self.running = True
        self.paused = False
        self.tick_duration = 0.08
        self.tick_counter = 0
        self.autosave_interval_days = 7
        self.last_autosave_day = 0
        self.selected_person_id: Optional[int] = min(self.population.people) if self.population.people else None
        self.camera_x = self.world.width // 2
        self.camera_y = self.world.height // 2
        self.message_cache: List[str] = []
        self._macro_metrics_cache_tick = -1
        self._macro_metrics_cache: Dict[str, float] = {}
        if self.selected_person_id is not None:
            selected = self.population.people[self.selected_person_id]
            self.camera_x, self.camera_y = selected.location
        self.population.prepare_hour(self.calendar.day_index, self.calendar.hour)
        self.log_news(
            "engine",
            f"Simulation initialized from seed {self.seed} on world seed {self.world_seed}.",
            "A new city started running autonomously.",
            0.6,
        )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def _bootstrap_employment(self) -> None:
        for _ in range(10):
            self.systems.company.spawn_hiring_waves()
            self.systems.company.run_hiring(self.population)
        self.world.prune_empty_companies()

    @staticmethod
    def generate_seed() -> int:
        return int(time.time()) % 1_000_000_007

    def generate_weather(self) -> WeatherState:
        season = self.calendar.season()
        base_temp = {
            "Winter": 8.0,
            "Spring": 19.0,
            "Summer": 31.0,
            "Autumn": 20.0,
        }[season]
        condition = self.rng.choices(
            WEATHER_TYPES,
            weights={
                "clear": 28,
                "cloudy": 22,
                "rain": 16,
                "storm": 4,
                "fog": 8,
                "heatwave": 3 if season == "Summer" else 1,
                "cold_snap": 3 if season == "Winter" else 1,
            }.values(),
            k=1,
        )[0]
        temp_shift = {
            "clear": self.rng.uniform(-3, 3),
            "cloudy": self.rng.uniform(-2, 2),
            "rain": self.rng.uniform(-4, 1),
            "storm": self.rng.uniform(-5, 2),
            "fog": self.rng.uniform(-4, 0),
            "heatwave": self.rng.uniform(5, 9),
            "cold_snap": self.rng.uniform(-9, -4),
        }[condition]
        precipitation = {
            "clear": 0.0,
            "cloudy": 0.05,
            "rain": self.rng.uniform(0.35, 0.8),
            "storm": self.rng.uniform(0.7, 1.0),
            "fog": 0.1,
            "heatwave": 0.0,
            "cold_snap": 0.0,
        }[condition]
        cloud_cover = {
            "clear": 0.1,
            "cloudy": 0.75,
            "rain": 0.88,
            "storm": 1.0,
            "fog": 0.65,
            "heatwave": 0.15,
            "cold_snap": 0.2,
        }[condition]
        severity = clamp(precipitation + abs(temp_shift) / 10.0, 0.0, 1.0)
        return WeatherState(
            condition=condition,
            temperature_c=round(base_temp + temp_shift, 1),
            wind_kph=round(self.rng.uniform(4, 38) + severity * 22, 1),
            precipitation=round(precipitation, 2),
            cloud_cover=cloud_cover,
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Logging and timeline
    # ------------------------------------------------------------------
    def log_news(self, category: str, headline: str, detail: str, importance: float) -> None:
        item = NewsItem(self.calendar.label(), category, headline, detail, importance)
        self.news.append(item)
        self.news = self.news[-240:]
        self.message_cache.append(headline)
        self.message_cache = self.message_cache[-20:]

    def log_timeline(self, event_type: str, title: str, payload: Optional[Dict[str, Any]] = None) -> None:
        event = TimelineEvent(self.calendar.label(), event_type, title, payload or {})
        self.timeline.append(event)
        self.timeline = self.timeline[-400:]

    # ------------------------------------------------------------------
    # Main ticking
    # ------------------------------------------------------------------
    def step(self) -> None:
        if self.paused:
            return
        current_hour = self.calendar.hour
        current_day = self.calendar.day_index

        if current_hour == 0:
            self._run_daily_cycle()

        self.population.hourly_update(current_day, current_hour)
        self._apply_weather_effects_hourly()
        self._run_event_engine()

        self.calendar.advance_hour()
        if self.calendar.hour == 0:
            self.weather = self.generate_weather()
            self.log_news("weather", f"Forecast updated: {self.weather.condition}.", self.weather.summary(), 0.3)
        self.population.prepare_hour(self.calendar.day_index, self.calendar.hour)
        self.tick_counter += 1

    def _run_daily_cycle(self) -> None:
        day_index = self.calendar.day_index
        self.world.tick_daily_world(day_index)
        self.population.daily_update(day_index)
        report = self.systems.tick_daily(self.population, day_index)
        self._ingest_system_report(report)
        self._daily_story_events()
        if day_index - self.last_autosave_day >= self.autosave_interval_days:
            self.save(SAVE_FILE)
            self.last_autosave_day = day_index

    def _ingest_system_report(self, report: Dict[str, List[str]]) -> None:
        for category, items in report.items():
            for text in items[:24]:
                importance = 0.4 if category in {"hiring", "social", "crime", "courts"} else 0.25
                self.log_news(category, text, f"Generated by {category} system.", importance)
                self.log_timeline(category, text)

    def _apply_weather_effects_hourly(self) -> None:
        for person in self.population.people.values():
            if self.weather.condition == "storm":
                person.stress = clamp(person.stress + 0.004, 0.0, 1.0)
                person.energy = clamp(person.energy - 0.003, 0.0, 1.0)
            elif self.weather.condition == "heatwave":
                person.energy = clamp(person.energy - 0.004, 0.0, 1.0)
            elif self.weather.condition == "clear":
                person.happiness = clamp(person.happiness + 0.002, 0.0, 1.0)

    def _run_event_engine(self) -> None:
        events = self.event_engine.tick(self)
        for event in events:
            self.timeline.append(event)
            self.timeline = self.timeline[-400:]
            self.log_news(event.event_type, event.title, json.dumps(event.payload) if event.payload else "Triggered by event engine.", 0.55)

    def _daily_story_events(self) -> None:
        top_company = max(self.world.companies.values(), key=lambda company: company.market_value) if self.world.companies else None
        top_district = max(self.world.districts.values(), key=lambda district: district.desirability) if self.world.districts else None
        if top_company is not None and self.calendar.day_index % 7 == 0:
            self.log_news(
                "weekly",
                f"{top_company.name} led the market this week.",
                f"{top_company.stock_symbol} is the highest-valued listed company in the city.",
                0.45,
            )
        if top_district is not None and top_district.average_rent > 1300 and self.rng.random() < 0.2:
            self.log_news(
                "housing",
                f"Rents continued climbing in {top_district.name}.",
                f"Average rent reached {top_district.average_rent:.0f}.",
                0.35,
            )

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 2,
            "seed": self.seed,
            "world_seed": self.world_seed,
            "calendar": self.calendar.__dict__,
            "weather": self.weather.__dict__,
            "world": self.world.to_dict(),
            "population": self.population.to_dict(),
            "systems": self.systems.to_dict(),
            "news": [item.__dict__ for item in self.news],
            "timeline": [event.__dict__ for event in self.timeline],
            "paused": self.paused,
            "tick_duration": self.tick_duration,
            "last_autosave_day": self.last_autosave_day,
            "selected_person_id": self.selected_person_id,
            "camera_x": self.camera_x,
            "camera_y": self.camera_y,
            "message_cache": self.message_cache,
        }

    @staticmethod
    def _serialize_save_payload(data: Dict[str, Any]) -> bytes:
        codec = "msgpack" if MSGPACK_AVAILABLE else "pickle"
        if codec == "msgpack":
            payload = msgpack.packb(data, use_bin_type=True)
        else:
            payload = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        return SAVE_CONTAINER_MAGIC + codec.encode("ascii") + b"\n" + payload

    @staticmethod
    def _deserialize_save_payload(blob: bytes) -> Dict[str, Any]:
        if blob.startswith(SAVE_CONTAINER_MAGIC):
            codec_and_payload = blob[len(SAVE_CONTAINER_MAGIC):]
            codec_line, payload = codec_and_payload.split(b"\n", 1)
            codec = codec_line.decode("ascii")
            if codec == "msgpack":
                if not MSGPACK_AVAILABLE:
                    raise RuntimeError("This save was written with msgpack, but msgpack is not installed.")
                return msgpack.unpackb(payload, raw=False)
            return pickle.loads(payload)
        return pickle.loads(blob)

    def save(self, path: str) -> None:
        with open(path, "wb") as handle:
            pickle.dump(self.to_dict(), handle, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _soft_cap(value: float, threshold: float, scale: float) -> float:
        if value <= threshold:
            return value
        return threshold + math.log10(1.0 + value - threshold) * scale

    def _stabilize_loaded_state(self) -> None:
        self.world.prune_empty_companies(include_with_openings=True)
        self.world.normalize_company_structure()
        self.world.stabilize_economy_state()
        for person in self.population.people.values():
            person.cash = self._soft_cap(max(0.0, person.cash), 250_000.0, 40_000.0)
            person.bank_balance = self._soft_cap(max(0.0, person.bank_balance), 750_000.0, 90_000.0)
            person.assets = self._soft_cap(max(0.0, person.assets), 1_000_000.0, 120_000.0)
            person.debt = self._soft_cap(max(0.0, person.debt), 500_000.0, 80_000.0)
        for stock in self.systems.stock_market.stocks.values():
            company = self.world.companies.get(stock.company_id)
            if company is None:
                continue
            stock.price = round(max(1.0, company.market_value / 120_000.0), 2)
            stock.last_change = clamp(stock.last_change, -0.25, 0.25)

    @classmethod
    def load(cls, path: str) -> "SimulationEngine":
        with open(path, "rb") as probe:
            prefix = probe.read(2)
        if prefix == b"\x1f\x8b":
            with gzip.open(path, "rb") as handle:
                data = cls._deserialize_save_payload(handle.read())
        else:
            with open(path, "rb") as handle:
                data = pickle.load(handle)
        engine = cls(seed=data["seed"], world_seed=data.get("world_seed", data["world"].get("seed", data["seed"])))
        engine.calendar = CalendarState(**data["calendar"])
        engine.weather = WeatherState(**data["weather"])
        engine.world = WorldMap.from_dict(data["world"])
        engine.world_seed = engine.world.seed
        engine.population = Population.from_dict(
            data["population"],
            engine.world,
            schedule_day_index=engine.calendar.day_index,
        )
        engine.systems = SimulationSystems.from_dict(engine.seed, engine.world, data["systems"])
        engine.news = [NewsItem(**item) for item in data["news"]]
        engine.timeline = [TimelineEvent(**event) for event in data["timeline"]]
        engine.paused = data["paused"]
        engine.tick_duration = data["tick_duration"]
        engine.last_autosave_day = data["last_autosave_day"]
        engine.selected_person_id = data["selected_person_id"]
        engine.camera_x = data["camera_x"]
        engine.camera_y = data["camera_y"]
        engine.message_cache = list(data["message_cache"])
        engine.event_engine = EventEngine(engine.seed)
        engine._stabilize_loaded_state()
        engine.population.prepare_hour(engine.calendar.day_index, engine.calendar.hour)
        return engine

    # ------------------------------------------------------------------
    # Input / control helpers used by the terminal UI
    # ------------------------------------------------------------------
    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.log_news("engine", "Simulation paused." if self.paused else "Simulation resumed.", "Input toggled runtime pause state.", 0.1)

    def change_speed(self, faster: bool) -> None:
        if faster:
            self.tick_duration = max(0.01, self.tick_duration * 0.7)
        else:
            self.tick_duration = min(0.4, self.tick_duration * 1.3)

    def move_camera(self, dx: int, dy: int) -> None:
        self.camera_x = max(0, min(self.world.width - 1, self.camera_x + dx))
        self.camera_y = max(0, min(self.world.height - 1, self.camera_y + dy))

    def center_on_selected_person(self) -> None:
        person = self.selected_person()
        self.camera_x, self.camera_y = person.location

    def cycle_selected_person(self) -> None:
        ids = sorted(self.population.people.keys())
        if not ids:
            return
        if self.selected_person_id not in ids:
            self.selected_person_id = ids[0]
            return
        idx = ids.index(self.selected_person_id)
        self.selected_person_id = ids[(idx + 1) % len(ids)]

    def selected_person(self) -> Person:
        if self.selected_person_id is None or self.selected_person_id not in self.population.people:
            self.selected_person_id = min(self.population.people) if self.population.people else None
        if self.selected_person_id is None:
            raise RuntimeError("Population has no citizens.")
        return self.population.people[self.selected_person_id]

    def recent_headlines(self, limit: int = 8) -> List[str]:
        return [item.headline for item in self.news[-limit:]][::-1]

    def recent_timeline_lines(self, limit: int = 8) -> List[str]:
        return [f"{event.timestamp[-5:]} {event.title[:52]}" for event in self.timeline[-limit:]][::-1]

    # ------------------------------------------------------------------
    # Derived metrics for UI and debugging
    # ------------------------------------------------------------------
    def macro_metrics(self) -> Dict[str, float]:
        if self._macro_metrics_cache_tick == self.tick_counter and self._macro_metrics_cache:
            return self._macro_metrics_cache
        snapshot = self.world.economic_history[-1]
        population = list(self.population.people.values())
        avg_happiness = sum(person.happiness for person in population) / max(1, len(population))
        avg_stress = sum(person.stress for person in population) / max(1, len(population))
        avg_karma = sum(person.hidden_karma for person in population) / max(1, len(population))
        incarceration = len(self.systems.law.inmates) / max(1, len(population))
        self._macro_metrics_cache = {
            "unemployment": snapshot.unemployment_rate,
            "housing_index": snapshot.housing_index,
            "crime_index": snapshot.crime_index,
            "avg_happiness": avg_happiness,
            "avg_stress": avg_stress,
            "avg_karma": avg_karma,
            "incarceration_rate": incarceration,
        }
        self._macro_metrics_cache_tick = self.tick_counter
        return self._macro_metrics_cache

    def weather_impact_lines(self) -> List[str]:
        return [
            f"Season: {self.calendar.season()}",
            f"Condition: {self.weather.condition}",
            f"Temp: {self.weather.temperature_c:0.1f} C",
            f"Wind: {self.weather.wind_kph:0.0f} kph",
            f"Precip: {self.weather.precipitation:0.2f}",
            f"Severity: {self.weather.severity:0.2f}",
        ]

    # ------------------------------------------------------------------
    # Console runtime
    # ------------------------------------------------------------------
    def run_terminal(self) -> None:
        from ui import TerminalUI

        ui = TerminalUI(self)
        try:
            curses.wrapper(ui.run)
        except Exception:
            print("Simulation crashed with an uncaught exception:")
            print(traceback.format_exc())
            raise


def main() -> None:
    engine = SimulationEngine()
    engine.run_terminal()


if __name__ == "__main__":
    main()
