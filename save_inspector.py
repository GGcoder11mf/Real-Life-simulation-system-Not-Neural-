from __future__ import annotations

import gzip
import os
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

try:
    import importlib.util

    MSGPACK_AVAILABLE = importlib.util.find_spec("msgpack") is not None
    if MSGPACK_AVAILABLE:
        import msgpack
except Exception:
    MSGPACK_AVAILABLE = False


WINDOW_SIZE = (1480, 920)
FPS = 60
SAVE_CONTAINER_MAGIC = b"RLS_SAVE_V2"
SAVE_EXTENSIONS = {".pkl", ".pickle", ".sav", ".save", ".gz"}
UI_BG = (15, 20, 28)
PANEL_BG = (24, 31, 42)
PANEL_ALT = (34, 42, 57)
PANEL_SOFT = (43, 53, 72)
CARD_BG = (30, 37, 49)
CARD_HOVER = (42, 51, 67)
CARD_SELECTED = (54, 91, 120)
TEXT = (236, 240, 245)
TEXT_MUTED = (166, 178, 193)
TEXT_FAINT = (124, 138, 156)
ACCENT = (77, 174, 255)
ACCENT_DIM = (53, 116, 170)
GOOD = (91, 214, 138)
WARN = (240, 199, 92)
BAD = (236, 103, 103)
SHADOW = (7, 10, 15)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_money(value: Any) -> str:
    if value is None:
        return "-"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:.1f}K"
    return f"{sign}${amount:.0f}"


def format_ratio(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def ensure_tuple(value: Any) -> Tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    return (0, 0)


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def preview_value(value: Any, max_len: int = 120) -> str:
    text = safe_text(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def relationship_value(rel: Any, field: str) -> float:
    if isinstance(rel, dict):
        try:
            return float(rel.get(field, 0.0))
        except (TypeError, ValueError):
            return 0.0
    if isinstance(rel, (list, tuple)):
        field_positions = {
            "affinity": 0,
            "trust": 1,
            "romance": 2,
            "respect": 3,
            "familiarity": 4,
            "rivalry": 5,
            "gossip_knowledge": 6,
            "last_interaction_day": 7,
            "interaction_count": 8,
        }
        index = field_positions.get(field)
        if index is None or index >= len(rel):
            return 0.0
        try:
            return float(rel[index])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def memory_field(memory: Any, field: str) -> Any:
    if isinstance(memory, dict):
        return memory.get(field)
    if isinstance(memory, (list, tuple)):
        field_positions = {
            "timestamp": 0,
            "category": 1,
            "headline": 2,
            "impact": 3,
            "location": 4,
            "related_people": 5,
            "tags": 6,
        }
        index = field_positions.get(field)
        if index is None or index >= len(memory):
            return None
        return memory[index]
    return None


def read_save_blob(path: Path) -> bytes:
    with path.open("rb") as probe:
        prefix = probe.read(2)
    if prefix == b"\x1f\x8b":
        with gzip.open(path, "rb") as handle:
            return handle.read()
    with path.open("rb") as handle:
        return handle.read()


def decode_save_blob(blob: bytes) -> Dict[str, Any]:
    if blob.startswith(SAVE_CONTAINER_MAGIC):
        codec_and_payload = blob[len(SAVE_CONTAINER_MAGIC):]
        codec_line, payload = codec_and_payload.split(b"\n", 1)
        codec = codec_line.decode("ascii")
        if codec == "msgpack":
            if not MSGPACK_AVAILABLE:
                raise RuntimeError("Save uses msgpack but msgpack is not installed.")
            return msgpack.unpackb(payload, raw=False)
        return pickle.loads(payload)
    return pickle.loads(blob)


def load_save_data(path: Path) -> Dict[str, Any]:
    return decode_save_blob(read_save_blob(path))


def build_save_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    world = data.get("world", {})
    population = data.get("population", {})
    systems = data.get("systems", {})
    return {
        "schema": data.get("schema_version", world.get("schema_version", 1)),
        "seed": data.get("seed"),
        "world_seed": data.get("world_seed", world.get("seed")),
        "date": format_calendar(data.get("calendar", {})),
        "weather": format_weather(data.get("weather", {})),
        "people": len(population.get("people", {})),
        "households": len(population.get("households", {})),
        "companies": len(world.get("companies", {})),
        "districts": len(world.get("districts", {})),
        "buildings": len(world.get("buildings", {})),
        "transit": len(world.get("transit_lines", {})),
        "stocks": len(systems.get("stocks", {})),
        "news": len(data.get("news", [])),
        "timeline": len(data.get("timeline", [])),
    }


def format_calendar(calendar: Dict[str, Any]) -> str:
    if not calendar:
        return "Unknown date"
    month = int(calendar.get("month", 0))
    months = [
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    month_name = months[month] if 0 <= month < len(months) else str(month)
    return f"{month_name} {calendar.get('day', '?')}, {calendar.get('year', '?')} {int(calendar.get('hour', 0)):02d}:00"


def format_weather(weather: Dict[str, Any]) -> str:
    if not weather:
        return "Unknown weather"
    return (
        f"{safe_text(weather.get('condition', 'clear')).title()} "
        f"{float(weather.get('temperature_c', 0.0)):.1f}C "
        f"wind {float(weather.get('wind_kph', 0.0)):.0f}kph"
    )


@dataclass
class EntityRecord:
    category: str
    record_id: str
    title: str
    subtitle: str
    search_text: str
    sort_values: Dict[str, Any]
    badges: List[str]
    details: List[Tuple[str, str]]
    sections: List[Tuple[str, List[str]]] = field(default_factory=list)


@dataclass
class SavePreview:
    path: Path
    status: str
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SaveIndex:
    def __init__(self, path: Path, data: Dict[str, Any]) -> None:
        self.path = path
        self.data = data
        self.summary = build_save_summary(data)
        self.records: List[EntityRecord] = []
        self.by_category: Dict[str, List[EntityRecord]] = {}
        self.sort_options: Dict[str, List[Tuple[str, str]]] = {}
        self._build()

    def _build(self) -> None:
        self.records.extend(self._build_people())
        self.records.extend(self._build_companies())
        self.records.extend(self._build_households())
        self.records.extend(self._build_districts())
        self.records.extend(self._build_buildings())
        self.records.extend(self._build_transit())
        self.records.extend(self._build_stocks())
        self.records.extend(self._build_news())
        self.records.extend(self._build_timeline())
        self.by_category = {"all": list(self.records)}
        for record in self.records:
            self.by_category.setdefault(record.category, []).append(record)
        self.sort_options = {
            "all": [("name", "Name"), ("id", "ID"), ("category", "Category")],
            "people": [("name", "Name"), ("wealth", "Wealth"), ("happiness", "Happiness"), ("stress", "Stress"), ("age", "Age")],
            "companies": [("name", "Name"), ("value", "Market Value"), ("health", "Health"), ("employees", "Employees")],
            "households": [("name", "Name"), ("members", "Members"), ("costs", "Monthly Cost"), ("savings", "Savings")],
            "districts": [("name", "Name"), ("wealth", "Wealth"), ("crime", "Crime"), ("desirability", "Desirability")],
            "buildings": [("name", "Name"), ("rent", "Rent"), ("capacity", "Capacity"), ("quality", "Quality")],
            "transit": [("name", "Name"), ("stops", "Stops"), ("speed", "Speed")],
            "stocks": [("name", "Name"), ("price", "Price"), ("change", "Change"), ("volume", "Volume")],
            "news": [("id", "Newest"), ("importance", "Importance"), ("name", "Headline")],
            "timeline": [("id", "Newest"), ("name", "Title"), ("category", "Type")],
        }

    def records_for(self, category: str) -> List[EntityRecord]:
        return self.by_category.get(category, [])

    def _build_people(self) -> List[EntityRecord]:
        population = self.data.get("population", {})
        people = population.get("people", {})
        households = population.get("households", {})
        world = self.data.get("world", {})
        companies = world.get("companies", {})
        buildings = world.get("buildings", {})
        records: List[EntityRecord] = []
        for person_id, person in people.items():
            household = households.get(str(person.get("household_id"))) or households.get(person.get("household_id"))
            company = companies.get(str(person.get("job_company_id"))) or companies.get(person.get("job_company_id"))
            home_building = buildings.get(str(person.get("home_building_id"))) or buildings.get(person.get("home_building_id"))
            wealth = float(person.get("cash", 0.0)) + float(person.get("bank_balance", 0.0)) + float(person.get("assets", 0.0)) - float(person.get("debt", 0.0))
            location = ensure_tuple(person.get("location"))
            badges = [
                person.get("job_title") or "Unemployed",
                person.get("education_level", "unknown"),
                person.get("vehicle", "none"),
            ]
            details = [
                ("ID", str(person_id)),
                ("Age", safe_text(person.get("age"))),
                ("Gender", safe_text(person.get("gender"))),
                ("Life Stage", safe_text(person.get("life_stage"))),
                ("Job", safe_text(person.get("job_title") or "Unemployed")),
                ("Employer", safe_text(company.get("name") if company else "-")),
                ("Home", safe_text(home_building.get("name") if home_building else "-")),
                ("Household", safe_text(person.get("household_id"))),
                ("Location", f"{location[0]}, {location[1]}"),
                ("Cash", format_money(person.get("cash"))),
                ("Bank", format_money(person.get("bank_balance"))),
                ("Assets", format_money(person.get("assets"))),
                ("Debt", format_money(person.get("debt"))),
                ("Net Worth", format_money(wealth)),
                ("Salary", format_money(person.get("salary"))),
                ("Health", format_ratio(person.get("health"))),
                ("Energy", format_ratio(person.get("energy"))),
                ("Stress", format_ratio(person.get("stress"))),
                ("Happiness", format_ratio(person.get("happiness"))),
                ("Motivation", format_ratio(person.get("motivation"))),
                ("Reputation", format_ratio(person.get("reputation_public"))),
                ("Karma", format_ratio(person.get("hidden_karma"))),
            ]
            skill_items = sorted((person.get("skills") or {}).items(), key=lambda item: item[1], reverse=True)[:6]
            relationship_items = sorted(
                (person.get("relationships") or {}).items(),
                key=lambda item: relationship_value(item[1], "familiarity"),
                reverse=True,
            )[:5]
            memory_items = list(person.get("memories", []))[-5:]
            sections = [
                ("Top Skills", [f"{name}: {float(value):.2f}" for name, value in skill_items] or ["No skill data"]),
                (
                    "Relationships",
                    [
                        f"Person {other_id}: affinity {relationship_value(rel, 'affinity'):.2f}, trust {relationship_value(rel, 'trust'):.2f}"
                        for other_id, rel in relationship_items
                    ]
                    or ["No relationships"],
                ),
                (
                    "Recent Memories",
                    [
                        f"{safe_text(memory_field(memory, 'timestamp'))}: {safe_text(memory_field(memory, 'headline'))}"
                        for memory in memory_items
                    ]
                    or ["No memories"],
                ),
                (
                    "Family",
                    [
                        f"Household {person.get('household_id')} with {len(household.get('member_ids', [])) if household else 0} members",
                        f"Family IDs: {', '.join(str(pid) for pid in person.get('family_ids', [])[:10]) or '-'}",
                        f"Children IDs: {', '.join(str(pid) for pid in person.get('children_ids', [])[:10]) or '-'}",
                    ],
                ),
            ]
            records.append(
                EntityRecord(
                    category="people",
                    record_id=str(person_id),
                    title=safe_text(person.get("full_name", f"Person {person_id}")),
                    subtitle=f"{person.get('job_title') or 'Unemployed'} | age {person.get('age')} | {format_money(wealth)}",
                    search_text=" ".join(
                        [
                            safe_text(person.get("full_name")),
                            safe_text(person.get("job_title")),
                            safe_text(person.get("education_level")),
                            safe_text(person.get("gender")),
                            safe_text(person.get("life_stage")),
                            safe_text(company.get("name") if company else ""),
                            safe_text(home_building.get("name") if home_building else ""),
                            " ".join(safe_text(text) for text in person.get("certifications", [])),
                        ]
                    ).lower(),
                    sort_values={
                        "name": safe_text(person.get("full_name")).lower(),
                        "id": int(person_id),
                        "category": "people",
                        "wealth": wealth,
                        "happiness": float(person.get("happiness", 0.0)),
                        "stress": float(person.get("stress", 0.0)),
                        "age": int(person.get("age", 0)),
                    },
                    badges=badges,
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_companies(self) -> List[EntityRecord]:
        world = self.data.get("world", {})
        companies = world.get("companies", {})
        districts = world.get("districts", {})
        buildings = world.get("buildings", {})
        records: List[EntityRecord] = []
        for company_id, company in companies.items():
            district = districts.get(str(company.get("district_id"))) or districts.get(company.get("district_id"))
            building = buildings.get(str(company.get("building_id"))) or buildings.get(company.get("building_id"))
            employees = len(company.get("employee_ids", []))
            if employees <= 0:
                continue
            health = self._company_health_score(company)
            details = [
                ("ID", str(company_id)),
                ("Sector", safe_text(company.get("sector"))),
                ("Scale", safe_text(company.get("company_scale"))),
                ("District", safe_text(district.get("name") if district else "-")),
                ("Building", safe_text(building.get("name") if building else "-")),
                ("Employees", safe_text(employees)),
                ("Open Positions", safe_text(len(company.get("open_positions", [])))),
                ("Value", format_money(company.get("market_value"))),
                ("Cash", format_money(company.get("cash"))),
                ("Payroll", format_money(company.get("payroll_budget"))),
                ("Demand", format_ratio(company.get("demand"))),
                ("Supply", format_ratio(company.get("supply"))),
                ("Productivity", format_ratio(company.get("productivity"))),
                ("Prestige", format_ratio(company.get("prestige"))),
                ("Health", format_ratio(health)),
                ("Risk", format_ratio(company.get("bankruptcy_risk"))),
                ("Target Headcount", safe_text(company.get("target_headcount"))),
                ("Stock Symbol", safe_text(company.get("stock_symbol") or "-")),
            ]
            sections = [
                ("Open Positions", [safe_text(role) for role in company.get("open_positions", [])[:12]] or ["No open positions"]),
                (
                    "Shift Templates",
                    [f"{shift[0]:02d}:00-{shift[1]:02d}:00" for shift in company.get("shift_templates", [])[:8]]
                    or ["No shift templates"],
                ),
                (
                    "Employee IDs",
                    [", ".join(str(pid) for pid in company.get("employee_ids", [])[:20])] or ["No employees"],
                ),
            ]
            records.append(
                EntityRecord(
                    category="companies",
                    record_id=str(company_id),
                    title=safe_text(company.get("name", f"Company {company_id}")),
                    subtitle=f"{company.get('sector')} | {employees} employees | {format_money(company.get('market_value'))}",
                    search_text=" ".join(
                        [
                            safe_text(company.get("name")),
                            safe_text(company.get("sector")),
                            safe_text(company.get("company_scale")),
                            safe_text(district.get("name") if district else ""),
                            safe_text(building.get("name") if building else ""),
                            safe_text(company.get("stock_symbol")),
                        ]
                    ).lower(),
                    sort_values={
                        "name": safe_text(company.get("name")).lower(),
                        "id": int(company_id),
                        "category": "companies",
                        "value": float(company.get("market_value", 0.0)),
                        "health": health,
                        "employees": employees,
                    },
                    badges=[safe_text(company.get("sector")), safe_text(company.get("company_scale")), safe_text(company.get("stock_symbol") or "private")],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _company_health_score(self, company: Dict[str, Any]) -> float:
        payroll = max(1.0, float(company.get("payroll_budget", 0.0)))
        liquidity = clamp(float(company.get("cash", 0.0)) / payroll, 0.0, 1.0)
        balance = clamp((float(company.get("demand", 0.0)) - float(company.get("supply", 0.0))) * 0.5 + 0.5, 0.0, 1.0)
        risk = clamp(1.0 - float(company.get("bankruptcy_risk", 0.0)), 0.0, 1.0)
        productivity = clamp(float(company.get("productivity", 0.0)), 0.0, 1.0)
        return (liquidity + balance + risk + productivity) / 4.0

    def _build_households(self) -> List[EntityRecord]:
        population = self.data.get("population", {})
        people = population.get("people", {})
        households = population.get("households", {})
        world = self.data.get("world", {})
        buildings = world.get("buildings", {})
        records: List[EntityRecord] = []
        for household_id, household in households.items():
            member_ids = list(household.get("member_ids", []))
            members = [people.get(str(pid)) or people.get(pid) for pid in member_ids]
            member_names = [safe_text(member.get("full_name")) for member in members if member]
            building = buildings.get(str(household.get("home_building_id"))) or buildings.get(household.get("home_building_id"))
            details = [
                ("ID", str(household_id)),
                ("Members", safe_text(len(member_ids))),
                ("Home Building", safe_text(building.get("name") if building else "-")),
                ("Listing", safe_text(household.get("listing_id"))),
                ("Savings Pool", format_money(household.get("savings_pool"))),
                ("Monthly Costs", format_money(household.get("monthly_costs"))),
            ]
            sections = [
                ("Members", member_names or ["No linked members"]),
                ("Member IDs", [", ".join(str(pid) for pid in member_ids)] if member_ids else ["No member ids"]),
            ]
            records.append(
                EntityRecord(
                    category="households",
                    record_id=str(household_id),
                    title=f"Household {household_id}",
                    subtitle=f"{len(member_ids)} members | {format_money(household.get('monthly_costs'))} monthly",
                    search_text=" ".join([f"household {household_id}", safe_text(building.get("name") if building else ""), *member_names]).lower(),
                    sort_values={
                        "name": f"household {int(household_id):05d}",
                        "id": int(household_id),
                        "category": "households",
                        "members": len(member_ids),
                        "costs": float(household.get("monthly_costs", 0.0)),
                        "savings": float(household.get("savings_pool", 0.0)),
                    },
                    badges=[safe_text(len(member_ids)) + " members", format_money(household.get("monthly_costs"))],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_districts(self) -> List[EntityRecord]:
        world = self.data.get("world", {})
        districts = world.get("districts", {})
        records: List[EntityRecord] = []
        for district_id, district in districts.items():
            zoning_mix = district.get("zoning_mix", {})
            top_zone = max(zoning_mix, key=zoning_mix.get) if zoning_mix else "unknown"
            details = [
                ("ID", str(district_id)),
                ("Center", f"{ensure_tuple(district.get('center'))[0]}, {ensure_tuple(district.get('center'))[1]}"),
                ("Terrain", safe_text(district.get("dominant_terrain"))),
                ("Primary Zone", safe_text(top_zone)),
                ("Wealth", format_ratio(district.get("wealth"))),
                ("Crime", format_ratio(district.get("crime_heat"))),
                ("Transit", format_ratio(district.get("transit_score"))),
                ("Desirability", format_ratio(district.get("desirability"))),
                ("Capacity", safe_text(district.get("population_capacity"))),
                ("Average Rent", format_money(district.get("average_rent"))),
                ("Average Home Price", format_money(district.get("average_home_price"))),
                ("Buildings", safe_text(len(district.get("building_ids", [])))),
                ("Companies", safe_text(len(district.get("company_ids", [])))),
            ]
            sections = [
                ("Zoning Mix", [f"{name}: {float(value):.2f}" for name, value in sorted(zoning_mix.items())] or ["No zoning mix"]),
                ("Linked Buildings", [", ".join(str(item) for item in district.get("building_ids", [])[:20])] or ["No buildings"]),
                ("Linked Companies", [", ".join(str(item) for item in district.get("company_ids", [])[:20])] or ["No companies"]),
            ]
            records.append(
                EntityRecord(
                    category="districts",
                    record_id=str(district_id),
                    title=safe_text(district.get("name", f"District {district_id}")),
                    subtitle=f"{top_zone} | wealth {format_ratio(district.get('wealth'))} | crime {format_ratio(district.get('crime_heat'))}",
                    search_text=" ".join(
                        [
                            safe_text(district.get("name")),
                            safe_text(district.get("dominant_terrain")),
                            safe_text(top_zone),
                        ]
                    ).lower(),
                    sort_values={
                        "name": safe_text(district.get("name")).lower(),
                        "id": int(district_id),
                        "category": "districts",
                        "wealth": float(district.get("wealth", 0.0)),
                        "crime": float(district.get("crime_heat", 0.0)),
                        "desirability": float(district.get("desirability", 0.0)),
                    },
                    badges=[safe_text(top_zone), safe_text(district.get("dominant_terrain"))],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_buildings(self) -> List[EntityRecord]:
        world = self.data.get("world", {})
        buildings = world.get("buildings", {})
        districts = world.get("districts", {})
        companies = world.get("companies", {})
        records: List[EntityRecord] = []
        for building_id, building in buildings.items():
            district = districts.get(str(building.get("district_id"))) or districts.get(building.get("district_id"))
            company = companies.get(str(building.get("company_id"))) or companies.get(building.get("company_id"))
            details = [
                ("ID", str(building_id)),
                ("Type", safe_text(building.get("building_type"))),
                ("District", safe_text(district.get("name") if district else "-")),
                ("Tile", f"{ensure_tuple(building.get('tile'))[0]}, {ensure_tuple(building.get('tile'))[1]}"),
                ("Company", safe_text(company.get("name") if company else "-")),
                ("Capacity", safe_text(building.get("capacity"))),
                ("Quality", format_ratio(building.get("quality"))),
                ("Rent", format_money(building.get("rent"))),
                ("Price", format_money(building.get("purchase_price"))),
                ("Service", format_ratio(building.get("service_score"))),
                ("Job Slots", safe_text(building.get("job_slots"))),
                ("Level", safe_text(building.get("level"))),
                ("Maintenance", format_ratio(building.get("maintenance_backlog"))),
            ]
            sections = [
                (
                    "Open Hours",
                    [f"{building.get('open_hours', [8, 18])[0]:02d}:00-{building.get('open_hours', [8, 18])[1]:02d}:00"],
                ),
                ("Households", [", ".join(str(item) for item in building.get("household_ids", [])[:20])] or ["No households"]),
            ]
            records.append(
                EntityRecord(
                    category="buildings",
                    record_id=str(building_id),
                    title=safe_text(building.get("name", f"Building {building_id}")),
                    subtitle=f"{building.get('building_type')} | cap {building.get('capacity')} | rent {format_money(building.get('rent'))}",
                    search_text=" ".join(
                        [
                            safe_text(building.get("name")),
                            safe_text(building.get("building_type")),
                            safe_text(district.get("name") if district else ""),
                            safe_text(company.get("name") if company else ""),
                        ]
                    ).lower(),
                    sort_values={
                        "name": safe_text(building.get("name")).lower(),
                        "id": int(building_id),
                        "category": "buildings",
                        "rent": float(building.get("rent", 0.0)),
                        "capacity": float(building.get("capacity", 0.0)),
                        "quality": float(building.get("quality", 0.0)),
                    },
                    badges=[safe_text(building.get("building_type")), safe_text(district.get("name") if district else "")],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_transit(self) -> List[EntityRecord]:
        lines = self.data.get("world", {}).get("transit_lines", {})
        records: List[EntityRecord] = []
        for line_id, line in lines.items():
            details = [
                ("ID", str(line_id)),
                ("Type", safe_text(line.get("line_type"))),
                ("Stops", safe_text(len(line.get("stops", [])))),
                ("Speed", format_ratio(line.get("speed_multiplier"))),
                ("District Links", safe_text(len(line.get("district_ids", [])))),
            ]
            sections = [
                ("Stops", [f"{stop[0]}, {stop[1]}" for stop in line.get("stops", [])[:30]] or ["No stops"]),
                ("District IDs", [", ".join(str(item) for item in line.get("district_ids", [])[:20])] or ["No district ids"]),
            ]
            records.append(
                EntityRecord(
                    category="transit",
                    record_id=str(line_id),
                    title=safe_text(line.get("name", f"Transit Line {line_id}")),
                    subtitle=f"{line.get('line_type')} | {len(line.get('stops', []))} stops | speed {format_ratio(line.get('speed_multiplier'))}",
                    search_text=" ".join([safe_text(line.get("name")), safe_text(line.get("line_type"))]).lower(),
                    sort_values={
                        "name": safe_text(line.get("name")).lower(),
                        "id": int(line_id),
                        "category": "transit",
                        "stops": len(line.get("stops", [])),
                        "speed": float(line.get("speed_multiplier", 0.0)),
                    },
                    badges=[safe_text(line.get("line_type")), safe_text(len(line.get("stops", []))) + " stops"],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_stocks(self) -> List[EntityRecord]:
        stocks = self.data.get("systems", {}).get("stocks", {})
        world = self.data.get("world", {})
        companies = world.get("companies", {})
        records: List[EntityRecord] = []
        for symbol, stock in stocks.items():
            company = companies.get(str(stock.get("company_id"))) or companies.get(stock.get("company_id"))
            details = [
                ("Symbol", symbol),
                ("Company", safe_text(company.get("name") if company else f"Company {stock.get('company_id')}")),
                ("Price", format_money(stock.get("price"))),
                ("Change", format_ratio(stock.get("last_change"))),
                ("Shares", safe_text(stock.get("shares_outstanding"))),
                ("Volume", safe_text(stock.get("daily_volume"))),
                ("Volatility", format_ratio(stock.get("volatility"))),
            ]
            sections = [("Notes", [f"Linked company id: {safe_text(stock.get('company_id'))}"])]
            records.append(
                EntityRecord(
                    category="stocks",
                    record_id=symbol,
                    title=symbol,
                    subtitle=f"{safe_text(company.get('name') if company else 'Unlinked company')} | {format_money(stock.get('price'))}",
                    search_text=" ".join([symbol, safe_text(company.get("name") if company else "")]).lower(),
                    sort_values={
                        "name": symbol.lower(),
                        "id": symbol.lower(),
                        "category": "stocks",
                        "price": float(stock.get("price", 0.0)),
                        "change": float(stock.get("last_change", 0.0)),
                        "volume": float(stock.get("daily_volume", 0.0)),
                    },
                    badges=[format_money(stock.get("price")), f"d {format_ratio(stock.get('last_change'))}"],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_news(self) -> List[EntityRecord]:
        records: List[EntityRecord] = []
        news = list(self.data.get("news", []))
        for index, item in enumerate(reversed(news), start=1):
            details = [
                ("Slot", str(index)),
                ("Time", safe_text(item.get("timestamp"))),
                ("Category", safe_text(item.get("category"))),
                ("Importance", format_ratio(item.get("importance"))),
            ]
            sections = [("Detail", [safe_text(item.get("detail")) or "No detail"])]
            records.append(
                EntityRecord(
                    category="news",
                    record_id=str(index),
                    title=safe_text(item.get("headline", f"News {index}")),
                    subtitle=f"{item.get('category')} | {safe_text(item.get('timestamp'))}",
                    search_text=" ".join(
                        [safe_text(item.get("headline")), safe_text(item.get("detail")), safe_text(item.get("category"))]
                    ).lower(),
                    sort_values={
                        "name": safe_text(item.get("headline")).lower(),
                        "id": -index,
                        "category": "news",
                        "importance": float(item.get("importance", 0.0)),
                    },
                    badges=[safe_text(item.get("category")), f"imp {format_ratio(item.get('importance'))}"],
                    details=details,
                    sections=sections,
                )
            )
        return records

    def _build_timeline(self) -> List[EntityRecord]:
        records: List[EntityRecord] = []
        timeline = list(self.data.get("timeline", []))
        for index, item in enumerate(reversed(timeline), start=1):
            payload = item.get("payload", {})
            sections = [("Payload", [f"{key}: {preview_value(value)}" for key, value in payload.items()] or ["No payload"])]
            records.append(
                EntityRecord(
                    category="timeline",
                    record_id=str(index),
                    title=safe_text(item.get("title", f"Timeline Event {index}")),
                    subtitle=f"{item.get('event_type')} | {safe_text(item.get('timestamp'))}",
                    search_text=" ".join(
                        [safe_text(item.get("title")), safe_text(item.get("event_type")), safe_text(item.get("timestamp"))]
                    ).lower(),
                    sort_values={
                        "name": safe_text(item.get("title")).lower(),
                        "id": -index,
                        "category": "timeline",
                    },
                    badges=[safe_text(item.get("event_type"))],
                    details=[
                        ("Slot", str(index)),
                        ("Time", safe_text(item.get("timestamp"))),
                        ("Type", safe_text(item.get("event_type"))),
                    ],
                    sections=sections,
                )
            )
        return records


class SaveInspectorApp:
    def __init__(self, root: Path) -> None:
        pygame.init()
        pygame.display.set_caption("RLS Save Inspector")
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.root = root
        self.fonts = {
            "small": pygame.font.SysFont("segoeui,arial", 16),
            "body": pygame.font.SysFont("segoeui,arial", 20),
            "title": pygame.font.SysFont("segoeui,arial", 28, bold=True),
            "hero": pygame.font.SysFont("segoeui,arial", 38, bold=True),
        }
        self.running = True
        self.mode = "loader"
        self.loader_items: List[SavePreview] = []
        self.loader_selection = 0
        self.loader_scroll = 0
        self.loader_message = "Scanning for save files..."
        self.loader_busy = False
        self.loader_query = ""
        self.loader_input_active = False
        self.index: Optional[SaveIndex] = None
        self.category_tabs = ["all", "people", "companies", "households", "districts", "buildings", "transit", "stocks", "news", "timeline"]
        self.selected_category = "all"
        self.search_text = ""
        self.sort_key = "name"
        self.result_selection = 0
        self.result_scroll = 0
        self.status_message = "L load another save | / focus search | Tab categories | F2 sort"
        self._click_regions: List[Tuple[pygame.Rect, str, Any]] = []
        self.refresh_loader()

    def refresh_loader(self) -> None:
        self.loader_busy = True
        self.loader_message = "Scanning save files..."
        self.loader_items = self.scan_save_files()
        self.loader_selection = 0
        self.loader_scroll = 0
        self.loader_busy = False
        if not self.loader_items:
            self.loader_message = "No .pkl/.save files found. Type a path below or copy one into this folder."
        else:
            self.loader_message = f"Found {len(self.loader_items)} save files."

    def scan_save_files(self) -> List[SavePreview]:
        candidates: List[Path] = []
        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SAVE_EXTENSIONS:
                candidates.append(path)
        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        previews: List[SavePreview] = []
        for path in candidates[:80]:
            try:
                summary = build_save_summary(load_save_data(path))
                previews.append(SavePreview(path=path, status="ok", summary=summary))
            except Exception as exc:
                previews.append(SavePreview(path=path, status="error", error=str(exc)))
        return previews

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode((max(1100, event.w), max(720, event.h)), pygame.RESIZABLE)
        elif event.type == pygame.KEYDOWN:
            if self.mode == "loader":
                self.handle_loader_key(event)
            else:
                self.handle_browser_key(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.handle_mouse(event.pos, event.button)
        elif event.type == pygame.MOUSEWHEEL:
            if self.mode == "loader":
                self.loader_scroll = max(0, self.loader_scroll - event.y)
            else:
                self.result_scroll = max(0, self.result_scroll - event.y)

    def handle_loader_key(self, event: pygame.event.Event) -> None:
        if self.loader_input_active:
            if event.key == pygame.K_RETURN:
                self.load_path(Path(self.loader_query.strip()))
                self.loader_input_active = False
            elif event.key == pygame.K_ESCAPE:
                self.loader_input_active = False
            elif event.key == pygame.K_BACKSPACE:
                self.loader_query = self.loader_query[:-1]
            else:
                if event.unicode and event.unicode.isprintable():
                    self.loader_query += event.unicode
            return
        if event.key in (pygame.K_DOWN, pygame.K_j):
            self.loader_selection = min(len(self.loader_items) - 1, self.loader_selection + 1) if self.loader_items else 0
        elif event.key in (pygame.K_UP, pygame.K_k):
            self.loader_selection = max(0, self.loader_selection - 1)
        elif event.key == pygame.K_RETURN and self.loader_items:
            self.load_preview(self.loader_items[self.loader_selection])
        elif event.key == pygame.K_r:
            self.refresh_loader()
        elif event.key == pygame.K_SLASH:
            self.loader_input_active = True
        elif event.key == pygame.K_ESCAPE:
            self.running = False

    def handle_browser_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE and self.search_text:
            self.search_text = ""
            self.result_selection = 0
            self.result_scroll = 0
            return
        if event.key == pygame.K_l:
            self.mode = "loader"
            self.loader_input_active = False
            self.status_message = "Pick another save."
            return
        if event.key == pygame.K_F2:
            options = self.current_sort_options()
            keys = [item[0] for item in options]
            if self.sort_key not in keys:
                self.sort_key = keys[0]
            else:
                self.sort_key = keys[(keys.index(self.sort_key) + 1) % len(keys)]
            self.result_selection = 0
            self.result_scroll = 0
            return
        if event.key == pygame.K_TAB:
            index = (self.category_tabs.index(self.selected_category) + 1) % len(self.category_tabs)
            self.select_category(self.category_tabs[index])
            return
        if event.key in (pygame.K_DOWN, pygame.K_j):
            self.result_selection = min(max(0, len(self.filtered_records()) - 1), self.result_selection + 1)
        elif event.key in (pygame.K_UP, pygame.K_k):
            self.result_selection = max(0, self.result_selection - 1)
        elif event.key == pygame.K_PAGEUP:
            self.result_selection = max(0, self.result_selection - 10)
        elif event.key == pygame.K_PAGEDOWN:
            self.result_selection = min(max(0, len(self.filtered_records()) - 1), self.result_selection + 10)
        elif event.key == pygame.K_BACKSPACE:
            self.search_text = self.search_text[:-1]
            self.result_selection = 0
            self.result_scroll = 0
        else:
            if event.unicode and event.unicode.isprintable():
                self.search_text += event.unicode
                self.result_selection = 0
                self.result_scroll = 0

    def handle_mouse(self, pos: Tuple[int, int], button: int) -> None:
        if button not in (1, 4, 5):
            return
        if button in (4, 5):
            delta = -1 if button == 4 else 1
            if self.mode == "loader":
                self.loader_scroll = max(0, self.loader_scroll + delta)
            else:
                self.result_scroll = max(0, self.result_scroll + delta)
            return
        for rect, action, payload in self._click_regions:
            if rect.collidepoint(pos):
                if action == "load_preview":
                    self.load_preview(payload)
                elif action == "loader_input":
                    self.loader_input_active = True
                elif action == "select_category":
                    self.select_category(payload)
                elif action == "select_sort":
                    self.sort_key = payload
                    self.result_selection = 0
                    self.result_scroll = 0
                elif action == "select_result":
                    self.result_selection = payload
                elif action == "open_loader":
                    self.mode = "loader"
                break

    def load_preview(self, preview: SavePreview) -> None:
        if preview.status != "ok":
            self.status_message = preview.error or "This file could not be loaded."
            return
        self.load_path(preview.path)

    def load_path(self, path: Path) -> None:
        try:
            data = load_save_data(path)
            self.index = SaveIndex(path, data)
            self.mode = "browser"
            self.selected_category = "all"
            self.sort_key = "name"
            self.result_selection = 0
            self.result_scroll = 0
            self.search_text = ""
            self.status_message = f"Loaded {path.name}. Search by name, sector, job, district, symbol, headline, or id."
        except Exception as exc:
            self.status_message = f"Load failed: {exc}"

    def filtered_records(self) -> List[EntityRecord]:
        if not self.index:
            return []
        records = list(self.index.records_for(self.selected_category))
        if self.search_text.strip():
            tokens = [token.lower() for token in self.search_text.split() if token.strip()]
            records = [record for record in records if all(token in record.search_text or token in record.record_id.lower() for token in tokens)]
        reverse = self.sort_key not in {"name", "id", "category"}
        records.sort(key=lambda record: record.sort_values.get(self.sort_key, record.sort_values.get("name")), reverse=reverse)
        return records

    def current_sort_options(self) -> List[Tuple[str, str]]:
        if not self.index:
            return [("name", "Name")]
        return self.index.sort_options.get(self.selected_category, self.index.sort_options["all"])

    def select_category(self, category: str) -> None:
        self.selected_category = category
        options = [item[0] for item in self.current_sort_options()]
        if self.sort_key not in options:
            self.sort_key = options[0]
        self.result_selection = 0
        self.result_scroll = 0

    def selected_record(self) -> Optional[EntityRecord]:
        records = self.filtered_records()
        if not records:
            return None
        self.result_selection = clamp(self.result_selection, 0, len(records) - 1)
        return records[int(self.result_selection)]

    def draw(self) -> None:
        self.screen.fill(UI_BG)
        self._click_regions = []
        if self.mode == "loader":
            self.draw_loader()
        else:
            self.draw_browser()

    def draw_loader(self) -> None:
        width, height = self.screen.get_size()
        self.draw_gradient((0, 0, width, height), (11, 19, 30), (24, 38, 54))
        outer = pygame.Rect(36, 36, width - 72, height - 72)
        self.draw_panel(outer, radius=24)
        self.draw_text("RLS Save Inspector", self.fonts["hero"], TEXT, (outer.x + 28, outer.y + 24))
        self.draw_text("Choose a save file or type a path. Loader previews counts and world state before opening.", self.fonts["body"], TEXT_MUTED, (outer.x + 30, outer.y + 74))

        left = pygame.Rect(outer.x + 24, outer.y + 120, int(outer.w * 0.54), outer.h - 210)
        right = pygame.Rect(left.right + 18, left.y, outer.right - left.right - 42, left.h)
        input_rect = pygame.Rect(outer.x + 24, outer.bottom - 66, outer.w - 48, 42)

        self.draw_panel(left, fill=PANEL_ALT)
        self.draw_panel(right, fill=PANEL_ALT)
        self.draw_panel(input_rect, fill=(18, 24, 34), radius=12)
        self._click_regions.append((input_rect, "loader_input", None))

        self.draw_text("Save Files", self.fonts["title"], TEXT, (left.x + 18, left.y + 14))
        self.draw_text(self.loader_message, self.fonts["small"], TEXT_MUTED, (left.x + 20, left.y + 50))
        self.draw_text("Path input", self.fonts["small"], TEXT_FAINT, (input_rect.x + 14, input_rect.y - 18))
        path_label = self.loader_query if self.loader_input_active or self.loader_query else "Press / and type a full or relative path, then Enter"
        self.draw_text(path_label, self.fonts["body"], TEXT if self.loader_query else TEXT_FAINT, (input_rect.x + 14, input_rect.y + 10))

        row_h = 74
        visible_rows = max(1, (left.h - 84) // row_h)
        max_scroll = max(0, len(self.loader_items) - visible_rows)
        self.loader_scroll = int(clamp(self.loader_scroll, 0, max_scroll))
        if self.loader_selection < self.loader_scroll:
            self.loader_scroll = self.loader_selection
        if self.loader_selection >= self.loader_scroll + visible_rows:
            self.loader_scroll = self.loader_selection - visible_rows + 1

        for draw_index in range(visible_rows):
            item_index = self.loader_scroll + draw_index
            if item_index >= len(self.loader_items):
                break
            preview = self.loader_items[item_index]
            card = pygame.Rect(left.x + 14, left.y + 80 + draw_index * row_h, left.w - 28, row_h - 10)
            color = CARD_SELECTED if item_index == self.loader_selection else CARD_BG
            self.draw_panel(card, fill=color, radius=14)
            self._click_regions.append((card, "load_preview", preview))
            self.draw_text(preview.path.name, self.fonts["body"], TEXT, (card.x + 14, card.y + 10))
            sub = str(preview.path.relative_to(self.root)) if preview.path.is_relative_to(self.root) else str(preview.path)
            self.draw_text(sub, self.fonts["small"], TEXT_MUTED, (card.x + 14, card.y + 36))
            if preview.status == "ok" and preview.summary:
                blurb = f"{preview.summary['people']} people | {preview.summary['companies']} companies | {preview.summary['date']}"
                self.draw_text(blurb, self.fonts["small"], ACCENT, (card.right - 330, card.y + 10))
            else:
                self.draw_text("Unreadable", self.fonts["small"], BAD, (card.right - 110, card.y + 10))

        selected = self.loader_items[self.loader_selection] if self.loader_items else None
        self.draw_text("Preview", self.fonts["title"], TEXT, (right.x + 18, right.y + 14))
        if selected is None:
            self.draw_text("No save selected.", self.fonts["body"], TEXT_MUTED, (right.x + 18, right.y + 70))
        elif selected.status != "ok" or not selected.summary:
            self.draw_text(selected.path.name, self.fonts["body"], TEXT, (right.x + 18, right.y + 70))
            self.draw_text(selected.error or "This file could not be decoded.", self.fonts["body"], BAD, (right.x + 18, right.y + 110))
        else:
            summary = selected.summary
            self.draw_text(selected.path.name, self.fonts["title"], TEXT, (right.x + 18, right.y + 64))
            meta = [
                f"Schema {summary['schema']}",
                f"Seed {summary['seed']}",
                f"World {summary['world_seed']}",
                summary["date"],
                summary["weather"],
            ]
            y = right.y + 110
            for line in meta:
                self.draw_text(line, self.fonts["body"], TEXT_MUTED, (right.x + 18, y))
                y += 32
            stats = [
                ("People", summary["people"]),
                ("Households", summary["households"]),
                ("Companies", summary["companies"]),
                ("Districts", summary["districts"]),
                ("Buildings", summary["buildings"]),
                ("Transit", summary["transit"]),
                ("Stocks", summary["stocks"]),
                ("News", summary["news"]),
                ("Timeline", summary["timeline"]),
            ]
            cols = 2
            card_w = (right.w - 54) // cols
            for idx, (label, value) in enumerate(stats):
                col = idx % cols
                row = idx // cols
                rect = pygame.Rect(right.x + 18 + col * (card_w + 18), right.y + 280 + row * 86, card_w, 70)
                self.draw_panel(rect, fill=CARD_BG, radius=14)
                self.draw_text(label, self.fonts["small"], TEXT_MUTED, (rect.x + 12, rect.y + 10))
                self.draw_text(str(value), self.fonts["title"], TEXT, (rect.x + 12, rect.y + 28))

        help_text = "Controls: Up/Down select  Enter load  R refresh  / path input  Esc quit"
        self.draw_text(help_text, self.fonts["small"], TEXT_FAINT, (outer.x + 28, outer.bottom - 92))

    def draw_browser(self) -> None:
        if not self.index:
            return
        width, height = self.screen.get_size()
        self.draw_gradient((0, 0, width, height), (10, 17, 24), (23, 30, 43))
        top = pygame.Rect(22, 18, width - 44, 110)
        left = pygame.Rect(22, 144, 520, height - 166)
        right = pygame.Rect(left.right + 18, 144, width - left.right - 40, height - 166)
        self.draw_panel(top, radius=24)
        self.draw_panel(left, radius=24)
        self.draw_panel(right, radius=24)

        summary = self.index.summary
        self.draw_text(self.index.path.name, self.fonts["hero"], TEXT, (top.x + 22, top.y + 14))
        subtitle = f"{summary['date']} | {summary['weather']} | {summary['people']} people | {summary['companies']} companies | schema {summary['schema']}"
        self.draw_text(subtitle, self.fonts["body"], TEXT_MUTED, (top.x + 24, top.y + 62))

        open_button = pygame.Rect(top.right - 188, top.y + 20, 160, 44)
        self.draw_panel(open_button, fill=ACCENT_DIM, radius=14)
        self.draw_text("Load Another", self.fonts["body"], TEXT, (open_button.x + 20, open_button.y + 10))
        self._click_regions.append((open_button, "open_loader", None))

        search_rect = pygame.Rect(left.x + 18, left.y + 18, left.w - 36, 42)
        self.draw_panel(search_rect, fill=(18, 24, 34), radius=12)
        query = self.search_text if self.search_text else "Type to search names, ids, jobs, sectors, districts, symbols, headlines..."
        self.draw_text(query, self.fonts["body"], TEXT if self.search_text else TEXT_FAINT, (search_rect.x + 12, search_rect.y + 10))

        tab_x = left.x + 18
        tab_y = left.y + 74
        for category in self.category_tabs:
            label = category.title()
            tab_w = max(72, self.fonts["small"].size(label)[0] + 28)
            rect = pygame.Rect(tab_x, tab_y, tab_w, 30)
            fill = ACCENT_DIM if category == self.selected_category else PANEL_SOFT
            self.draw_panel(rect, fill=fill, radius=11)
            self.draw_text(label, self.fonts["small"], TEXT, (rect.x + 12, rect.y + 7))
            self._click_regions.append((rect, "select_category", category))
            tab_x += tab_w + 8
            if tab_x > left.right - 120:
                tab_x = left.x + 18
                tab_y += 38

        sort_y = tab_y + 44
        self.draw_text("Sort", self.fonts["small"], TEXT_FAINT, (left.x + 18, sort_y))
        sort_x = left.x + 60
        for key, label in self.current_sort_options():
            rect = pygame.Rect(sort_x, sort_y - 6, max(72, self.fonts["small"].size(label)[0] + 24), 28)
            fill = ACCENT_DIM if key == self.sort_key else PANEL_SOFT
            self.draw_panel(rect, fill=fill, radius=10)
            self.draw_text(label, self.fonts["small"], TEXT, (rect.x + 10, rect.y + 6))
            self._click_regions.append((rect, "select_sort", key))
            sort_x += rect.w + 8

        records = self.filtered_records()
        count_label = f"{len(records)} matches in {self.selected_category}"
        self.draw_text(count_label, self.fonts["small"], TEXT_MUTED, (left.x + 18, sort_y + 34))

        list_top = sort_y + 62
        row_h = 82
        visible_rows = max(1, (left.bottom - list_top - 16) // row_h)
        max_scroll = max(0, len(records) - visible_rows)
        self.result_scroll = int(clamp(self.result_scroll, 0, max_scroll))
        if self.result_selection < self.result_scroll:
            self.result_scroll = self.result_selection
        if self.result_selection >= self.result_scroll + visible_rows:
            self.result_scroll = self.result_selection - visible_rows + 1

        for draw_index in range(visible_rows):
            item_index = self.result_scroll + draw_index
            if item_index >= len(records):
                break
            record = records[item_index]
            rect = pygame.Rect(left.x + 16, list_top + draw_index * row_h, left.w - 32, row_h - 10)
            fill = CARD_SELECTED if item_index == self.result_selection else CARD_BG
            self.draw_panel(rect, fill=fill, radius=16)
            self._click_regions.append((rect, "select_result", item_index))
            self.draw_text(record.title, self.fonts["body"], TEXT, (rect.x + 14, rect.y + 10))
            self.draw_text(record.subtitle, self.fonts["small"], TEXT_MUTED, (rect.x + 14, rect.y + 38))
            badge_x = rect.x + 14
            badge_y = rect.y + 56
            for badge in record.badges[:3]:
                badge_text = preview_value(badge, 18)
                badge_w = self.fonts["small"].size(badge_text)[0] + 16
                badge_rect = pygame.Rect(badge_x, badge_y, badge_w, 20)
                self.draw_panel(badge_rect, fill=(32, 66, 92), radius=8)
                self.draw_text(badge_text, self.fonts["small"], TEXT, (badge_rect.x + 8, badge_rect.y + 3))
                badge_x += badge_w + 8

        record = self.selected_record()
        if record is None:
            self.draw_text("No matching records.", self.fonts["title"], TEXT, (right.x + 24, right.y + 24))
            return

        self.draw_text(record.title, self.fonts["hero"], TEXT, (right.x + 24, right.y + 24))
        self.draw_text(f"{record.category.title()} #{record.record_id}", self.fonts["body"], ACCENT, (right.x + 26, right.y + 70))
        self.draw_text(record.subtitle, self.fonts["body"], TEXT_MUTED, (right.x + 26, right.y + 102))

        column_a = pygame.Rect(right.x + 24, right.y + 144, (right.w - 72) // 2, right.h - 170)
        column_b = pygame.Rect(column_a.right + 24, column_a.y, column_a.w, column_a.h)

        self.draw_text("Snapshot", self.fonts["title"], TEXT, (column_a.x, column_a.y))
        y = column_a.y + 42
        for label, value in record.details:
            self.draw_text(label, self.fonts["small"], TEXT_FAINT, (column_a.x, y))
            self.draw_text(value, self.fonts["body"], TEXT, (column_a.x + 150, y - 4))
            y += 28
            if y > column_a.bottom - 40:
                break

        section_y = column_b.y
        for title, lines in record.sections:
            self.draw_text(title, self.fonts["title"], TEXT, (column_b.x, section_y))
            section_y += 34
            for line in lines[:8]:
                wrapped = self.wrap_text(line, self.fonts["small"], column_b.w)
                for segment in wrapped[:2]:
                    self.draw_text(segment, self.fonts["small"], TEXT_MUTED, (column_b.x, section_y))
                    section_y += 20
                if section_y > column_b.bottom - 40:
                    break
            section_y += 16
            if section_y > column_b.bottom - 40:
                break

        footer = pygame.Rect(22, height - 48, width - 44, 28)
        self.draw_text(self.status_message, self.fonts["small"], TEXT_FAINT, (footer.x + 8, footer.y))

    def draw_panel(self, rect: pygame.Rect, fill: Tuple[int, int, int] = PANEL_BG, radius: int = 18) -> None:
        shadow_rect = rect.move(0, 4)
        pygame.draw.rect(self.screen, SHADOW, shadow_rect, border_radius=radius)
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen, (70, 82, 102), rect, width=1, border_radius=radius)

    def draw_text(self, text: str, font: pygame.font.Font, color: Tuple[int, int, int], pos: Tuple[int, int]) -> None:
        surface = font.render(text, True, color)
        self.screen.blit(surface, pos)

    def draw_gradient(self, rect_like: Tuple[int, int, int, int], top_color: Tuple[int, int, int], bottom_color: Tuple[int, int, int]) -> None:
        rect = pygame.Rect(rect_like)
        target = pygame.Surface((rect.w, rect.h))
        for y in range(rect.h):
            blend = y / max(1, rect.h - 1)
            color = (
                int(top_color[0] * (1 - blend) + bottom_color[0] * blend),
                int(top_color[1] * (1 - blend) + bottom_color[1] * blend),
                int(top_color[2] * (1 - blend) + bottom_color[2] * blend),
            )
            pygame.draw.line(target, color, (0, y), (rect.w, y))
        self.screen.blit(target, rect.topleft)

    def wrap_text(self, text: str, font: pygame.font.Font, width: int) -> List[str]:
        words = text.split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            trial = current + " " + word
            if font.size(trial)[0] <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines


def main() -> None:
    app = SaveInspectorApp(Path.cwd())
    if len(sys.argv) > 1:
        app.load_path(Path(sys.argv[1]))
    app.run()


if __name__ == "__main__":
    main()
