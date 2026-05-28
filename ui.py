"""
ui.py

Pure terminal user interface built on curses and ANSI-style colors.
The layout is intentionally information-dense, closer to old strategy
and management interfaces than to a minimal menu. The player sees the
simulation from multiple angles at once: map, people, economy, news,
calendar, and activity panels.
"""

from __future__ import annotations

import curses
import textwrap
import time
from typing import List, Optional, Tuple

from entities import Person
from engine import SimulationEngine


COLOR_PAIRS = {
    "default": (curses.COLOR_WHITE, curses.COLOR_BLACK),
    "water": (curses.COLOR_CYAN, curses.COLOR_BLACK),
    "park": (curses.COLOR_GREEN, curses.COLOR_BLACK),
    "rural": (curses.COLOR_YELLOW, curses.COLOR_BLACK),
    "suburban": (curses.COLOR_WHITE, curses.COLOR_BLACK),
    "urban": (curses.COLOR_WHITE, curses.COLOR_BLUE),
    "industrial": (curses.COLOR_MAGENTA, curses.COLOR_BLACK),
    "road": (curses.COLOR_BLACK, curses.COLOR_WHITE),
    "rail": (curses.COLOR_RED, curses.COLOR_BLACK),
    "player": (curses.COLOR_BLACK, curses.COLOR_GREEN),
    "npc": (curses.COLOR_BLACK, curses.COLOR_YELLOW),
    "panel": (curses.COLOR_WHITE, curses.COLOR_BLACK),
    "headline": (curses.COLOR_BLACK, curses.COLOR_CYAN),
    "warning": (curses.COLOR_YELLOW, curses.COLOR_BLACK),
    "danger": (curses.COLOR_RED, curses.COLOR_BLACK),
    "good": (curses.COLOR_GREEN, curses.COLOR_BLACK),
    "accent": (curses.COLOR_BLUE, curses.COLOR_BLACK),
}


class TerminalUI:
    """Curses frontend for the simulation engine."""

    def __init__(self, engine: SimulationEngine) -> None:
        self.engine = engine
        self.screen: Optional["curses._CursesWindow"] = None
        self.color_ids = {}
        self.map_view_width = 0
        self.map_view_height = 0
        self.status_message = "Arrows/WASD pan map. Space pause. Tab cycle citizen. F5 save. F9 load. Q quit."
        self.last_draw_time = 0.0
        self.frame_counter = 0
        self.panel_scroll = {"news": 0, "timeline": 0}
        self.target_fps = 15.0
        self.max_sim_steps_per_frame = 2

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    def run(self, screen: "curses._CursesWindow") -> None:
        self.screen = screen
        curses.curs_set(0)
        screen.nodelay(True)
        screen.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        self._init_colors()
        last_time = time.monotonic()
        sim_accumulator = 0.0
        draw_interval = 1.0 / self.target_fps
        while self.engine.running:
            now = time.monotonic()
            frame_time = now - last_time
            last_time = now
            # Clamp long stalls so an expensive daily tick does not cause a
            # large catch-up burst that makes controls feel sticky.
            frame_time = min(frame_time, 0.25)
            if not self.engine.paused:
                sim_accumulator += frame_time
            self.handle_input()
            steps = 0
            while not self.engine.paused and sim_accumulator >= self.engine.tick_duration and steps < self.max_sim_steps_per_frame:
                self.engine.step()
                sim_accumulator -= self.engine.tick_duration
                steps += 1
            self.draw()
            elapsed = time.monotonic() - now
            time.sleep(max(0.001, draw_interval - elapsed))

    def _init_colors(self) -> None:
        pair_id = 1
        for name, (fg, bg) in COLOR_PAIRS.items():
            curses.init_pair(pair_id, fg, bg)
            self.color_ids[name] = curses.color_pair(pair_id)
            pair_id += 1

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_input(self) -> None:
        if self.screen is None:
            return
        key = self.screen.getch()
        while key != -1:
            self._dispatch_key(key)
            key = self.screen.getch()

    def _dispatch_key(self, key: int) -> None:
        if key in (ord("q"), ord("Q")):
            self.engine.running = False
        elif key in (ord(" "),):
            self.engine.toggle_pause()
        elif key in (ord("+"), ord("=")):
            self.engine.change_speed(True)
        elif key == ord("-"):
            self.engine.change_speed(False)
        elif key in (curses.KEY_LEFT, ord("a"), ord("A")):
            self.engine.move_camera(-2, 0)
        elif key in (curses.KEY_RIGHT, ord("d"), ord("D")):
            self.engine.move_camera(2, 0)
        elif key in (curses.KEY_UP, ord("w"), ord("W")):
            self.engine.move_camera(0, -1)
        elif key in (curses.KEY_DOWN, ord("s")):
            self.engine.move_camera(0, 1)
        elif key == ord("c") or key == ord("C"):
            self.engine.center_on_selected_person()
        elif key == ord("\t"):
            self.engine.cycle_selected_person()
        elif key == ord("n") or key == ord("N"):
            self.panel_scroll["news"] += 1
        elif key == ord("m") or key == ord("M"):
            self.panel_scroll["news"] = max(0, self.panel_scroll["news"] - 1)
        elif key == ord("t") or key == ord("T"):
            self.panel_scroll["timeline"] += 1
        elif key == ord("g") or key == ord("G"):
            self.panel_scroll["timeline"] = max(0, self.panel_scroll["timeline"] - 1)
        elif key == curses.KEY_F5:
            self.engine.save("life_sim_save.pkl")
            self.status_message = "Saved simulation to life_sim_save.pkl"
        elif key == curses.KEY_F9:
            try:
                loaded = SimulationEngine.load("life_sim_save.pkl")
                self.engine = loaded
                self.status_message = "Loaded simulation from life_sim_save.pkl"
            except Exception as exc:
                self.status_message = f"Load failed: {exc}"

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self) -> None:
        if self.screen is None:
            return
        self.screen.erase()
        max_y, max_x = self.screen.getmaxyx()
        self._draw_header(0, 0, max_x)

        left_w = max(28, max_x // 4)
        right_w = max(34, max_x // 4)
        center_w = max_x - left_w - right_w
        header_h = 3
        footer_h = 2
        body_h = max_y - header_h - footer_h
        center_h = body_h

        self.map_view_width = max(20, center_w - 2)
        self.map_view_height = max(12, center_h - 2)

        self._draw_left_column(header_h, 0, body_h, left_w)
        self._draw_map_panel(header_h, left_w, center_h, center_w)
        self._draw_right_column(header_h, left_w + center_w, body_h, right_w)
        self._draw_footer(max_y - footer_h, 0, max_x, footer_h)

        self.screen.noutrefresh()
        curses.doupdate()
        self.last_draw_time = time.time()
        self.frame_counter += 1

    def _draw_header(self, y: int, x: int, width: int) -> None:
        selected = self.engine.selected_person()
        metrics = self.engine.macro_metrics()
        title = (
            f" ASCII LIFE SIM :: Seed {self.engine.seed} :: World {self.engine.world_seed} "
            f":: {self.engine.calendar.label()} :: {self.engine.weather.summary()} "
        )
        self._fill_line(y, x, width, " ", self.color_ids["headline"])
        self._write(y, x, title[: max(0, width - 1)], self.color_ids["headline"] | curses.A_BOLD)
        line2 = (
            f"Citizen {selected.full_name} | Mood {selected.happiness:0.2f} | Stress {selected.stress:0.2f} | "
            f"Cash ${selected.cash:0.0f} | Bank ${selected.bank_balance:0.0f} | Unemp {metrics['unemployment']:0.2f}"
        )
        self._fill_line(y + 1, x, width, " ", self.color_ids["panel"])
        self._write(y + 1, x, line2[: max(0, width - 1)], self.color_ids["panel"])
        self._fill_line(y + 2, x, width, "-", self.color_ids["accent"])

    def _draw_footer(self, y: int, x: int, width: int, height: int) -> None:
        if height <= 0:
            return
        self._fill_line(y, x, width, "-", self.color_ids["accent"])
        label = self.status_message
        if self.engine.paused:
            label += " [PAUSED]"
        label += f" | Tick {self.engine.tick_counter} | Frame {self.frame_counter} | Delay {self.engine.tick_duration:0.02f}s"
        self._fill_line(y + 1, x, width, " ", self.color_ids["panel"])
        self._write(y + 1, x, label[: max(0, width - 1)], self.color_ids["panel"])

    # ------------------------------------------------------------------
    # Left column
    # ------------------------------------------------------------------
    def _draw_left_column(self, y: int, x: int, height: int, width: int) -> None:
        top = height // 2
        self._draw_selected_person_panel(y, x, top, width)
        self._draw_relationship_panel(y + top, x, height - top, width)

    def _draw_selected_person_panel(self, y: int, x: int, height: int, width: int) -> None:
        person = self.engine.selected_person()
        self._panel_box(y, x, height, width, f" Citizen {person.person_id} ")
        lines = self._person_summary_lines(person, width - 2, height - 2)
        self._write_lines(y + 1, x + 1, width - 2, height - 2, lines)

    def _draw_relationship_panel(self, y: int, x: int, height: int, width: int) -> None:
        person = self.engine.selected_person()
        self._panel_box(y, x, height, width, " Relationships ")
        lines = self.engine.population.relationship_lines(person.person_id, limit=max(4, height - 3))
        if not lines:
            lines = ["No meaningful ties recorded."]
        self._write_lines(y + 1, x + 1, width - 2, height - 2, lines)

    # ------------------------------------------------------------------
    # Map and center panels
    # ------------------------------------------------------------------
    def _draw_map_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._panel_box(y, x, height, width, " City Map ")
        map_h = max(10, height - 10)
        map_w = width - 2
        self._draw_map(y + 1, x + 1, map_h, map_w)
        self._draw_map_stats(y + map_h + 1, x + 1, height - map_h - 2, map_w)

    def _draw_map(self, y: int, x: int, height: int, width: int) -> None:
        world = self.engine.world
        half_w = width // 2
        half_h = height // 2
        start_x = max(0, min(world.width - width, self.engine.camera_x - half_w))
        start_y = max(0, min(world.height - height, self.engine.camera_y - half_h))
        selected = self.engine.selected_person()
        for draw_y in range(height):
            world_y = start_y + draw_y
            if world_y >= world.height:
                break
            for draw_x in range(width):
                world_x = start_x + draw_x
                if world_x >= world.width:
                    break
                tile = world.tile_at(world_x, world_y)
                glyph = tile.glyph()
                color_key = tile.color_key()
                color = self.color_ids.get(color_key, self.color_ids["default"])
                if (world_x, world_y) == selected.location:
                    glyph = "&"
                    color = self.color_ids["warning"] | curses.A_BOLD
                elif tile.occupants:
                    glyph = "o"
                    color = self.color_ids["npc"]
                elif tile.landmark:
                    glyph = "*"
                    color = self.color_ids["headline"] | curses.A_BOLD
                self._write(y + draw_y, x + draw_x, glyph, color)

    def _draw_map_stats(self, y: int, x: int, height: int, width: int) -> None:
        if height <= 0:
            return
        world = self.engine.world
        selected = self.engine.selected_person()
        tile = world.tile_at(*selected.location)
        district = world.districts[tile.district_id]
        landmarks = world.landmarks_near(*selected.location, radius=8)
        summary = [
            f"Citizen tile: ({selected.location[0]}, {selected.location[1]}) {tile.terrain}/{tile.zone}",
            f"District: {district.name} | Wealth {district.wealth:0.2f} | Crime {district.crime_heat:0.2f}",
            f"Tile value {tile.property_value:0.0f} | Commute factor {tile.commute_factor:0.2f} | Occupants {len(tile.occupants)}",
            f"Nearby landmarks: {', '.join(landmarks[:3]) if landmarks else 'none'}",
        ]
        for idx, line in enumerate(summary[:height]):
            self._write(y + idx, x, line[: max(0, width - 1)], self.color_ids["panel"])

    # ------------------------------------------------------------------
    # Right column
    # ------------------------------------------------------------------
    def _draw_right_column(self, y: int, x: int, height: int, width: int) -> None:
        h1 = max(8, height // 4)
        h2 = max(8, height // 4)
        h3 = max(8, height // 4)
        h4 = max(6, height - h1 - h2 - h3)
        self._draw_metrics_panel(y, x, h1, width)
        self._draw_news_panel(y + h1, x, h2, width)
        self._draw_company_panel(y + h1 + h2, x, h3, width)
        self._draw_timeline_panel(y + h1 + h2 + h3, x, h4, width)

    def _draw_metrics_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._panel_box(y, x, height, width, " Systems ")
        metrics = self.engine.macro_metrics()
        lines = [
            f"Season         {self.engine.calendar.season()}",
            f"Weather        {self.engine.weather.condition}",
            f"Housing idx    {metrics['housing_index']:0.0f}",
            f"Crime idx      {metrics['crime_index']:0.2f}",
            f"Avg happiness  {metrics['avg_happiness']:0.2f}",
            f"Avg stress     {metrics['avg_stress']:0.2f}",
            f"Avg karma      {metrics['avg_karma']:0.2f}",
            f"Incarceration  {metrics['incarceration_rate']:0.3f}",
        ]
        lines.extend(self.engine.systems.stock_market.market_lines(limit=max(0, height - len(lines) - 2)))
        self._write_lines(y + 1, x + 1, width - 2, height - 2, lines)

    def _draw_news_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._panel_box(y, x, height, width, " News ")
        headlines = [item.headline for item in reversed(self.engine.news)]
        scroll = self.panel_scroll["news"]
        visible = headlines[scroll: scroll + max(1, height - 2)]
        if not visible:
            visible = ["No headlines yet."]
        self._write_lines(y + 1, x + 1, width - 2, height - 2, visible)

    def _draw_company_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._panel_box(y, x, height, width, " Companies ")
        visible = self.engine.world.company_summary_lines(limit=max(1, height - 2))
        if not visible:
            visible = ["No companies recorded yet."]
        self._write_lines(y + 1, x + 1, width - 2, height - 2, visible)

    def _draw_timeline_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._panel_box(y, x, height, width, " Timeline ")
        events = [event.title for event in reversed(self.engine.timeline)]
        scroll = self.panel_scroll["timeline"]
        visible = events[scroll: scroll + max(1, height - 2)]
        if not visible:
            visible = ["No systemic events logged yet."]
        self._write_lines(y + 1, x + 1, width - 2, height - 2, visible)

    # ------------------------------------------------------------------
    # Person summaries
    # ------------------------------------------------------------------
    def _person_summary_lines(self, person: Person, width: int, height: int) -> List[str]:
        job = person.job_title or "Unemployed"
        household = self.engine.population.household_for_person(person.person_id)
        home = household.home_building_id if household else None
        schedule = person.current_activity(self.engine.calendar.hour)
        bg = self.engine.systems.background_check(person)
        lines = [
            f"{person.full_name}",
            f"{person.gender}, age {person.age}, stage {person.life_stage}",
            f"Job: {job}",
            f"Salary: ${person.salary:0.0f} | Edu: {person.education_level}",
            f"Home building: {home if home else '-'}",
            f"Location: {person.location[0]},{person.location[1]}",
            f"Current activity: {schedule}",
            f"Energy {person.energy:0.2f}  Health {person.health:0.2f}",
            f"Happiness {person.happiness:0.2f}  Stress {person.stress:0.2f}",
            f"Motivation {person.motivation:0.2f}  Karma {person.hidden_karma:0.2f}",
            f"Reputation {person.reputation_public:0.2f}  BG check {bg:0.2f}",
            f"Cash ${person.cash:0.0f}  Bank ${person.bank_balance:0.0f}",
            f"Debt ${person.debt:0.0f}  Assets ${person.assets:0.0f}",
            f"Vehicle: {person.vehicle}",
            "Skills:",
        ]
        for key, value in sorted(person.skills.items(), key=lambda item: item[1], reverse=True)[:6]:
            lines.append(f"  {key[:12]:12} {value:0.2f}")
        if person.memories:
            lines.append("Recent memory:")
            lines.append(f"  {person.memories[-1].headline[: max(0, width - 4)]}")
        return lines[:height]

    # ------------------------------------------------------------------
    # Generic panel helpers
    # ------------------------------------------------------------------
    def _panel_box(self, y: int, x: int, height: int, width: int, title: str) -> None:
        if height < 2 or width < 2:
            return
        try:
            self.screen.addstr(y, x, "+" + "-" * max(0, width - 2) + "+", self.color_ids["accent"])
            for row in range(1, max(1, height - 1)):
                if y + row >= self.screen.getmaxyx()[0]:
                    break
                self._write(y + row, x, "|", self.color_ids["accent"])
                if width > 2:
                    self._write(y + row, x + 1, " " * max(0, width - 2), self.color_ids["panel"])
                self._write(y + row, x + width - 1, "|", self.color_ids["accent"])
            self.screen.addstr(y + height - 1, x, "+" + "-" * max(0, width - 2) + "+", self.color_ids["accent"])
            if width > len(title) + 4:
                self._write(y, x + 2, title[: width - 4], self.color_ids["headline"] | curses.A_BOLD)
        except curses.error:
            pass

    def _write_lines(self, y: int, x: int, width: int, height: int, lines: List[str]) -> None:
        if width <= 0 or height <= 0:
            return
        out_y = y
        for line in lines:
            wrapped = self._wrap(line, width)
            for chunk in wrapped:
                if out_y >= y + height:
                    return
                color = self._line_color(chunk)
                self._write(out_y, x, chunk[:width].ljust(width), color)
                out_y += 1

    def _wrap(self, text: str, width: int) -> List[str]:
        if width <= 0:
            return [""]
        return textwrap.wrap(text, width=width, replace_whitespace=False, drop_whitespace=False) or [text[:width]]

    def _line_color(self, text: str) -> int:
        lower = text.lower()
        if any(word in lower for word in ["bankruptcy", "convicted", "crime", "laid off", "meltdown", "failed"]):
            return self.color_ids["danger"]
        if any(word in lower for word in ["hired", "graduated", "goodwill", "refund", "promotion", "raise"]):
            return self.color_ids["good"]
        if any(word in lower for word in ["warning", "stress", "debt", "rent", "tax"]):
            return self.color_ids["warning"]
        return self.color_ids["panel"]

    def _fill_line(self, y: int, x: int, width: int, char: str, color: int) -> None:
        if width <= 0:
            return
        try:
            self.screen.addstr(y, x, char * max(0, width - 1), color)
        except curses.error:
            pass

    def _write(self, y: int, x: int, text: str, color: int) -> None:
        try:
            self.screen.addstr(y, x, text, color)
        except curses.error:
            pass

    # ------------------------------------------------------------------
    # Extra reporting surfaces kept here for extensibility
    # ------------------------------------------------------------------
    def mini_chart(self, values: List[float], width: int) -> str:
        if not values or width <= 0:
            return ""
        bars = " .:-=+*#%@"
        lo = min(values)
        hi = max(values)
        span = max(0.001, hi - lo)
        sample = values[-width:]
        chars = []
        for value in sample:
            idx = int(((value - lo) / span) * (len(bars) - 1))
            chars.append(bars[max(0, min(len(bars) - 1, idx))])
        return "".join(chars)

    def economy_chart_lines(self, width: int) -> List[str]:
        history = self.engine.world.economic_history
        if not history:
            return ["No economy history."]
        housing = [snap.housing_index for snap in history]
        crime = [snap.crime_index for snap in history]
        unemp = [snap.unemployment_rate for snap in history]
        return [
            f"Housing {self.mini_chart(housing, width - 8)}",
            f"Crime   {self.mini_chart(crime, width - 8)}",
            f"Unemp   {self.mini_chart(unemp, width - 8)}",
        ]

    def debug_population_lines(self, width: int) -> List[str]:
        lines = []
        for person in list(self.engine.population.people.values())[:12]:
            lines.append(
                f"{person.person_id:3d} {person.full_name[:16]:16} {person.location!s:>10} {person.current_activity(self.engine.calendar.hour)[:10]:10}"
            )
        return [line[:width] for line in lines]

    def district_lines(self, width: int) -> List[str]:
        return [line[:width] for line in self.engine.world.district_summary_lines(limit=12)]

    def company_lines(self, width: int) -> List[str]:
        return [line[:width] for line in self.engine.world.company_summary_lines(limit=12)]

    def player_schedule_lines(self, width: int) -> List[str]:
        player = self.engine.selected_person()
        lines = []
        for block in sorted(player.schedule.values(), key=lambda item: (item.start_hour, item.end_hour)):
            lines.append(f"{block.start_hour:02d}-{block.end_hour:02d} {block.activity}")
        return [line[:width] for line in lines]

    def player_memory_lines(self, width: int) -> List[str]:
        player = self.engine.selected_person()
        lines = [memory.headline for memory in player.memories[-10:]]
        return [line[:width] for line in reversed(lines)]

    def world_hotspot_lines(self, width: int) -> List[str]:
        world = self.engine.world
        districts = sorted(world.districts.values(), key=lambda district: district.crime_heat, reverse=True)[:5]
        lines = ["Crime Hotspots:"]
        for district in districts:
            lines.append(f"{district.name[:16]:16} {district.crime_heat:0.2f}")
        districts = sorted(world.districts.values(), key=lambda district: district.desirability, reverse=True)[:5]
        lines.append("Best Districts:")
        for district in districts:
            lines.append(f"{district.name[:16]:16} {district.desirability:0.2f}")
        return [line[:width] for line in lines]

    def transport_lines(self, width: int) -> List[str]:
        lines = []
        for line in self.engine.world.transit_lines.values():
            lines.append(f"{line.name[:16]:16} {line.line_type:8} {len(line.stops):2d} stops")
        return [line[:width] for line in lines]

    def weather_lines(self, width: int) -> List[str]:
        return [line[:width] for line in self.engine.weather_impact_lines()]

    def stock_lines(self, width: int) -> List[str]:
        return [line[:width] for line in self.engine.systems.stock_market.market_lines(limit=12)]

    def legal_lines(self, width: int) -> List[str]:
        lines = []
        for case in list(self.engine.systems.crime.cases.values())[-8:]:
            lines.append(
                f"Case {case.case_id:03d} {case.crime_type[:8]:8} sev {case.severity:0.2f} {case.verdict or 'open'}"
            )
        return [line[:width] for line in lines] or ["No legal cases."]

    def education_lines(self, width: int) -> List[str]:
        lines = []
        for program in list(self.engine.systems.education.programs.values())[:8]:
            lines.append(
                f"{program.name[:18]:18} {program.program_type:7} {len(program.enrolled_ids):2d}/{program.seats:2d}"
            )
        return [line[:width] for line in lines]

    def control_help_lines(self, width: int) -> List[str]:
        lines = [
            "Controls:",
            "Arrows/WASD pan map",
            "Space pause/resume",
            "+ / - adjust speed",
            "Tab cycle citizen",
            "C center on selected",
            "N/M scroll news",
            "T/G scroll timeline",
            "F5 save",
            "F9 load",
            "Q quit",
        ]
        return [line[:width] for line in lines]

    # The following method intentionally centralizes optional dashboard
    # content for future alternate layouts. Keeping this in the UI layer
    # avoids hard-coding a single presentation and makes it easier to
    # expose new systemic information without modifying the engine core.
    def alternate_dashboard_sections(self, width: int) -> List[Tuple[str, List[str]]]:
        return [
            ("Economy", self.economy_chart_lines(width)),
            ("Districts", self.district_lines(width)),
            ("Companies", self.company_lines(width)),
            ("Schedule", self.player_schedule_lines(width)),
            ("Memories", self.player_memory_lines(width)),
            ("Hotspots", self.world_hotspot_lines(width)),
            ("Transit", self.transport_lines(width)),
            ("Weather", self.weather_lines(width)),
            ("Stocks", self.stock_lines(width)),
            ("Law", self.legal_lines(width)),
            ("Education", self.education_lines(width)),
            ("Help", self.control_help_lines(width)),
        ]
