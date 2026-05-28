"""
entities.py

This module models people as long-running autonomous agents.
No citizen is simulation-special; the UI can inspect any person,
but the world logic treats everyone uniformly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from world import Building, HousingListing, JobPosting, WorldMap, clamp, round_for_save


SKILL_KEYS = [
    "software",
    "service",
    "logistics",
    "engineering",
    "medicine",
    "teaching",
    "transport",
    "finance",
    "communication",
    "law",
    "fitness",
    "craft",
]

PERSONALITY_AXES = [
    "discipline",
    "sociability",
    "risk_tolerance",
    "empathy",
    "ambition",
    "impulsiveness",
    "resilience",
]

PERSON_SAVE_FLOAT_DIGITS = 4
WORK_TRAIT_KEYS = [
    "work_ethic",
    "reliability",
    "teamwork",
    "adaptability",
    "learning_drive",
]


FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Avery", "Casey", "Cameron", "Parker", "Riley", "Quinn",
    "Elliot", "Reese", "Devon", "Hayden", "Rowan", "Skyler", "Drew", "Sam", "Jamie", "Logan",
]

LAST_NAMES = [
    "Patel", "Reed", "Carter", "Shaw", "Rivera", "Bennett", "Morris", "Nguyen", "Coleman", "Santos",
    "Brooks", "Foster", "Hayes", "Ward", "Bailey", "Kim", "Murphy", "Price", "Diaz", "Powell",
]


@dataclass
class GeneticsProfile:
    """Inheritable tendencies used to make citizens feel varied."""

    vitality: float
    cognition: float
    stature: float
    metabolism: float
    stress_sensitivity: float
    addiction_risk: float
    longevity: float

    @classmethod
    def random(cls, rng: random.Random) -> "GeneticsProfile":
        return cls(
            vitality=rng.uniform(0.2, 1.0),
            cognition=rng.uniform(0.2, 1.0),
            stature=rng.uniform(0.2, 1.0),
            metabolism=rng.uniform(0.2, 1.0),
            stress_sensitivity=rng.uniform(0.2, 1.0),
            addiction_risk=rng.uniform(0.0, 1.0),
            longevity=rng.uniform(0.3, 1.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class PersonalityProfile:
    """Stable social/behavioral tendencies."""

    discipline: float
    sociability: float
    risk_tolerance: float
    empathy: float
    ambition: float
    impulsiveness: float
    resilience: float

    @classmethod
    def random(cls, rng: random.Random) -> "PersonalityProfile":
        return cls(
            discipline=rng.uniform(0.0, 1.0),
            sociability=rng.uniform(0.0, 1.0),
            risk_tolerance=rng.uniform(0.0, 1.0),
            empathy=rng.uniform(0.0, 1.0),
            ambition=rng.uniform(0.0, 1.0),
            impulsiveness=rng.uniform(0.0, 1.0),
            resilience=rng.uniform(0.0, 1.0),
        )

    def axis_dict(self) -> Dict[str, float]:
        return self.__dict__.copy()


@dataclass
class MemoryRecord:
    timestamp: str
    category: str
    headline: str
    impact: float
    location: Optional[Tuple[int, int]] = None
    related_people: List[int] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class Relationship:
    person_id: int
    affinity: float = 0.0
    trust: float = 0.0
    romance: float = 0.0
    respect: float = 0.0
    familiarity: float = 0.0
    rivalry: float = 0.0
    gossip_knowledge: float = 0.0
    last_interaction_day: int = 0
    interaction_count: int = 0

    def closeness(self) -> float:
        return max(0.0, self.affinity * 0.35 + self.trust * 0.3 + self.familiarity * 0.2 + self.respect * 0.15)


@dataclass
class ScheduleBlock:
    start_hour: int
    end_hour: int
    activity: str
    target: Optional[Tuple[int, int]] = None
    building_id: Optional[int] = None
    intensity: float = 0.5


@dataclass
class Household:
    household_id: int
    member_ids: List[int]
    home_building_id: int
    listing_id: int
    savings_pool: float = 0.0
    monthly_costs: float = 0.0


class Person:
    """
    Full citizen simulation entity.

    The code is deliberately explicit instead of compact because many
    systems need hooks into a person's state: finances, education,
    crime, law, jobs, relationships, stress, and schedules.
    """

    def __init__(
        self,
        person_id: int,
        rng: random.Random,
        world: WorldMap,
        age: Optional[int] = None,
    ) -> None:
        self.person_id = person_id
        self.rng = rng
        self.first_name = rng.choice(FIRST_NAMES)
        self.last_name = rng.choice(LAST_NAMES)
        self.full_name = f"{self.first_name} {self.last_name}"
        self.age = age if age is not None else rng.randint(0, 72)
        self.gender = rng.choice(["woman", "man", "nonbinary"])
        self.genetics = GeneticsProfile.random(rng)
        self.personality = PersonalityProfile.random(rng)
        self.health = clamp(0.5 + self.genetics.vitality * 0.45 + rng.uniform(-0.1, 0.1), 0.0, 1.0)
        self.energy = clamp(0.6 + rng.uniform(-0.15, 0.15), 0.0, 1.0)
        self.stress = clamp(0.25 + (1.0 - self.personality.resilience) * 0.2 + rng.uniform(-0.1, 0.1), 0.0, 1.0)
        self.happiness = clamp(0.45 + rng.uniform(-0.15, 0.2), 0.0, 1.0)
        self.motivation = clamp(0.45 + self.personality.ambition * 0.3 + rng.uniform(-0.1, 0.15), 0.0, 1.0)
        self.reputation_public = clamp(0.5 + rng.uniform(-0.15, 0.15), 0.0, 1.0)
        self.hidden_karma = clamp(0.5 + rng.uniform(-0.2, 0.2), 0.0, 1.0)
        self.crime_tendency = clamp(
            self.personality.risk_tolerance * 0.35 + self.personality.impulsiveness * 0.35 + (1.0 - self.personality.empathy) * 0.3,
            0.0,
            1.0,
        )
        self.skills: Dict[str, float] = {key: clamp(rng.uniform(0.0, 0.45), 0.0, 1.0) for key in SKILL_KEYS}
        self.skill_practice: Dict[str, float] = {key: 0.0 for key in SKILL_KEYS}
        self.learning_focus_skill: Optional[str] = None
        self.education_level = rng.choice(["none", "school", "college", "certificate"])
        self.certifications: List[str] = []
        self.memories: List[MemoryRecord] = []
        self.relationships: Dict[int, Relationship] = {}
        self.family_ids: List[int] = []
        self.parent_ids: List[int] = []
        self.children_ids: List[int] = []
        self.spouse_id: Optional[int] = None
        self.relation_roles: Dict[int, str] = {}
        self.household_id: Optional[int] = None
        self.home_building_id: Optional[int] = None
        self.job_company_id: Optional[int] = None
        self.job_title: Optional[str] = None
        self.job_skill: Optional[str] = None
        self.salary: float = 0.0
        self.job_shift: Tuple[int, int] = (9, 17)
        self.student_status: Optional[str] = None
        self.current_enrollment_building: Optional[int] = None
        self.schedule: Dict[int, ScheduleBlock] = {}
        self.social_circle: List[int] = []
        self.work_traits: Dict[str, float] = {key: clamp(rng.uniform(0.2, 1.0), 0.0, 1.0) for key in WORK_TRAIT_KEYS}
        self.job_performance = clamp(0.45 + rng.uniform(-0.12, 0.12), 0.0, 1.0)
        self.job_satisfaction = clamp(0.5 + rng.uniform(-0.18, 0.18), 0.0, 1.0)
        self.days_unproductive = 0
        self.vehicle = rng.choice(["none", "bike", "car", "bus_pass"])
        self.cash = round(rng.uniform(200.0, 6000.0), 2)
        self.bank_balance = round(rng.uniform(0.0, 20_000.0), 2)
        self.debt = round(rng.uniform(0.0, 8_000.0), 2)
        self.assets = round(rng.uniform(0.0, 15_000.0), 2)
        self.investment_accounts: Dict[str, float] = {}
        self.arrest_record: List[str] = []
        self.location = self._spawn_location(world)
        self.destination = self.location
        self.path: List[Tuple[int, int]] = []
        self.hours_since_rest = 0
        self.last_paid_day = 0
        self.last_major_event_day = 0
        self.gossip_log: List[str] = []
        self.life_stage = self._derive_life_stage()
        self.add_memory("origin", f"Born into the procedural city at age {self.age}.", 0.15)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    def _spawn_location(self, world: WorldMap) -> Tuple[int, int]:
        tile = world.random_walkable_tile()
        return (tile.x, tile.y)

    def _derive_life_stage(self) -> str:
        if self.age < 13:
            return "child"
        if self.age < 18:
            return "teen"
        if self.age < 22:
            return "young_adult"
        if self.age < 40:
            return "adult"
        if self.age < 60:
            return "midlife"
        return "senior"

    # ------------------------------------------------------------------
    # Narrative helpers
    # ------------------------------------------------------------------
    def add_memory(
        self,
        category: str,
        headline: str,
        impact: float,
        timestamp: str = "",
        location: Optional[Tuple[int, int]] = None,
        related_people: Optional[List[int]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        self.memories.append(
            MemoryRecord(
                timestamp=timestamp,
                category=category,
                headline=headline,
                impact=impact,
                location=location,
                related_people=related_people or [],
                tags=tags or [],
            )
        )
        if len(self.memories) > 180:
            self.memories = self.memories[-180:]
        self.happiness = clamp(self.happiness + impact * 0.05, 0.0, 1.0)
        self.stress = clamp(self.stress - impact * 0.03, 0.0, 1.0)

    def relationship_with(self, other_id: int) -> Relationship:
        if other_id not in self.relationships:
            self.relationships[other_id] = Relationship(person_id=other_id)
        return self.relationships[other_id]

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def build_daily_schedule(self, world: WorldMap, day_index: int) -> None:
        self.schedule = {}
        for hour in range(24):
            self.schedule[hour] = self._plan_hour(world, day_index, hour)

    def _plan_hour(self, world: WorldMap, day_index: int, hour: int) -> ScheduleBlock:
        home_tile = self.home_tile(world)
        work_tile = self.work_tile(world)
        school_tile = self.school_tile(world)

        if self._should_sleep(hour):
            return ScheduleBlock(hour, hour + 1, "sleep", target=home_tile, building_id=self.home_building_id, intensity=0.2)

        obligation = self._mandatory_activity_block(world, hour, home_tile, work_tile, school_tile)
        if obligation is not None:
            return obligation

        activity = self._choose_self_directed_activity(hour)
        target = home_tile
        building_id = self.home_building_id
        if activity == "socialize":
            target = self._choose_social_target(world)
        elif activity == "exercise":
            target = self._choose_park_target(world)
        elif activity == "errand":
            target = self._choose_commercial_target(world)
        elif activity == "clinic":
            target = self._choose_service_target(world, "hospital")
        elif activity == "study_self" and school_tile and self.rng.random() < 0.35:
            target = school_tile
            building_id = self.current_enrollment_building
        return ScheduleBlock(hour, hour + 1, activity, target=target, building_id=building_id, intensity=0.45)

    def _should_sleep(self, hour: int) -> bool:
        if hour >= 23 or hour <= 5:
            return True
        if self.energy < 0.14:
            return True
        if self.hours_since_rest >= 20 and self.energy < 0.35:
            return True
        if self.stress > 0.88 and self.energy < 0.45:
            return True
        return False

    def _mandatory_activity_block(
        self,
        world: WorldMap,
        hour: int,
        home_tile: Tuple[int, int],
        work_tile: Optional[Tuple[int, int]],
        school_tile: Optional[Tuple[int, int]],
    ) -> Optional[ScheduleBlock]:
        if self.student_status and school_tile and 8 <= hour < 14 and self.energy > 0.08:
            activity = "commute_school" if self.location != school_tile else "study"
            return ScheduleBlock(hour, hour + 1, activity, target=school_tile, building_id=self.current_enrollment_building, intensity=0.8)

        if self.job_company_id and work_tile and self._hour_in_range(hour, *self.job_shift):
            if self.health < 0.16 or (self.energy < 0.08 and self.stress > 0.92):
                return ScheduleBlock(hour, hour + 1, "rest", target=home_tile, building_id=self.home_building_id, intensity=0.5)
            activity = "commute_work" if self.location != work_tile else "work"
            return ScheduleBlock(hour, hour + 1, activity, target=work_tile, intensity=0.85)

        if self.job_company_id and work_tile:
            shift_start, shift_end = self.job_shift
            if self._hour_before_shift(hour, shift_start) and self.energy > 0.22:
                return ScheduleBlock(hour, hour + 1, "commute_work", target=work_tile, intensity=0.55)
            if self._hour_after_shift(hour, shift_end) and self.location != home_tile:
                return ScheduleBlock(hour, hour + 1, "commute_home", target=home_tile, building_id=self.home_building_id, intensity=0.45)

        if self.job_company_id is None and self.age >= 18 and 9 <= hour < 12 and self.motivation > 0.2:
            return ScheduleBlock(hour, hour + 1, "job_search", target=home_tile, building_id=self.home_building_id, intensity=0.55)

        return None

    def _choose_self_directed_activity(self, hour: int) -> str:
        if self.health < 0.3 and self.cash >= 40.0 and 8 <= hour <= 20 and self.rng.random() < 0.6:
            return "clinic"
        if self.stress > 0.78:
            return "rest" if self.personality.sociability < 0.55 else self.rng.choice(["rest", "socialize"])
        if self.energy < 0.28:
            return "rest"
        if self.personality.sociability > 0.62 and 17 <= hour <= 21 and self.rng.random() < 0.45:
            return "socialize"
        if self.motivation > 0.68 and self.rng.random() < 0.28:
            return "study_self"
        if self.health < 0.55 and self.rng.random() < 0.2:
            return "exercise"
        if self.cash > 120.0 and 10 <= hour <= 19 and self.rng.random() < 0.18:
            return "errand"
        if self.personality.sociability > 0.5 and self.rng.random() < 0.15:
            return "socialize"
        if self.rng.random() < 0.12:
            return "exercise"
        return "rest"

    def _hour_in_range(self, hour: int, start: int, end: int) -> bool:
        if start == end:
            return False
        if end < start:
            return hour >= start or hour < end
        return start <= hour < end

    def _hour_before_shift(self, hour: int, start: int) -> bool:
        return hour == (start - 1) % 24

    def _hour_after_shift(self, hour: int, end: int) -> bool:
        return hour == end % 24

    def _choose_social_target(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        parks = world.building_by_type("park_facility")
        stations = world.building_by_type("station")
        shops = world.building_by_type("shop")
        options = parks + stations + shops
        if not options:
            return self.home_tile(world)
        building = self.rng.choice(options)
        return building.tile

    def _choose_park_target(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        candidates = [tile for row in world.tiles for tile in row if tile.terrain == "park"]
        if not candidates:
            return self.home_tile(world)
        tile = self.rng.choice(candidates)
        return (tile.x, tile.y)

    def _choose_commercial_target(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        shops = world.building_by_type("shop") + world.building_by_type("office")
        if not shops:
            return self.home_tile(world)
        return self.rng.choice(shops).tile

    def _choose_service_target(self, world: WorldMap, building_type: str) -> Optional[Tuple[int, int]]:
        buildings = world.building_by_type(building_type)
        if not buildings:
            return self.home_tile(world)
        return self.rng.choice(buildings).tile

    def current_activity(self, hour: int) -> str:
        block = self.current_block(hour)
        return block.activity if block is not None else "idle"

    def current_block(self, hour: int) -> Optional[ScheduleBlock]:
        return self.schedule.get(hour)

    # ------------------------------------------------------------------
    # Map movement
    # ------------------------------------------------------------------
    def vehicle_speed_bonus(self) -> float:
        return {
            "none": 1.0,
            "bike": 1.15,
            "bus_pass": 1.25,
            "car": 1.45,
        }.get(self.vehicle, 1.0)

    def set_destination(self, target: Optional[Tuple[int, int]], world: WorldMap) -> None:
        if target is None:
            return
        self.destination = target
        self.path = world.find_route(self.location, target, max_steps=2000)

    def move_step(self, world: WorldMap) -> None:
        if not self.path or self.location == self.destination:
            return
        if self.path[0] == self.location:
            self.path.pop(0)
        steps = 2 if self.vehicle in {"bike", "car"} else 1
        for _ in range(steps):
            if not self.path:
                break
            next_pos = self.path.pop(0)
            self.location = next_pos
        world.register_population_position(self.person_id, *self.location)

    def update_position_for_hour(self, world: WorldMap, hour: int) -> None:
        block = self.current_block(hour)
        if block and block.target:
            if self.destination != block.target:
                self.set_destination(block.target, world)
            self.move_step(world)
        else:
            self.destination = self.location
            self.path = []

    # ------------------------------------------------------------------
    # Life simulation
    # ------------------------------------------------------------------
    def daily_update(self, world: WorldMap, day_index: int) -> None:
        self.age_if_needed(day_index)
        self.decay_relationships(day_index)
        self.skill_decay()
        self.resolve_basic_needs()
        self.schedule = {}
        self.last_major_event_day = day_index if self.stress > 0.82 or self.happiness < 0.2 else self.last_major_event_day

    def hourly_update(self, world: WorldMap, day_index: int, hour: int) -> None:
        self.schedule[hour] = self._plan_hour(world, day_index, hour)
        activity = self.current_activity(hour)
        self.update_position_for_hour(world, hour)
        self._apply_activity_effects(activity)
        self._ambient_effects_from_location(world)
        self._maybe_generate_spontaneous_social_contact(world, day_index)

    def _apply_activity_effects(self, activity: str) -> None:
        if activity == "sleep":
            self.energy = clamp(self.energy + 0.18, 0.0, 1.0)
            self.stress = clamp(self.stress - 0.05, 0.0, 1.0)
            self.hours_since_rest = 0
        else:
            self.hours_since_rest += 1
            self.energy = clamp(self.energy - 0.04, 0.0, 1.0)

        if activity == "work":
            skill_match = self.skills.get(self._job_skill_key() or "", 0.0)
            work_score = (
                self.work_traits["work_ethic"] * 0.28
                + self.work_traits["reliability"] * 0.24
                + self.work_traits["teamwork"] * 0.12
                + self.work_traits["adaptability"] * 0.12
                + skill_match * 0.24
            )
            self.job_performance = clamp(self.job_performance + (work_score - 0.55) * 0.025, 0.0, 1.0)
            self.job_satisfaction = clamp(
                self.job_satisfaction + (skill_match - 0.45) * 0.015 - max(0.0, self.stress - 0.72) * 0.02,
                0.0,
                1.0,
            )
            if work_score < 0.42:
                self.days_unproductive += 1
            else:
                self.days_unproductive = max(0, self.days_unproductive - 1)
            self.motivation = clamp(self.motivation + 0.01 + self.work_traits["learning_drive"] * 0.004, 0.0, 1.0)
            self.stress = clamp(self.stress + 0.025 - self.personality.discipline * 0.01 + (0.55 - self.job_satisfaction) * 0.02, 0.0, 1.0)
            practiced_skill = self._job_skill_key()
            if practiced_skill:
                self.skill_practice[practiced_skill] = min(3.0, self.skill_practice.get(practiced_skill, 0.0) + 0.45)
                self.skills[practiced_skill] = clamp(
                    self.skills[practiced_skill] + 0.00035 + self.work_traits["learning_drive"] * 0.0002,
                    0.0,
                    1.0,
                )
        elif activity in {"study", "study_self"}:
            self.stress = clamp(self.stress + 0.02, 0.0, 1.0)
            key = self._priority_learning_skill()
            education_multiplier = {
                "none": 1.0,
                "school": 1.1,
                "certificate": 1.22,
                "college": 1.32,
            }.get(self.education_level, 1.0)
            gain = (0.0008 + self.genetics.cognition * 0.0003 + self.work_traits["learning_drive"] * 0.00025) * education_multiplier
            self.skills[key] = clamp(self.skills[key] + gain, 0.0, 1.0)
            self.skill_practice[key] = min(4.0, self.skill_practice.get(key, 0.0) + 1.0)
        elif activity == "socialize":
            self.happiness = clamp(self.happiness + 0.04 + self.personality.sociability * 0.02, 0.0, 1.0)
            self.stress = clamp(self.stress - 0.03, 0.0, 1.0)
        elif activity == "exercise":
            self.health = clamp(self.health + 0.01, 0.0, 1.0)
            self.happiness = clamp(self.happiness + 0.015, 0.0, 1.0)
        elif activity == "job_search":
            self.stress = clamp(self.stress + 0.02, 0.0, 1.0)
            self.motivation = clamp(self.motivation - 0.01, 0.0, 1.0)
        elif activity == "rest":
            self.stress = clamp(self.stress - 0.015, 0.0, 1.0)
            self.happiness = clamp(self.happiness + 0.005, 0.0, 1.0)
        elif activity == "clinic":
            self.health = clamp(self.health + 0.02, 0.0, 1.0)
            self.cash = max(0.0, self.cash - 40.0)

    def _ambient_effects_from_location(self, world: WorldMap) -> None:
        tile = world.tile_at(*self.location)
        district = world.districts[tile.district_id]
        self.stress = clamp(self.stress + tile.crime_pressure * 0.005 - district.transit_score * 0.003, 0.0, 1.0)
        self.happiness = clamp(self.happiness + (tile.property_value / 4000.0) * 0.002, 0.0, 1.0)

    def _maybe_generate_spontaneous_social_contact(self, world: WorldMap, day_index: int) -> None:
        tile = world.tile_at(*self.location)
        others = [pid for pid in tile.occupants if pid != self.person_id]
        if not others or self.rng.random() > 0.15:
            return
        other_id = self.rng.choice(others)
        rel = self.relationship_with(other_id)
        rel.affinity = clamp(rel.affinity + self.personality.sociability * 0.04 - self.stress * 0.015, -1.0, 1.0)
        rel.familiarity = clamp(rel.familiarity + 0.05, 0.0, 1.0)
        rel.last_interaction_day = day_index
        rel.interaction_count += 1
        if other_id not in self.social_circle and rel.familiarity > 0.25:
            self.social_circle.append(other_id)
        if self.rng.random() < 0.05:
            self.add_memory("social", f"Had an unexpected conversation with citizen {other_id}.", 0.03)

    # ------------------------------------------------------------------
    # Finance and career
    # ------------------------------------------------------------------
    def assign_home(self, household_id: int, listing: HousingListing, building: Building) -> None:
        self.household_id = household_id
        self.home_building_id = building.building_id
        self.location = building.tile
        self.destination = self.location

    def assign_job(self, company_id: int, title: str, salary: float, shift: Tuple[int, int]) -> None:
        self.assign_job_profile(company_id, title, salary, shift, None)

    def assign_job_profile(
        self,
        company_id: int,
        title: str,
        salary: float,
        shift: Tuple[int, int],
        skill_key: Optional[str],
    ) -> None:
        self.job_company_id = company_id
        self.job_title = title
        self.job_skill = skill_key
        self.salary = salary
        self.job_shift = shift
        self.job_performance = clamp(self.job_performance + 0.06, 0.0, 1.0)
        self.job_satisfaction = clamp(self.job_satisfaction + 0.05, 0.0, 1.0)
        self.days_unproductive = 0
        self.add_memory("career", f"Took a new job as {title}.", 0.08)

    def remove_job(self) -> None:
        if self.job_title:
            self.add_memory("career", f"Lost job: {self.job_title}.", -0.12)
        self.job_company_id = None
        self.job_title = None
        self.job_skill = None
        self.salary = 0.0
        self.job_performance = clamp(self.job_performance - 0.08, 0.0, 1.0)
        self.job_satisfaction = clamp(self.job_satisfaction - 0.12, 0.0, 1.0)
        self.days_unproductive = 0

    def receive_pay(self) -> None:
        if self.salary <= 0.0:
            return
        gross = self.salary / 30.0
        self.cash += gross * 0.35
        self.bank_balance += gross * 0.65
        self.happiness = clamp(self.happiness + 0.015, 0.0, 1.0)

    def pay_living_costs(self, amount: float) -> None:
        from_cash = min(self.cash, amount)
        self.cash -= from_cash
        remain = amount - from_cash
        if remain > 0:
            from_bank = min(self.bank_balance, remain)
            self.bank_balance -= from_bank
            remain -= from_bank
        if remain > 0:
            self.debt += remain
            self.stress = clamp(self.stress + 0.08, 0.0, 1.0)

    def job_eligibility_score(self, posting: JobPosting, world: WorldMap) -> float:
        company = world.companies.get(posting.company_id)
        if company is None:
            return -1.0
        building = world.buildings.get(company.building_id)
        if building is None:
            return -1.0
        commute = world.estimate_commute_time(self.location, building.tile, self.vehicle_speed_bonus())
        skill = self.skills.get(posting.required_skill, 0.0)
        strongest_skill_key = max(self.skills, key=self.skills.get) if self.skills else posting.required_skill
        strongest_skill_value = self.skills.get(strongest_skill_key, 0.0)
        alignment_bonus = 0.12 if strongest_skill_key == posting.required_skill else max(0.0, skill - strongest_skill_value * 0.75) * 0.05
        return (
            skill * 0.52
            + self.personality.discipline * 0.1
            + self.personality.ambition * 0.08
            + self.work_traits["work_ethic"] * 0.08
            + self.work_traits["learning_drive"] * 0.05
            + self.education_bonus() * 0.08
            + alignment_bonus
            + clamp(1.0 - commute / 240.0, 0.0, 1.0) * 0.09
        )

    def education_bonus(self) -> float:
        return {
            "none": 0.0,
            "school": 0.25,
            "certificate": 0.45,
            "college": 0.65,
        }.get(self.education_level, 0.0)

    def seek_job(self, world: WorldMap) -> Optional[int]:
        if self.job_company_id is not None:
            return None
        postings = world.open_job_postings()[:120]
        if not postings:
            return None
        scored = sorted(postings, key=lambda post: self.job_eligibility_score(post, world), reverse=True)
        best = scored[0]
        if self.job_eligibility_score(best, world) < 0.0:
            return None
        if self.job_eligibility_score(best, world) < max(0.15, best.required_level * 0.55):
            return None
        return best.posting_id

    def choose_investment_symbol(self, symbols: List[str]) -> Optional[str]:
        if not symbols or self.bank_balance < 500.0:
            return None
        return self.rng.choice(symbols)

    # ------------------------------------------------------------------
    # Education
    # ------------------------------------------------------------------
    def enroll(self, status: str, building_id: int, tuition: float) -> None:
        self.student_status = status
        self.current_enrollment_building = building_id
        self.education_level = "school" if status == "school" else self.education_level
        self.pay_living_costs(tuition)
        self.add_memory("education", f"Enrolled in {status}.", 0.05)

    def complete_certification(self, name: str, skill_key: str) -> None:
        if name not in self.certifications:
            self.certifications.append(name)
        self.education_level = "certificate"
        self.skills[skill_key] = clamp(self.skills[skill_key] + 0.12, 0.0, 1.0)
        self.work_traits["learning_drive"] = clamp(self.work_traits["learning_drive"] + 0.05, 0.0, 1.0)
        self.add_memory("education", f"Completed certification: {name}.", 0.09)

    def graduate_college(self, major_skill: str) -> None:
        self.education_level = "college"
        self.skills[major_skill] = clamp(self.skills[major_skill] + 0.18, 0.0, 1.0)
        self.work_traits["adaptability"] = clamp(self.work_traits["adaptability"] + 0.05, 0.0, 1.0)
        self.work_traits["learning_drive"] = clamp(self.work_traits["learning_drive"] + 0.08, 0.0, 1.0)
        self.student_status = None
        self.current_enrollment_building = None
        self.add_memory("education", "Graduated from college.", 0.14)

    def _priority_learning_skill(self) -> str:
        job_skill = self._job_skill_key()
        if job_skill:
            return job_skill
        weakest_skill = min(self.skills.items(), key=lambda item: item[1])[0]
        if self.learning_focus_skill is None or self.learning_focus_skill not in self.skills:
            self.learning_focus_skill = weakest_skill
        focus_value = self.skills[self.learning_focus_skill]
        weakest_value = self.skills[weakest_skill]
        if focus_value > 0.82 and weakest_value < focus_value - 0.35:
            self.learning_focus_skill = weakest_skill
        return self.learning_focus_skill

    def _job_skill_key(self) -> Optional[str]:
        if self.job_skill:
            return self.job_skill
        if self.job_company_id and self.job_title:
            for key in ["software", "service", "logistics", "engineering", "finance", "law"]:
                if key in self.job_title.lower():
                    return key
        return None

    # ------------------------------------------------------------------
    # Social and family logic
    # ------------------------------------------------------------------
    def maybe_form_relationship(self, other_id: int) -> bool:
        if other_id in self.family_ids or other_id in self.parent_ids or other_id == self.spouse_id:
            return False
        rel = self.relationship_with(other_id)
        if rel.closeness() > 0.62 and self.personality.sociability > 0.35:
            rel.romance = clamp(rel.romance + 0.1, 0.0, 1.0)
            return rel.romance > 0.45
        return False

    def maybe_have_child(self, partner_id: int, next_person_id: int) -> Optional[Dict[str, Any]]:
        if self.age < 22 or self.age > 48:
            return None
        if self.spouse_id != partner_id:
            return None
        if self.relationship_with(partner_id).romance < 0.62:
            return None
        if self.rng.random() > 0.015:
            return None
        return {
            "new_person_id": next_person_id,
            "parents": [self.person_id, partner_id],
        }

    def decay_relationships(self, day_index: int) -> None:
        for relationship in self.relationships.values():
            days = max(0, day_index - relationship.last_interaction_day)
            if days <= 0:
                continue
            decay = min(0.03, days * 0.0008)
            relationship.affinity = clamp(relationship.affinity - decay * (1.0 - self.personality.sociability), -1.0, 1.0)
            relationship.familiarity = clamp(relationship.familiarity - decay * 0.5, 0.0, 1.0)
            relationship.romance = clamp(relationship.romance - decay * 0.4, 0.0, 1.0)

    def spread_gossip(self) -> Optional[str]:
        if not self.gossip_log or self.personality.sociability < 0.2:
            return None
        return self.rng.choice(self.gossip_log)

    def set_relation_role(self, other_id: int, role: str) -> None:
        if other_id == self.person_id:
            return
        self.relation_roles[int(other_id)] = role
        if role in {"mother", "father", "parent", "child", "son", "daughter", "sibling", "wife", "husband", "spouse"}:
            if other_id not in self.family_ids:
                self.family_ids.append(other_id)

    def set_spouse(self, other: "Person") -> None:
        self.spouse_id = other.person_id
        other.spouse_id = self.person_id
        self_role = "wife" if other.gender == "woman" else "husband" if other.gender == "man" else "spouse"
        other_role = "wife" if self.gender == "woman" else "husband" if self.gender == "man" else "spouse"
        self.set_relation_role(other.person_id, self_role)
        other.set_relation_role(self.person_id, other_role)
        rel_self = self.relationship_with(other.person_id)
        rel_other = other.relationship_with(self.person_id)
        rel_self.romance = clamp(max(rel_self.romance, 0.72), 0.0, 1.0)
        rel_other.romance = clamp(max(rel_other.romance, 0.72), 0.0, 1.0)
        rel_self.trust = clamp(max(rel_self.trust, 0.65), 0.0, 1.0)
        rel_other.trust = clamp(max(rel_other.trust, 0.65), 0.0, 1.0)

    def add_parent(self, parent: "Person") -> None:
        if parent.person_id not in self.parent_ids:
            self.parent_ids.append(parent.person_id)
        parent_role = "mother" if parent.gender == "woman" else "father" if parent.gender == "man" else "parent"
        child_role = "daughter" if self.gender == "woman" else "son" if self.gender == "man" else "child"
        self.set_relation_role(parent.person_id, parent_role)
        parent.set_relation_role(self.person_id, child_role)
        if self.person_id not in parent.children_ids:
            parent.children_ids.append(self.person_id)
        rel_child = self.relationship_with(parent.person_id)
        rel_parent = parent.relationship_with(self.person_id)
        rel_child.trust = clamp(max(rel_child.trust, 0.6), 0.0, 1.0)
        rel_parent.trust = clamp(max(rel_parent.trust, 0.75), 0.0, 1.0)

    # ------------------------------------------------------------------
    # Internal wellness model
    # ------------------------------------------------------------------
    def age_if_needed(self, day_index: int) -> None:
        if day_index > 0 and day_index % 365 == 0:
            self.age += 1
            self.life_stage = self._derive_life_stage()
            self.health = clamp(self.health - 0.01 * (1.0 - self.genetics.longevity), 0.0, 1.0)
            self.add_memory("life", f"Had a birthday and turned {self.age}.", 0.03)

    def resolve_basic_needs(self) -> None:
        if self.hours_since_rest > 18:
            self.stress = clamp(self.stress + 0.06, 0.0, 1.0)
            self.health = clamp(self.health - 0.01, 0.0, 1.0)
        if self.cash + self.bank_balance < 100.0:
            self.stress = clamp(self.stress + 0.04, 0.0, 1.0)
            self.happiness = clamp(self.happiness - 0.03, 0.0, 1.0)
        if self.debt > 20_000.0:
            self.motivation = clamp(self.motivation - 0.02, 0.0, 1.0)

    def skill_decay(self) -> None:
        for skill, value in list(self.skills.items()):
            practice = self.skill_practice.get(skill, 0.0)
            if practice >= 0.75:
                decay = 0.00035
            elif value > 0.4:
                decay = 0.0025
            else:
                decay = 0.001
            self.skills[skill] = clamp(value - decay, 0.0, 1.0)
            self.skill_practice[skill] = max(0.0, practice * 0.55 - 0.05)

    # ------------------------------------------------------------------
    # Location helpers
    # ------------------------------------------------------------------
    def home_tile(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        if self.home_building_id is None or self.home_building_id not in world.buildings:
            return self.location
        return world.buildings[self.home_building_id].tile

    def work_tile(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        if self.job_company_id is None or self.job_company_id not in world.companies:
            return None
        company = world.companies[self.job_company_id]
        return world.buildings[company.building_id].tile

    def school_tile(self, world: WorldMap) -> Optional[Tuple[int, int]]:
        if self.current_enrollment_building is None or self.current_enrollment_building not in world.buildings:
            return None
        return world.buildings[self.current_enrollment_building].tile

    def _serialize_memories(self) -> List[List[Any]]:
        serialized: List[List[Any]] = []
        for memory in self.memories:
            serialized.append(
                [
                    memory.timestamp,
                    memory.category,
                    memory.headline,
                    round_for_save(memory.impact, PERSON_SAVE_FLOAT_DIGITS),
                    memory.location,
                    list(memory.related_people),
                    list(memory.tags),
                ]
            )
        return serialized

    def _serialize_relationships(self) -> Dict[int, List[Any]]:
        serialized: Dict[int, List[Any]] = {}
        for pid, rel in self.relationships.items():
            serialized[int(pid)] = [
                round_for_save(rel.affinity, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.trust, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.romance, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.respect, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.familiarity, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.rivalry, PERSON_SAVE_FLOAT_DIGITS),
                round_for_save(rel.gossip_knowledge, PERSON_SAVE_FLOAT_DIGITS),
                rel.last_interaction_day,
                rel.interaction_count,
            ]
        return serialized

    @staticmethod
    def _deserialize_memory(memory: Any) -> MemoryRecord:
        if isinstance(memory, dict):
            return MemoryRecord(**memory)
        timestamp, category, headline, impact, location, related_people, tags = memory
        return MemoryRecord(
            timestamp=timestamp,
            category=category,
            headline=headline,
            impact=impact,
            location=tuple(location) if location is not None else None,
            related_people=list(related_people),
            tags=list(tags),
        )

    @staticmethod
    def _deserialize_relationship(pid: int, relationship_data: Any) -> Relationship:
        if isinstance(relationship_data, dict):
            return Relationship(**relationship_data)
        return Relationship(
            person_id=pid,
            affinity=relationship_data[0],
            trust=relationship_data[1],
            romance=relationship_data[2],
            respect=relationship_data[3],
            familiarity=relationship_data[4],
            rivalry=relationship_data[5],
            gossip_knowledge=relationship_data[6],
            last_interaction_day=relationship_data[7],
            interaction_count=relationship_data[8],
        )

    # ------------------------------------------------------------------
    # Serialization support
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 2,
            "person_id": self.person_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "age": self.age,
            "gender": self.gender,
            "genetics": self.genetics.to_dict(),
            "personality": self.personality.axis_dict(),
            "health": round_for_save(self.health, PERSON_SAVE_FLOAT_DIGITS),
            "energy": round_for_save(self.energy, PERSON_SAVE_FLOAT_DIGITS),
            "stress": round_for_save(self.stress, PERSON_SAVE_FLOAT_DIGITS),
            "happiness": round_for_save(self.happiness, PERSON_SAVE_FLOAT_DIGITS),
            "motivation": round_for_save(self.motivation, PERSON_SAVE_FLOAT_DIGITS),
            "reputation_public": round_for_save(self.reputation_public, PERSON_SAVE_FLOAT_DIGITS),
            "hidden_karma": round_for_save(self.hidden_karma, PERSON_SAVE_FLOAT_DIGITS),
            "crime_tendency": round_for_save(self.crime_tendency, PERSON_SAVE_FLOAT_DIGITS),
            "skills": {key: round_for_save(value, PERSON_SAVE_FLOAT_DIGITS) for key, value in self.skills.items()},
            "skill_practice": {key: round_for_save(value, PERSON_SAVE_FLOAT_DIGITS) for key, value in self.skill_practice.items()},
            "learning_focus_skill": self.learning_focus_skill,
            "education_level": self.education_level,
            "certifications": self.certifications,
            "memories": self._serialize_memories(),
            "relationships": self._serialize_relationships(),
            "family_ids": self.family_ids,
            "parent_ids": self.parent_ids,
            "children_ids": self.children_ids,
            "spouse_id": self.spouse_id,
            "relation_roles": self.relation_roles,
            "household_id": self.household_id,
            "home_building_id": self.home_building_id,
            "job_company_id": self.job_company_id,
            "job_title": self.job_title,
            "job_skill": self.job_skill,
            "salary": round_for_save(self.salary, 2),
            "job_shift": self.job_shift,
            "student_status": self.student_status,
            "current_enrollment_building": self.current_enrollment_building,
            "social_circle": self.social_circle,
            "work_traits": {key: round_for_save(value, PERSON_SAVE_FLOAT_DIGITS) for key, value in self.work_traits.items()},
            "job_performance": round_for_save(self.job_performance, PERSON_SAVE_FLOAT_DIGITS),
            "job_satisfaction": round_for_save(self.job_satisfaction, PERSON_SAVE_FLOAT_DIGITS),
            "days_unproductive": self.days_unproductive,
            "vehicle": self.vehicle,
            "cash": round_for_save(self.cash, 2),
            "bank_balance": round_for_save(self.bank_balance, 2),
            "debt": round_for_save(self.debt, 2),
            "assets": round_for_save(self.assets, 2),
            "investment_accounts": {key: round_for_save(value, 2) for key, value in self.investment_accounts.items()},
            "arrest_record": self.arrest_record,
            "location": self.location,
            "destination": self.destination,
            "hours_since_rest": self.hours_since_rest,
            "last_paid_day": self.last_paid_day,
            "last_major_event_day": self.last_major_event_day,
            "gossip_log": self.gossip_log,
            "life_stage": self.life_stage,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], rng: random.Random, world: WorldMap, schedule_day_index: int = 0) -> "Person":
        person = cls(person_id=data["person_id"], rng=rng, world=world, age=data["age"])
        person.first_name = data["first_name"]
        person.last_name = data["last_name"]
        person.full_name = data["full_name"]
        person.gender = data["gender"]
        person.genetics = GeneticsProfile(**data["genetics"])
        person.personality = PersonalityProfile(**data["personality"])
        person.health = data["health"]
        person.energy = data["energy"]
        person.stress = data["stress"]
        person.happiness = data["happiness"]
        person.motivation = data["motivation"]
        person.reputation_public = data["reputation_public"]
        person.hidden_karma = data["hidden_karma"]
        person.crime_tendency = data["crime_tendency"]
        person.skills = data["skills"]
        person.skill_practice = {key: 0.0 for key in SKILL_KEYS}
        person.skill_practice.update(data.get("skill_practice", {}))
        person.learning_focus_skill = data.get("learning_focus_skill")
        person.education_level = data["education_level"]
        person.certifications = list(data["certifications"])
        person.memories = [cls._deserialize_memory(memory) for memory in data["memories"]]
        person.relationships = {
            int(pid): cls._deserialize_relationship(int(pid), rel)
            for pid, rel in data["relationships"].items()
        }
        person.family_ids = list(data["family_ids"])
        person.parent_ids = list(data.get("parent_ids", []))
        person.children_ids = list(data["children_ids"])
        person.spouse_id = data.get("spouse_id")
        person.relation_roles = {int(pid): role for pid, role in data.get("relation_roles", {}).items()}
        person.household_id = data["household_id"]
        person.home_building_id = data["home_building_id"]
        person.job_company_id = data["job_company_id"]
        person.job_title = data["job_title"]
        person.job_skill = data.get("job_skill")
        person.salary = data["salary"]
        person.job_shift = tuple(data["job_shift"])
        person.student_status = data["student_status"]
        person.current_enrollment_building = data["current_enrollment_building"]
        person.social_circle = list(data["social_circle"])
        person.work_traits = {key: 0.5 for key in WORK_TRAIT_KEYS}
        person.work_traits.update(data.get("work_traits", {}))
        person.job_performance = data.get("job_performance", person.job_performance)
        person.job_satisfaction = data.get("job_satisfaction", person.job_satisfaction)
        person.days_unproductive = data.get("days_unproductive", 0)
        person.vehicle = data["vehicle"]
        person.cash = data["cash"]
        person.bank_balance = data["bank_balance"]
        person.debt = data["debt"]
        person.assets = data["assets"]
        person.investment_accounts = dict(data["investment_accounts"])
        person.arrest_record = list(data["arrest_record"])
        person.location = tuple(data["location"])
        person.destination = tuple(data["destination"])
        person.path = [tuple(step) for step in data.get("path", [])]
        person.hours_since_rest = data["hours_since_rest"]
        person.last_paid_day = data["last_paid_day"]
        person.last_major_event_day = data["last_major_event_day"]
        person.gossip_log = list(data["gossip_log"])
        person.life_stage = data["life_stage"]
        person.path = []
        person.schedule = {}
        return person


class Population:
    """Owns all people and household graphs."""

    def __init__(self, seed: int, world: WorldMap, size: int = 240) -> None:
        self.seed = seed
        self.rng = random.Random(seed + 101)
        self.world = world
        self.people: Dict[int, Person] = {}
        self.households: Dict[int, Household] = {}
        self._household_counter = 1
        self._person_counter = 1
        self.generate_population(size)

    # ------------------------------------------------------------------
    # Population generation
    # ------------------------------------------------------------------
    def generate_population(self, size: int) -> None:
        for _ in range(size):
            person = Person(self._person_counter, self.rng, self.world, age=self._sample_initial_age())
            self.people[person.person_id] = person
            self.world.register_population_position(person.person_id, *person.location)
            self._person_counter += 1
        self._assign_homes()
        self._assign_default_education()
        self._assign_initial_social_graph()

    def _sample_initial_age(self) -> int:
        roll = self.rng.random()
        if roll < 0.08:
            return self.rng.randint(0, 12)
        if roll < 0.16:
            return self.rng.randint(13, 17)
        if roll < 0.42:
            return self.rng.randint(18, 29)
        if roll < 0.74:
            return self.rng.randint(30, 49)
        if roll < 0.9:
            return self.rng.randint(50, 64)
        return self.rng.randint(65, 84)

    def _assign_homes(self) -> None:
        listings = self.world.available_housing()
        self.rng.shuffle(listings)
        adults = [person for person in self.people.values() if person.age >= 18]
        minors = [person for person in self.people.values() if person.age < 18]
        self.rng.shuffle(adults)
        self.rng.shuffle(minors)
        assigned_ids: set[int] = set()

        while listings and (adults or minors):
            listing = listings.pop()
            listing.occupied = True
            building = self.world.buildings[listing.building_id]
            members = self._build_household_members(adults, minors, listing.bedrooms)
            if not members:
                continue
            household = Household(
                household_id=self._household_counter,
                member_ids=[member.person_id for member in members],
                home_building_id=building.building_id,
                listing_id=listing.listing_id,
                savings_pool=round(sum(member.bank_balance for member in members), 2),
                monthly_costs=round(listing.rent * 1.15, 2),
            )
            self.households[household.household_id] = household
            for member in members:
                member.assign_home(household.household_id, listing, building)
                assigned_ids.add(member.person_id)
                self.world.register_population_position(member.person_id, *member.location)
            listing.household_id = household.household_id
            self._link_household_family(members)
            self._household_counter += 1
        for person in self.people.values():
            if person.person_id not in assigned_ids:
                fallback_tile = self.world.random_walkable_tile()
                person.location = (fallback_tile.x, fallback_tile.y)
                self.world.register_population_position(person.person_id, *person.location)

    def _build_household_members(self, adults: List[Person], minors: List[Person], bedrooms: int) -> List[Person]:
        household_size_cap = max(1, min(6, bedrooms + 2))
        members: List[Person] = []
        if adults and minors and self.rng.random() < 0.48:
            adult_count = 2 if len(adults) >= 2 and bedrooms >= 2 and self.rng.random() < 0.68 else 1
            for _ in range(min(adult_count, len(adults))):
                members.append(adults.pop())
            child_target = min(len(minors), household_size_cap - len(members), self.rng.randint(1, max(1, bedrooms + 1)))
            for _ in range(child_target):
                members.append(minors.pop())
        elif adults:
            adult_count = 2 if len(adults) >= 2 and self.rng.random() < 0.42 else 1
            adult_count = min(adult_count, len(adults), household_size_cap)
            for _ in range(adult_count):
                members.append(adults.pop())
            if minors and len(members) < household_size_cap and self.rng.random() < 0.25:
                members.append(minors.pop())
        elif minors:
            members.append(minors.pop())
        return members

    def _link_household_family(self, members: List[Person]) -> None:
        adults = [member for member in members if member.age >= 18]
        minors = [member for member in members if member.age < 18]
        if len(adults) >= 2 and not adults[0].spouse_id and not adults[1].spouse_id:
            if abs(adults[0].age - adults[1].age) <= 18:
                adults[0].set_spouse(adults[1])
        for minor in minors:
            for parent in adults[:2]:
                minor.add_parent(parent)
        for member in members:
            for other in members:
                if member.person_id == other.person_id:
                    continue
                if other.person_id not in member.family_ids:
                    member.family_ids.append(other.person_id)
                if member.age < 18 and other.age < 18 and set(member.parent_ids) & set(other.parent_ids):
                    member.set_relation_role(other.person_id, "sibling")
                elif member.age >= 18 and other.age >= 18 and member.spouse_id != other.person_id and other.spouse_id != member.person_id:
                    if member.relation_roles.get(other.person_id) is None:
                        member.set_relation_role(other.person_id, "relative")

    def _assign_default_education(self) -> None:
        schools = self.world.building_by_type("school")
        colleges = self.world.building_by_type("college")
        for person in self.people.values():
            if person.age < 18 and schools:
                school = self.rng.choice(schools)
                person.student_status = "school"
                person.current_enrollment_building = school.building_id
                person.education_level = "school" if person.age >= 12 else "none"
            elif 18 <= person.age <= 24 and colleges and person.education_level in {"school", "none"} and self.rng.random() < 0.22:
                college = self.rng.choice(colleges)
                person.student_status = "college"
                person.current_enrollment_building = college.building_id

    def _assign_initial_social_graph(self) -> None:
        for person in self.people.values():
            household = self.household_for_person(person.person_id)
            if household is not None:
                for other_id in household.member_ids:
                    if other_id == person.person_id or other_id not in self.people:
                        continue
                    rel = person.relationship_with(other_id)
                    rel.affinity = self.rng.uniform(0.18, 0.72)
                    rel.trust = self.rng.uniform(0.32, 0.86)
                    rel.familiarity = self.rng.uniform(0.55, 1.0)
                    rel.last_interaction_day = 0
                    if other_id not in person.social_circle:
                        person.social_circle.append(other_id)
            district_candidates = self._district_social_candidates(person, limit=10)
            for other_id in district_candidates:
                if other_id == person.person_id:
                    continue
                rel = person.relationship_with(other_id)
                rel.affinity = self.rng.uniform(-0.2, 0.65)
                rel.trust = self.rng.uniform(0.0, 0.55)
                rel.familiarity = self.rng.uniform(0.05, 0.75)
                if rel.familiarity > 0.35:
                    if other_id not in person.social_circle:
                        person.social_circle.append(other_id)

    def _district_social_candidates(self, person: Person, limit: int = 10) -> List[int]:
        if person.home_building_id is None or person.home_building_id not in self.world.buildings:
            return []
        district_id = self.world.buildings[person.home_building_id].district_id
        candidates = [
            other.person_id
            for other in self.people.values()
            if other.person_id != person.person_id
            and other.home_building_id is not None
            and other.home_building_id in self.world.buildings
            and self.world.buildings[other.home_building_id].district_id == district_id
        ]
        self.rng.shuffle(candidates)
        return candidates[:limit]

    # ------------------------------------------------------------------
    # High-level tick API
    # ------------------------------------------------------------------
    def daily_update(self, day_index: int) -> None:
        for person in self.people.values():
            person.daily_update(self.world, day_index)

    def hourly_update(self, day_index: int, hour: int) -> None:
        for person in self.people.values():
            person.hourly_update(self.world, day_index, hour)

    def prepare_hour(self, day_index: int, hour: int) -> None:
        for person in self.people.values():
            person.schedule[hour] = person._plan_hour(self.world, day_index, hour)

    # ------------------------------------------------------------------
    # Career and household helpers
    # ------------------------------------------------------------------
    def unemployed_people(self) -> List[Person]:
        return [person for person in self.people.values() if person.job_company_id is None and person.age >= 18]

    def employed_people(self) -> List[Person]:
        return [person for person in self.people.values() if person.job_company_id is not None]

    def students(self) -> List[Person]:
        return [person for person in self.people.values() if person.student_status is not None]

    def nearest_people(self, x: int, y: int, radius: int = 4, limit: int = 12) -> List[Person]:
        found: List[Tuple[int, Person]] = []
        for person in self.people.values():
            distance = abs(person.location[0] - x) + abs(person.location[1] - y)
            if distance <= radius:
                found.append((distance, person))
        found.sort(key=lambda item: item[0])
        return [person for _, person in found[:limit]]

    def household_for_person(self, person_id: int) -> Optional[Household]:
        person = self.people[person_id]
        if person.household_id is None:
            return None
        return self.households.get(person.household_id)

    def pay_household_costs(self) -> None:
        for household in self.households.values():
            members = [self.people[pid] for pid in household.member_ids if pid in self.people]
            if not members:
                continue
            per_member = household.monthly_costs / max(1, len(members))
            for member in members:
                member.pay_living_costs(per_member)

    # ------------------------------------------------------------------
    # Social graph and emergent family logic
    # ------------------------------------------------------------------
    def run_social_layer(self, day_index: int) -> List[Dict[str, Any]]:
        births: List[Dict[str, Any]] = []
        ids = list(self.people.keys())
        self.rng.shuffle(ids)
        for person_id in ids:
            person = self.people[person_id]
            if person.age < 18 or not person.social_circle:
                continue
            partner_id = self._choose_relationship_target(person)
            if partner_id not in self.people or partner_id == person.person_id:
                continue
            other = self.people[partner_id]
            rel_a = person.relationship_with(partner_id)
            rel_b = other.relationship_with(person.person_id)
            boost = 0.01 + min(person.personality.empathy, other.personality.empathy) * 0.03
            rel_a.affinity = clamp(rel_a.affinity + boost, -1.0, 1.0)
            rel_b.affinity = clamp(rel_b.affinity + boost, -1.0, 1.0)
            if person.maybe_form_relationship(partner_id):
                rel_b.romance = clamp(rel_b.romance + 0.08, 0.0, 1.0)
                if person.spouse_id is None and other.spouse_id is None and rel_a.romance > 0.72 and rel_b.romance > 0.68:
                    person.set_spouse(other)
            child = person.maybe_have_child(partner_id, self._person_counter)
            if child:
                births.append(child)
                self._person_counter += 1
        return births

    def _choose_relationship_target(self, person: Person) -> int:
        if person.spouse_id is not None and person.spouse_id in self.people:
            return person.spouse_id
        candidates = [
            other_id
            for other_id in person.social_circle
            if other_id in self.people
            and other_id not in person.family_ids
            and self.people[other_id].age >= 18
            and abs(self.people[other_id].age - person.age) <= 14
        ]
        if not candidates:
            return self.rng.choice(person.social_circle)
        return self.rng.choice(candidates)

    def create_child(self, new_person_id: int, parents: List[int]) -> Person:
        child = Person(new_person_id, self.rng, self.world, age=0)
        child.age = 0
        child.life_stage = "child"
        child.education_level = "none"
        child.health = clamp(0.75 + self.rng.uniform(-0.1, 0.1), 0.0, 1.0)
        child.location = self.people[parents[0]].location
        child.destination = child.location
        child.family_ids = list(parents)
        for parent_id in parents:
            if self.people[parent_id].household_id:
                child.household_id = self.people[parent_id].household_id
                child.home_building_id = self.people[parent_id].home_building_id
            child.add_parent(self.people[parent_id])
        self.people[child.person_id] = child
        self.world.register_population_position(child.person_id, *child.location)
        if child.household_id and child.household_id in self.households:
            self.households[child.household_id].member_ids.append(child.person_id)
        child.add_memory("life", "Entered the world as a newborn.", 0.1)
        return child

    # ------------------------------------------------------------------
    # Reporting helpers for the UI
    # ------------------------------------------------------------------
    def top_people_lines(self, limit: int = 8) -> List[str]:
        people = sorted(
            self.people.values(),
            key=lambda person: person.happiness * 0.35 + person.skills["software"] * 0.1 + person.reputation_public * 0.25 + person.bank_balance / 50_000.0,
            reverse=True,
        )
        lines = []
        for person in people[:limit]:
            title = person.job_title or "Unemployed"
            lines.append(
                f"{person.full_name[:18]:18} {title[:12]:12} "
                f"H:{person.happiness:0.2f} S:{person.stress:0.2f} ${person.bank_balance:0.0f}"
            )
        return lines

    def relationship_lines(self, person_id: int, limit: int = 8) -> List[str]:
        person = self.people[person_id]
        ordered = sorted(person.relationships.values(), key=lambda rel: rel.closeness(), reverse=True)
        lines = []
        for rel in ordered[:limit]:
            if rel.person_id not in self.people:
                continue
            other = self.people[rel.person_id]
            role = person.relation_roles.get(rel.person_id)
            role_label = f"{role[:6]:6} " if role else ""
            lines.append(
                f"{other.full_name[:18]:18} {role_label}A:{rel.affinity:0.2f} T:{rel.trust:0.2f} R:{rel.romance:0.2f}"
            )
        return lines

    def activity_heatmap(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for person in self.people.values():
            activity = person.current_activity(12)
            counts[activity] = counts.get(activity, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Serialization support
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "people": {pid: person.to_dict() for pid, person in self.people.items()},
            "households": {hid: household.__dict__ for hid, household in self.households.items()},
            "counters": {
                "household": self._household_counter,
                "person": self._person_counter,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], world: WorldMap, schedule_day_index: int = 0) -> "Population":
        population = cls(seed=data["seed"], world=world, size=0)
        population.people = {}
        population.households = {int(hid): Household(**household) for hid, household in data["households"].items()}
        population._household_counter = data["counters"]["household"]
        population._person_counter = data["counters"]["person"]
        for pid, person_data in data["people"].items():
            person = Person.from_dict(person_data, population.rng, world, schedule_day_index=schedule_day_index)
            population.people[int(pid)] = person
            world.register_population_position(person.person_id, *person.location)
        return population
