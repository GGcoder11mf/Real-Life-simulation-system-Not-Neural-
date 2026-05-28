"""
pygame_frontend.py

Standalone pygame renderer for the life simulation.
It reuses the existing SimulationEngine without altering simulation logic.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Dict, List, Sequence, Tuple

import pygame

from engine import SAVE_FILE, SimulationEngine


WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 920
TARGET_FPS = 60
MAX_SIM_STEPS_PER_FRAME = 2

MAP_BG = (14, 19, 26)
PANEL_BG = (18, 24, 32)
PANEL_BG_ALT = (23, 31, 42)
PANEL_BORDER = (72, 95, 122)
TEXT = (232, 237, 243)
TEXT_DIM = (164, 176, 192)
TEXT_WARN = (246, 205, 97)
TEXT_DANGER = (242, 111, 111)
TEXT_GOOD = (116, 213, 138)
ACCENT = (86, 184, 255)
ACCENT_2 = (255, 153, 84)
ACCENT_3 = (149, 218, 112)
TEXT_SOFT = (198, 208, 220)

TERRAIN_COLORS = {
    "water": (33, 92, 158),
    "park": (59, 132, 80),
    "rural": (137, 126, 87),
    "suburban": (134, 149, 166),
    "urban": (83, 102, 122),
    "industrial": (121, 98, 127),
    "road": (88, 91, 97),
    "rail": (153, 93, 65),
}

WEATHER_TINTS = {
    "clear": (255, 220, 180, 14),
    "cloudy": (180, 190, 205, 26),
    "rain": (100, 136, 190, 40),
    "storm": (65, 88, 128, 62),
    "fog": (195, 205, 210, 48),
    "heatwave": (255, 139, 76, 42),
    "cold_snap": (130, 176, 255, 36),
}

TEXTURE_ALIASES = {
    "road": "road",
    "rail": "rail",
    "water": "water",
    "park": "grass",
    "rural": "dirt",
    "suburban": "grass",
    "urban": "road",
    "industrial": "dirt",
}

BUILDING_TEXTURES = {
    "house": ["house1", "house2"],
    "apartment": ["apartment1", "apartment2"],
    "shop": ["shop1", "shop2"],
    "office": ["office1", "office2"],
    "factory": ["factory1"],
    "school": ["school1"],
    "college": ["college1"],
    "police": ["police1"],
    "court": ["court1"],
    "prison": ["prison1"],
    "hospital": ["hospital1"],
    "park_facility": ["park_facility1"],
    "station": ["station1"],
    "warehouse": ["warehouse1"],
}

BUILDING_COLORS = {
    "house": (217, 189, 130),
    "apartment": (200, 206, 215),
    "shop": (255, 195, 115),
    "office": (147, 188, 228),
    "factory": (166, 133, 128),
    "warehouse": (143, 126, 116),
    "school": (248, 214, 117),
    "college": (242, 163, 104),
    "police": (115, 168, 214),
    "hospital": (128, 211, 184),
    "station": (174, 171, 220),
    "park_facility": (122, 187, 108),
    "court": (190, 180, 148),
    "prison": (122, 122, 132),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PygameFrontend:
    def __init__(self, engine: SimulationEngine) -> None:
        self.engine = engine
        self.engine_lock = threading.RLock()
        self.sim_thread: threading.Thread | None = None
        self.sim_stop = threading.Event()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Life Sim Visual Frontend")
        self.clock = pygame.time.Clock()
        self.running = True
        self.status_message = "Arrows/WASD move. Space pause. Tab cycle citizen. C center. F5 save. F9 load. Q quit."
        self.target_fps = TARGET_FPS
        self.max_sim_steps_per_frame = MAX_SIM_STEPS_PER_FRAME
        self.frame_counter = 0
        self.news_scroll = 0
        self.timeline_scroll = 0
        self.last_step_time = time.monotonic()
        self.sim_accumulator = 0.0
        self.tile_zoom = 0
        self.camera_x = engine.camera_x
        self.camera_y = engine.camera_y
        self.font_ui = pygame.font.SysFont("segoeui", 18)
        self.font_small = pygame.font.SysFont("consolas", 15)
        self.font_tiny = pygame.font.SysFont("consolas", 13)
        self.font_title = pygame.font.SysFont("verdana", 28, bold=True)
        self.texture_dir = os.path.join(os.path.dirname(__file__), "textures")
        self.terrain_texture_cache: dict[str, pygame.Surface] = {}
        self.scaled_terrain_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.sprite_cache: dict[str, pygame.Surface] = {}
        self.scaled_sprite_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.person_sprite_ids: dict[int, str] = {}
        self.building_sprite_cache: dict[str, pygame.Surface] = {}
        self.building_texture_names: Dict[str, List[str]] = {}
        self.scaled_building_sprite_cache: dict[tuple[str, int], pygame.Surface] = {}
        self.people_sprite_pools: Dict[str, List[str]] = {"male": [], "female": [], "all": []}
        self.map_surface_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.shade_overlay_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.weather_overlay_cache: dict[tuple[int, int, str], pygame.Surface] = {}
        self.active_menu: str | None = None
        self.active_overlay: str | None = None
        self.cached_snapshot: dict | None = None
        self.load_textures()

    def run(self) -> None:
        self.start_simulation_worker()
        try:
            while self.running and self.engine_running():
                self.handle_events()
                self.draw()
                self.clock.tick(self.target_fps)
        finally:
            self.stop_simulation_worker()
            pygame.quit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                self.set_engine_running(False)
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.handle_click(event.pos)
                elif event.button == 4:
                    self.handle_wheel(-1, event.pos)
                elif event.button == 5:
                    self.handle_wheel(1, event.pos)

    def handle_keydown(self, key: int) -> None:
        if key in (pygame.K_q, pygame.K_ESCAPE):
            self.running = False
            self.set_engine_running(False)
        elif key == pygame.K_SPACE:
            with self.engine_lock:
                self.engine.toggle_pause()
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            with self.engine_lock:
                self.engine.change_speed(True)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            with self.engine_lock:
                self.engine.change_speed(False)
        elif key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
            self.tile_zoom = max(-4, self.tile_zoom - 1)
        elif key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
            self.tile_zoom = min(8, self.tile_zoom + 1)
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.move_camera(-2, 0)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.move_camera(2, 0)
        elif key in (pygame.K_UP, pygame.K_w):
            self.move_camera(0, -1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.move_camera(0, 1)
        elif key == pygame.K_c:
            self.center_on_selected_person()
        elif key == pygame.K_TAB:
            with self.engine_lock:
                self.engine.cycle_selected_person()
            self.active_overlay = "citizen"
        elif key == pygame.K_n:
            self.news_scroll += 1
            self.active_overlay = "news"
        elif key == pygame.K_m:
            self.news_scroll = max(0, self.news_scroll - 1)
            self.active_overlay = "news"
        elif key == pygame.K_t:
            self.timeline_scroll += 1
            self.active_overlay = "timeline"
        elif key == pygame.K_g:
            self.timeline_scroll = max(0, self.timeline_scroll - 1)
            self.active_overlay = "timeline"
        elif key == pygame.K_F1:
            self.active_overlay = None if self.active_overlay == "help" else "help"
        elif key == pygame.K_F5:
            with self.engine_lock:
                self.engine.save(SAVE_FILE)
                self.status_message = f"Saved simulation to {SAVE_FILE}"
        elif key == pygame.K_F9:
            try:
                with self.engine_lock:
                    self.engine = SimulationEngine.load(SAVE_FILE)
                    self.camera_x = self.engine.camera_x
                    self.camera_y = self.engine.camera_y
                self.status_message = f"Loaded simulation from {SAVE_FILE}"
            except Exception as exc:
                self.status_message = f"Load failed: {exc}"

    def handle_click(self, pos: Tuple[int, int]) -> None:
        layout = self.compute_layout()
        menu_data = self.build_menu(layout)
        if self.handle_menu_click(pos, menu_data):
            return
        overlay_rect = layout.get("overlay_rect")
        if self.active_overlay and overlay_rect and overlay_rect.collidepoint(pos):
            if pygame.Rect(overlay_rect.right - 40, overlay_rect.y + 10, 28, 24).collidepoint(pos):
                self.active_overlay = None
            return
        map_rect = layout["map_rect"]
        body = layout["map_body"]
        if not body.collidepoint(pos):
            self.active_menu = None
            return
        tile_size = layout["tile_size"]
        start_x = layout["start_x"]
        start_y = layout["start_y"]
        tx = start_x + int((pos[0] - body.x) // tile_size)
        ty = start_y + int((pos[1] - body.y) // tile_size)
        snapshot = self.cached_snapshot
        if not snapshot:
            return
        if tx < 0 or ty < 0 or tx >= snapshot["world_width"] or ty >= snapshot["world_height"]:
            return
        self.camera_x = tx
        self.camera_y = ty
        tile_info = snapshot["tile_lookup"].get((tx, ty))
        occupant_ids = tile_info["occupants"] if tile_info else ()
        if occupant_ids:
            with self.engine_lock:
                person = self.engine.population.people.get(occupant_ids[0])
                if person is not None:
                    self.engine.selected_person_id = person.person_id
                    self.status_message = f"Selected {person.full_name} at {tx},{ty}"
        else:
            if tile_info:
                self.status_message = f"Tile {tx},{ty} {tile_info['terrain']}/{tile_info['zone']}"
        self.active_overlay = "citizen"
        self.active_menu = None

    def handle_wheel(self, direction: int, pos: Tuple[int, int]) -> None:
        layout = self.compute_layout()
        overlay_rect = layout.get("overlay_rect")
        if self.active_overlay == "news" and overlay_rect and overlay_rect.collidepoint(pos):
            self.news_scroll = max(0, self.news_scroll + direction)
            return
        if self.active_overlay == "timeline" and overlay_rect and overlay_rect.collidepoint(pos):
            self.timeline_scroll = max(0, self.timeline_scroll + direction)
            return
        if layout["map_body"].collidepoint(pos):
            self.tile_zoom = max(-4, min(8, self.tile_zoom - direction))

    def compute_layout(self) -> dict:
        width, height = self.screen.get_size()
        header_h = 52
        footer_h = 40
        map_rect = pygame.Rect(12, header_h + 10, width - 24, height - header_h - footer_h - 32)
        map_body = pygame.Rect(map_rect.x + 14, map_rect.y + 46, map_rect.width - 28, map_rect.height - 58)
        base_tile_size = min(map_body.width // 36, map_body.height // 24)
        tile_size = max(8, min(28, base_tile_size + self.tile_zoom))
        tiles_w = max(12, map_body.width // tile_size)
        tiles_h = max(10, map_body.height // tile_size)
        half_w = tiles_w // 2
        half_h = tiles_h // 2
        world_width, world_height = self.world_size()
        start_x = max(0, min(world_width - tiles_w, self.camera_x - half_w))
        start_y = max(0, min(world_height - tiles_h, self.camera_y - half_h))
        overlay_w = min(420, max(320, width // 3))
        overlay_h = min(560, max(260, height - 140))
        overlay_rect = pygame.Rect(width - overlay_w - 18, header_h + 18, overlay_w, overlay_h)

        return {
            "header": pygame.Rect(12, 12, width - 24, header_h),
            "footer": pygame.Rect(12, height - footer_h - 12, width - 24, footer_h),
            "map_rect": map_rect,
            "map_body": map_body,
            "overlay_rect": overlay_rect,
            "tile_size": tile_size,
            "tiles_w": tiles_w,
            "tiles_h": tiles_h,
            "start_x": start_x,
            "start_y": start_y,
        }

    def draw(self) -> None:
        self.draw_background()
        layout = self.compute_layout()
        self.cached_snapshot = self.capture_snapshot(layout)
        if not self.cached_snapshot:
            self.draw_loading_state(layout)
            self.draw_menu_bar(layout["header"])
            self.draw_footer(layout["footer"])
            pygame.display.flip()
            self.frame_counter += 1
            return
        self.draw_header(layout["header"])
        self.draw_map(layout["map_rect"], layout)
        self.draw_overlay(layout)
        self.draw_menu_bar(layout["header"])
        self.draw_footer(layout["footer"])
        pygame.display.flip()
        self.frame_counter += 1

    def draw_loading_state(self, layout: dict) -> None:
        self.draw_header(layout["header"])
        body = self.draw_panel(layout["map_rect"], "City Map", alt=True)
        glass = pygame.Surface(body.size, pygame.SRCALPHA)
        glass.fill((10, 14, 20, 220))
        self.screen.blit(glass, body.topleft)
        self.blit_text(self.font_ui, "Simulation busy, reusing last state...", (body.x + 24, body.y + 24), TEXT)

    def start_simulation_worker(self) -> None:
        self.sim_stop.clear()
        self.sim_thread = threading.Thread(target=self.simulation_loop, name="sim-worker", daemon=True)
        self.sim_thread.start()

    def stop_simulation_worker(self) -> None:
        self.sim_stop.set()
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=1.0)

    def simulation_loop(self) -> None:
        last_step = time.monotonic()
        while not self.sim_stop.is_set():
            with self.engine_lock:
                running = self.engine.running
                paused = self.engine.paused
                tick_duration = self.engine.tick_duration
            if not running:
                break
            if paused:
                last_step = time.monotonic()
                time.sleep(0.01)
                continue
            now = time.monotonic()
            elapsed = now - last_step
            if elapsed < tick_duration:
                time.sleep(min(0.005, tick_duration - elapsed))
                continue
            with self.engine_lock:
                if self.engine.running and not self.engine.paused:
                    self.engine.step()
            last_step = now

    def engine_running(self) -> bool:
        with self.engine_lock:
            return self.engine.running

    def set_engine_running(self, running: bool) -> None:
        with self.engine_lock:
            self.engine.running = running

    def world_size(self) -> tuple[int, int]:
        snapshot = self.cached_snapshot
        if snapshot:
            return snapshot["world_width"], snapshot["world_height"]
        with self.engine_lock:
            return self.engine.world.width, self.engine.world.height

    def move_camera(self, dx: int, dy: int) -> None:
        world_width, world_height = self.world_size()
        self.camera_x = max(0, min(world_width - 1, self.camera_x + dx))
        self.camera_y = max(0, min(world_height - 1, self.camera_y + dy))

    def center_on_selected_person(self) -> None:
        snapshot = self.cached_snapshot
        if snapshot:
            self.camera_x, self.camera_y = snapshot["selected_location"]
            return
        with self.engine_lock:
            self.engine.center_on_selected_person()
            self.camera_x = self.engine.camera_x
            self.camera_y = self.engine.camera_y

    def capture_snapshot(self, layout: dict) -> dict | None:
        if not self.engine_lock.acquire(blocking=False):
            return self.cached_snapshot
        try:
            engine = self.engine
            world = engine.world
            selected = engine.selected_person()
            metrics = engine.macro_metrics()
            start_x = layout["start_x"]
            start_y = layout["start_y"]
            tiles_w = layout["tiles_w"]
            tiles_h = layout["tiles_h"]
            visible_tiles = []
            tile_lookup = {}
            for dy in range(tiles_h):
                world_y = start_y + dy
                if world_y >= world.height:
                    break
                for dx in range(tiles_w):
                    world_x = start_x + dx
                    if world_x >= world.width:
                        break
                    tile = world.tile_at(world_x, world_y)
                    building_type = None
                    if tile.building_id is not None:
                        building = world.buildings.get(tile.building_id)
                        building_type = building.building_type if building is not None else None
                    info = {
                        "x": world_x,
                        "y": world_y,
                        "terrain_key": tile.color_key(),
                        "terrain": tile.terrain,
                        "elevation": tile.elevation,
                        "zone": tile.zone,
                        "landmark": tile.landmark,
                        "building_id": tile.building_id,
                        "building_type": building_type,
                        "occupants": tuple(tile.occupants),
                        "property_value": tile.property_value,
                        "district_id": tile.district_id,
                    }
                    visible_tiles.append(info)
                    tile_lookup[(world_x, world_y)] = info
            relationship_lines = engine.population.relationship_lines(selected.person_id, limit=16)
            if not relationship_lines:
                relationship_lines = ["No meaningful ties recorded."]
            company_lines = engine.world.company_summary_lines(limit=9) or ["No companies recorded yet."]
            news_lines = [item.headline for item in reversed(engine.news)][self.news_scroll:self.news_scroll + 9] or ["No headlines yet."]
            timeline_lines = [event.title for event in reversed(engine.timeline)][self.timeline_scroll:self.timeline_scroll + 8] or ["No systemic events logged yet."]
            household = engine.population.household_for_person(selected.person_id)
            home = household.home_building_id if household else "-"
            person_lines = [
                selected.full_name,
                f"{selected.gender}, age {selected.age}, stage {selected.life_stage}",
                f"Job: {selected.job_title or 'Unemployed'}",
                f"Salary ${selected.salary:.0f}  |  Education {selected.education_level}",
                f"Home building {home}  |  Vehicle {selected.vehicle}",
                f"Location {selected.location[0]}, {selected.location[1]}",
                f"Activity: {selected.current_activity(engine.calendar.hour)}",
                f"Destination: {selected.destination[0]}, {selected.destination[1]}",
                f"Energy {selected.energy:.2f}  Health {selected.health:.2f}",
                f"Happiness {selected.happiness:.2f}  Stress {selected.stress:.2f}",
                f"Motivation {selected.motivation:.2f}  Karma {selected.hidden_karma:.2f}",
                f"Reputation {selected.reputation_public:.2f}",
                f"Cash ${selected.cash:.0f}  Bank ${selected.bank_balance:.0f}",
                f"Debt ${selected.debt:.0f}  Assets ${selected.assets:.0f}",
                "Top skills:",
            ]
            for key, value in sorted(selected.skills.items(), key=lambda item: item[1], reverse=True)[:5]:
                person_lines.append(f"  {key[:14]:14} {value:.2f}")
            if selected.memories:
                person_lines.append("Recent memory:")
                person_lines.append(f"  {selected.memories[-1].headline}")
            selected_tile = world.tile_at(*selected.location)
            district = world.districts[selected_tile.district_id]
            return {
                "world_width": world.width,
                "world_height": world.height,
                "calendar_label": engine.calendar.label(),
                "calendar_hour": engine.calendar.hour,
                "season": engine.calendar.season(),
                "weather_summary": engine.weather.summary(),
                "weather_condition": engine.weather.condition,
                "selected_name": selected.full_name,
                "selected_activity": selected.current_activity(engine.calendar.hour),
                "selected_stress": selected.stress,
                "selected_location": selected.location,
                "selected_tile": {
                    "terrain": selected_tile.terrain,
                    "zone": selected_tile.zone,
                    "occupants": len(selected_tile.occupants),
                    "property_value": selected_tile.property_value,
                },
                "district": {
                    "name": district.name,
                    "wealth": district.wealth,
                    "crime_heat": district.crime_heat,
                    "transit_score": district.transit_score,
                },
                "metrics": metrics,
                "paused": engine.paused,
                "tick_counter": engine.tick_counter,
                "population_count": len(engine.population.people),
                "visible_tiles": visible_tiles,
                "tile_lookup": tile_lookup,
                "person_panel_lines": person_lines,
                "relationship_lines": relationship_lines,
                "systems_lines": [
                    f"Season: {engine.calendar.season()}",
                    f"Weather: {engine.weather.condition}",
                    f"Housing index: {metrics['housing_index']:.0f}",
                    f"Crime index: {metrics['crime_index']:.2f}",
                    f"Avg happiness: {metrics['avg_happiness']:.2f}",
                    f"Avg stress: {metrics['avg_stress']:.2f}",
                    f"Avg karma: {metrics['avg_karma']:.2f}",
                    f"Incarceration: {metrics['incarceration_rate']:.3f}",
                    *engine.systems.stock_market.market_lines(limit=4),
                ],
                "news_lines": news_lines,
                "company_lines": company_lines,
                "timeline_lines": timeline_lines,
            }
        finally:
            self.engine_lock.release()

    def draw_background(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill((10, 14, 20))
        for i in range(0, height, 3):
            blend = i / max(1, height)
            color = (
                int(14 + 12 * blend),
                int(20 + 18 * blend),
                int(28 + 24 * blend),
            )
            pygame.draw.line(self.screen, color, (0, i), (width, i))
        pygame.draw.circle(self.screen, (32, 55, 84), (width - 160, 110), 180)
        pygame.draw.circle(self.screen, (62, 45, 33), (120, height - 120), 140)

    def draw_panel(self, rect: pygame.Rect, title: str, alt: bool = False) -> pygame.Rect:
        bg = PANEL_BG_ALT if alt else PANEL_BG
        pygame.draw.rect(self.screen, bg, rect, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=2, border_radius=14)
        title_surf = self.font_ui.render(title, True, TEXT)
        self.screen.blit(title_surf, (rect.x + 14, rect.y + 10))
        pygame.draw.line(self.screen, ACCENT, (rect.x + 12, rect.y + 38), (rect.right - 12, rect.y + 38), 2)
        return pygame.Rect(rect.x + 14, rect.y + 46, rect.width - 28, rect.height - 58)

    def draw_header(self, rect: pygame.Rect) -> None:
        snapshot = self.cached_snapshot
        if not snapshot:
            return
        pygame.draw.rect(self.screen, (9, 13, 19), rect, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=2, border_radius=14)
        left = rect.x + 14
        self.blit_text(self.font_ui, "Life Sim", (left, rect.y + 14), TEXT)
        self.blit_text(self.font_small, f"{snapshot['calendar_label']}  |  {snapshot['weather_summary']}", (left + 210, rect.y + 8), TEXT)
        subtitle = f"{snapshot['selected_name']}  |  {snapshot['selected_activity']}  |  Stress {snapshot['selected_stress']:.2f}  |  Unemployment {snapshot['metrics']['unemployment']:.2f}"
        self.blit_text(self.font_tiny, subtitle, (left + 210, rect.y + 29), TEXT_DIM)

    def draw_footer(self, rect: pygame.Rect) -> None:
        snapshot = self.cached_snapshot
        if not snapshot:
            return
        status = self.status_message
        if snapshot["paused"]:
            status += "  [PAUSED]"
        pygame.draw.rect(self.screen, (9, 13, 19), rect, border_radius=12)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=1, border_radius=12)
        self.blit_text(self.font_small, status, (rect.x + 14, rect.y + 7), TEXT)
        info = f"Zoom {self.tile_zoom:+d}  |  Tick {snapshot['tick_counter']}  |  Population {snapshot['population_count']}  |  F1 help"
        self.blit_text(self.font_tiny, info, (rect.right - 310, rect.y + 10), TEXT_DIM)

    def draw_person_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Citizen")
        self.draw_text_block(body, self.cached_snapshot["person_panel_lines"])

    def draw_relationship_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Relationships")
        self.draw_text_block(body, self.cached_snapshot["relationship_lines"])

    def draw_map(self, rect: pygame.Rect, layout: dict) -> None:
        snapshot = self.cached_snapshot
        body = self.draw_panel(rect, "City Map", alt=True)
        tile_size = layout["tile_size"]
        tiles_w = layout["tiles_w"]
        tiles_h = layout["tiles_h"]

        map_surface = self.get_map_surface(tiles_w * tile_size, tiles_h * tile_size)
        map_surface.fill(MAP_BG)
        pulse = (math.sin(time.monotonic() * 4.0) + 1.0) * 0.5

        for tile in snapshot["visible_tiles"]:
            dx = tile["x"] - layout["start_x"]
            dy = tile["y"] - layout["start_y"]
            color = TERRAIN_COLORS.get(tile["terrain_key"], TERRAIN_COLORS["urban"])
            shade = int((tile["elevation"] - 0.5) * 24)
            final = tuple(int(clamp(c + shade, 0, 255)) for c in color)
            tile_rect = pygame.Rect(dx * tile_size, dy * tile_size, tile_size, tile_size)
            terrain_key = tile["terrain_key"]
            rotation = self.terrain_rotation(snapshot["tile_lookup"], tile["x"], tile["y"], terrain_key)
            terrain_texture = self.get_scaled_terrain_texture(terrain_key, tile_size, rotation)
            if terrain_texture is not None:
                map_surface.blit(terrain_texture, tile_rect.topleft)
                if shade != 0:
                    shade_overlay = self.get_shade_overlay(tile_size, shade)
                    map_surface.blit(shade_overlay, tile_rect.topleft)
            else:
                final = tuple(int(clamp(c + shade, 0, 255)) for c in color)
                pygame.draw.rect(map_surface, final, tile_rect)

            if tile["building_id"] is not None and tile_size >= 10 and tile["building_type"] is not None:
                self.draw_building_overlay(map_surface, tile_rect, tile["building_type"], tile_size, tile["building_id"])

            if tile["zone"] in {"commercial", "mixed_use"} and tile_size >= 10:
                pygame.draw.rect(map_surface, (255, 224, 138, 44), tile_rect.inflate(-tile_size // 3, -tile_size // 3), border_radius=3)
            if tile["landmark"] and tile_size >= 12:
                pygame.draw.circle(map_surface, ACCENT_2, tile_rect.center, max(2, tile_size // 4))
            if tile["occupants"]:
                self.draw_people_overlay(map_surface, tile_rect, tile["occupants"], tile_size)
            if (tile["x"], tile["y"]) == snapshot["selected_location"]:
                radius = max(4, int(tile_size * (0.32 + pulse * 0.18)))
                pygame.draw.circle(map_surface, (255, 234, 122), tile_rect.center, radius)
                pygame.draw.circle(map_surface, (255, 255, 255), tile_rect.center, max(2, radius // 2))

        self.screen.blit(map_surface, body.topleft)
        self.draw_weather_overlay(body)
        self.draw_map_info(body, layout)

    def draw_weather_overlay(self, rect: pygame.Rect) -> None:
        snapshot = self.cached_snapshot
        tint = WEATHER_TINTS.get(snapshot["weather_condition"]) if snapshot else None
        if not tint:
            return
        overlay = self.get_weather_overlay(rect.size, snapshot["weather_condition"], tint)
        self.screen.blit(overlay, rect.topleft)

    def draw_map_info(self, rect: pygame.Rect, layout: dict) -> None:
        snapshot = self.cached_snapshot
        info_h = 74
        info_rect = pygame.Rect(rect.x + 14, rect.bottom - info_h - 14, min(rect.width - 28, 560), info_h)
        glass = pygame.Surface(info_rect.size, pygame.SRCALPHA)
        glass.fill((8, 12, 18, 170))
        self.screen.blit(glass, info_rect.topleft)
        pygame.draw.rect(self.screen, (255, 255, 255, 28), info_rect, width=1, border_radius=10)
        lines = [
            f"Tile {snapshot['selected_location'][0]}, {snapshot['selected_location'][1]}  |  {snapshot['selected_tile']['terrain']}/{snapshot['selected_tile']['zone']}  |  Occupants {snapshot['selected_tile']['occupants']}  |  Value ${snapshot['selected_tile']['property_value']:.0f}",
            f"District {snapshot['district']['name']}  |  Wealth {snapshot['district']['wealth']:.2f}  |  Crime {snapshot['district']['crime_heat']:.2f}  |  Transit {snapshot['district']['transit_score']:.2f}",
            f"View origin {layout['start_x']}, {layout['start_y']}  |  Tile size {layout['tile_size']} px  |  Selected {snapshot['selected_activity']}",
        ]
        self.draw_text_block(info_rect.inflate(-12, -10), lines, line_height=20)

    def draw_overlay(self, layout: dict) -> None:
        if not self.active_overlay:
            return
        overlay_rect = layout["overlay_rect"]
        if self.active_overlay == "citizen":
            self.draw_person_panel(overlay_rect)
        elif self.active_overlay == "relationships":
            self.draw_relationship_panel(overlay_rect)
        elif self.active_overlay == "systems":
            self.draw_metrics_panel(overlay_rect)
        elif self.active_overlay == "news":
            self.draw_news_panel(overlay_rect)
        elif self.active_overlay == "companies":
            self.draw_company_panel(overlay_rect)
        elif self.active_overlay == "timeline":
            self.draw_timeline_panel(overlay_rect)
        elif self.active_overlay == "help":
            self.draw_help_panel(overlay_rect)
        close_rect = pygame.Rect(overlay_rect.right - 40, overlay_rect.y + 10, 28, 24)
        pygame.draw.rect(self.screen, (33, 41, 54), close_rect, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, close_rect, width=1, border_radius=6)
        self.blit_text(self.font_small, "X", (close_rect.x + 8, close_rect.y + 2), TEXT)

    def draw_help_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Help")
        lines = [
            "Click map: select citizen or tile",
            "Mouse wheel on map: zoom in/out",
            "WASD / arrows: move camera",
            "Tab: cycle citizen and open citizen panel",
            "C: center on selected citizen",
            "Space: pause",
            "F5: save",
            "F9: load",
            "Menus: open panels and simulation actions",
            "F1: toggle this help panel",
        ]
        self.draw_text_block(body, lines)

    def draw_metrics_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Systems")
        self.draw_text_block(body, self.cached_snapshot["systems_lines"])

    def draw_news_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "News")
        self.draw_text_block(body, self.cached_snapshot["news_lines"])

    def draw_company_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Companies")
        self.draw_text_block(body, self.cached_snapshot["company_lines"])

    def draw_timeline_panel(self, rect: pygame.Rect) -> None:
        body = self.draw_panel(rect, "Timeline")
        self.draw_text_block(body, self.cached_snapshot["timeline_lines"])

    def menu_definitions(self) -> List[tuple[str, List[tuple[str, str]]]]:
        return [
            ("View", [
                ("Citizen", "overlay:citizen"),
                ("Relationships", "overlay:relationships"),
                ("Systems", "overlay:systems"),
                ("News", "overlay:news"),
                ("Companies", "overlay:companies"),
                ("Timeline", "overlay:timeline"),
                ("Help", "overlay:help"),
                ("Hide Panel", "overlay:none"),
            ]),
            ("Map", [
                ("Zoom In", "map:zoom_in"),
                ("Zoom Out", "map:zoom_out"),
                ("Center Citizen", "map:center"),
            ]),
            ("Sim", [
                ("Pause/Resume", "sim:pause"),
                ("Faster", "sim:faster"),
                ("Slower", "sim:slower"),
                ("Save", "sim:save"),
                ("Load", "sim:load"),
            ]),
        ]

    def build_menu(self, layout: dict) -> dict:
        header = layout["header"]
        x = header.x + 86
        buttons: List[tuple[str, pygame.Rect]] = []
        widths = {"View": 68, "Map": 62, "Sim": 58}
        for label, _ in self.menu_definitions():
            rect = pygame.Rect(x, header.y + 12, widths.get(label, 64), 28)
            buttons.append((label, rect))
            x += rect.width + 8
        dropdown_entries: List[tuple[str, pygame.Rect, str]] = []
        if self.active_menu:
            for label, rect in buttons:
                if label != self.active_menu:
                    continue
                items = next(entries for menu_label, entries in self.menu_definitions() if menu_label == label)
                menu_rect = pygame.Rect(rect.x, rect.bottom + 4, 184, len(items) * 28 + 8)
                item_y = menu_rect.y + 4
                for item_label, action in items:
                    dropdown_entries.append((item_label, pygame.Rect(menu_rect.x + 4, item_y, menu_rect.width - 8, 24), action))
                    item_y += 28
                return {"buttons": buttons, "menu_rect": menu_rect, "entries": dropdown_entries}
        return {"buttons": buttons, "menu_rect": None, "entries": dropdown_entries}

    def draw_menu_bar(self, rect: pygame.Rect) -> None:
        menu_data = self.build_menu({"header": rect})
        for label, button_rect in menu_data["buttons"]:
            active = self.active_menu == label
            bg = (24, 34, 46) if active else (16, 22, 30)
            pygame.draw.rect(self.screen, bg, button_rect, border_radius=8)
            pygame.draw.rect(self.screen, ACCENT if active else PANEL_BORDER, button_rect, width=1, border_radius=8)
            self.blit_text(self.font_small, label, (button_rect.x + 12, button_rect.y + 5), TEXT)
        menu_rect = menu_data["menu_rect"]
        if menu_rect:
            pygame.draw.rect(self.screen, (14, 19, 26), menu_rect, border_radius=10)
            pygame.draw.rect(self.screen, PANEL_BORDER, menu_rect, width=1, border_radius=10)
            for label, item_rect, _ in menu_data["entries"]:
                pygame.draw.rect(self.screen, (22, 30, 40), item_rect, border_radius=6)
                self.blit_text(self.font_small, label, (item_rect.x + 10, item_rect.y + 3), TEXT)

    def handle_menu_click(self, pos: Tuple[int, int], menu_data: dict) -> bool:
        for label, button_rect in menu_data["buttons"]:
            if button_rect.collidepoint(pos):
                self.active_menu = None if self.active_menu == label else label
                return True
        if menu_data["menu_rect"] and menu_data["menu_rect"].collidepoint(pos):
            for _, item_rect, action in menu_data["entries"]:
                if item_rect.collidepoint(pos):
                    self.execute_menu_action(action)
                    self.active_menu = None
                    return True
        return False

    def execute_menu_action(self, action: str) -> None:
        if action.startswith("overlay:"):
            overlay = action.split(":", 1)[1]
            self.active_overlay = None if overlay == "none" else overlay
            return
        if action == "map:zoom_in":
            self.tile_zoom = min(8, self.tile_zoom + 1)
        elif action == "map:zoom_out":
            self.tile_zoom = max(-4, self.tile_zoom - 1)
        elif action == "map:center":
            self.center_on_selected_person()
        elif action == "sim:pause":
            with self.engine_lock:
                self.engine.toggle_pause()
        elif action == "sim:faster":
            with self.engine_lock:
                self.engine.change_speed(True)
        elif action == "sim:slower":
            with self.engine_lock:
                self.engine.change_speed(False)
        elif action == "sim:save":
            with self.engine_lock:
                self.engine.save(SAVE_FILE)
                self.status_message = f"Saved simulation to {SAVE_FILE}"
        elif action == "sim:load":
            try:
                with self.engine_lock:
                    self.engine = SimulationEngine.load(SAVE_FILE)
                    self.camera_x = self.engine.camera_x
                    self.camera_y = self.engine.camera_y
                self.status_message = f"Loaded simulation from {SAVE_FILE}"
            except Exception as exc:
                self.status_message = f"Load failed: {exc}"

    def load_textures(self) -> None:
        if not os.path.isdir(self.texture_dir):
            return
        for terrain_key, filename in TEXTURE_ALIASES.items():
            surface = self.load_surface_if_exists(os.path.join(self.texture_dir, f"{filename}.png"))
            if surface is not None:
                self.terrain_texture_cache[terrain_key] = surface
        for sprite_name in [
            "citizen_male1",
            "citizen_male2",
            "citizen_male3",
            "citizen_female1",
            "citizen_female2",
            "citizen_female3",
        ]:
            surface = self.load_surface_if_exists(os.path.join(self.texture_dir, f"{sprite_name}.png"), alpha=True)
            if surface is not None:
                self.sprite_cache[sprite_name] = surface
        self.people_sprite_pools = {
            "male": sorted(name for name in self.sprite_cache if "male" in name),
            "female": sorted(name for name in self.sprite_cache if "female" in name),
            "all": sorted(self.sprite_cache),
        }
        for building_type, sprite_names in BUILDING_TEXTURES.items():
            loaded_variants: List[str] = []
            for sprite_name in sprite_names:
                surface = self.load_surface_if_exists(os.path.join(self.texture_dir, f"{sprite_name}.png"), alpha=True)
                if surface is None:
                    continue
                self.building_sprite_cache[sprite_name] = surface
                loaded_variants.append(sprite_name)
            if loaded_variants:
                self.building_texture_names[building_type] = loaded_variants

    def load_surface_if_exists(self, path: str, alpha: bool = False) -> pygame.Surface | None:
        if not os.path.exists(path):
            return None
        try:
            image = pygame.image.load(path)
            return image.convert_alpha() if alpha else image.convert()
        except pygame.error:
            return None

    def get_scaled_terrain_texture(self, terrain_key: str, tile_size: int, rotation: int = 0) -> pygame.Surface | None:
        base = self.terrain_texture_cache.get(terrain_key)
        if base is None:
            return None
        cache_key = (terrain_key, tile_size, rotation % 360)
        if cache_key not in self.scaled_terrain_cache:
            scaled = pygame.transform.smoothscale(base, (tile_size, tile_size))
            if rotation % 360:
                scaled = pygame.transform.rotate(scaled, rotation % 360)
            self.scaled_terrain_cache[cache_key] = scaled
        return self.scaled_terrain_cache[cache_key]

    def terrain_rotation(self, tile_lookup: dict, x: int, y: int, terrain_key: str) -> int:
        if terrain_key not in {"road", "rail"}:
            return 0
        up = tile_lookup.get((x, y - 1), {}).get("terrain_key") == terrain_key
        down = tile_lookup.get((x, y + 1), {}).get("terrain_key") == terrain_key
        left = tile_lookup.get((x - 1, y), {}).get("terrain_key") == terrain_key
        right = tile_lookup.get((x + 1, y), {}).get("terrain_key") == terrain_key
        vertical = up or down
        horizontal = left or right
        if vertical and not horizontal:
            return 90
        if vertical and horizontal:
            return 90 if (up and down and not (left and right)) else 0
        return 0

    def get_map_surface(self, width: int, height: int) -> pygame.Surface:
        cache_key = (width, height)
        if cache_key not in self.map_surface_cache:
            self.map_surface_cache[cache_key] = pygame.Surface(cache_key, pygame.SRCALPHA)
        return self.map_surface_cache[cache_key]

    def get_shade_overlay(self, tile_size: int, shade: int) -> pygame.Surface:
        alpha = min(48, abs(shade) * 2)
        cache_key = (tile_size, shade)
        if cache_key not in self.shade_overlay_cache:
            overlay = pygame.Surface((tile_size, tile_size), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha) if shade > 0 else (0, 0, 0, alpha))
            self.shade_overlay_cache[cache_key] = overlay
        return self.shade_overlay_cache[cache_key]

    def get_weather_overlay(
        self,
        size: Tuple[int, int],
        condition: str,
        tint: Tuple[int, int, int, int],
    ) -> pygame.Surface:
        cache_key = (size[0], size[1], condition)
        if cache_key not in self.weather_overlay_cache:
            overlay = pygame.Surface(size, pygame.SRCALPHA)
            overlay.fill(tint)
            self.weather_overlay_cache[cache_key] = overlay
        return self.weather_overlay_cache[cache_key]

    def get_person_sprite(self, person_id: int, tile_size: int) -> pygame.Surface | None:
        sprite_id = self.person_sprite_ids.get(person_id)
        if sprite_id is None:
            if person_id % 2:
                pool = self.people_sprite_pools["male"]
            else:
                pool = self.people_sprite_pools["female"]
            if not pool:
                pool = self.people_sprite_pools["all"]
            if not pool:
                return None
            sprite_id = pool[person_id % len(pool)]
            self.person_sprite_ids[person_id] = sprite_id
        cache_key = (sprite_id, tile_size)
        if cache_key not in self.scaled_sprite_cache:
            source = self.sprite_cache[sprite_id]
            side = max(8, int(tile_size * 0.9))
            self.scaled_sprite_cache[cache_key] = pygame.transform.smoothscale(source, (side, side))
        return self.scaled_sprite_cache[cache_key]

    def get_building_sprite(self, building_type: str, building_id: int, tile_size: int) -> pygame.Surface | None:
        variants = self.building_texture_names.get(building_type)
        if not variants:
            return None
        sprite_id = variants[building_id % len(variants)]
        cache_key = (sprite_id, tile_size)
        if cache_key not in self.scaled_building_sprite_cache:
            source = self.building_sprite_cache[sprite_id]
            side = max(8, int(tile_size * 0.95))
            self.scaled_building_sprite_cache[cache_key] = pygame.transform.smoothscale(source, (side, side))
        return self.scaled_building_sprite_cache[cache_key]

    def draw_building_overlay(self, surface: pygame.Surface, tile_rect: pygame.Rect, building_type: str, tile_size: int, building_id: int) -> None:
        sprite = self.get_building_sprite(building_type, building_id, tile_size)
        if sprite is not None:
            sprite_rect = sprite.get_rect(center=(tile_rect.centerx, tile_rect.centery))
            surface.blit(sprite, sprite_rect.topleft)
            return
        color = BUILDING_COLORS.get(building_type, (215, 215, 215))
        inset = max(1, tile_size // 5)
        base_rect = tile_rect.inflate(-inset * 2, -inset * 2)
        base_rect.height = max(4, int(base_rect.height * 0.62))
        base_rect.bottom = tile_rect.bottom - max(1, tile_size // 8)
        roof = [
            (base_rect.left, base_rect.top),
            (base_rect.centerx, base_rect.top - max(2, tile_size // 5)),
            (base_rect.right, base_rect.top),
        ]
        pygame.draw.rect(surface, color, base_rect, border_radius=max(2, tile_size // 8))
        pygame.draw.polygon(surface, tuple(max(0, c - 28) for c in color), roof)
        pygame.draw.rect(surface, (30, 36, 44), base_rect, width=1, border_radius=max(2, tile_size // 8))

    def draw_people_overlay(self, surface: pygame.Surface, tile_rect: pygame.Rect, occupants: Sequence[int], tile_size: int) -> None:
        lead_id = occupants[0]
        sprite = self.get_person_sprite(lead_id, tile_size)
        if sprite is not None and tile_size >= 14:
            sprite_rect = sprite.get_rect(center=(tile_rect.centerx, tile_rect.centery + max(0, tile_size // 18)))
            surface.blit(sprite, sprite_rect.topleft)
        else:
            pygame.draw.circle(surface, (238, 243, 250), tile_rect.center, max(2, tile_size // 5))
        if len(occupants) > 1 and tile_size >= 12:
            badge_rect = pygame.Rect(0, 0, max(10, tile_size // 2 + 4), max(10, tile_size // 2))
            badge_rect.topright = (tile_rect.right - 1, tile_rect.top + 1)
            pygame.draw.rect(surface, (12, 18, 26), badge_rect, border_radius=badge_rect.height // 2)
            pygame.draw.rect(surface, ACCENT_3, badge_rect, width=1, border_radius=badge_rect.height // 2)
            count_text = self.font_tiny.render(str(min(99, len(occupants))), True, TEXT)
            text_rect = count_text.get_rect(center=badge_rect.center)
            surface.blit(count_text, text_rect.topleft)

    def draw_text_block(self, rect: pygame.Rect, lines: List[str], line_height: int = 22) -> None:
        y = rect.y
        max_lines = max(1, rect.height // line_height)
        for line in lines[:max_lines]:
            color = self.line_color(line)
            rendered = self.font_small.render(self.fit_text(line, rect.width, self.font_small), True, color)
            self.screen.blit(rendered, (rect.x, y))
            y += line_height

    def line_color(self, text: str) -> Tuple[int, int, int]:
        lower = text.lower()
        if any(word in lower for word in ["bankruptcy", "convicted", "crime", "laid off", "meltdown", "failed"]):
            return TEXT_DANGER
        if any(word in lower for word in ["hired", "graduated", "goodwill", "refund", "promotion", "raise"]):
            return TEXT_GOOD
        if any(word in lower for word in ["warning", "stress", "debt", "rent", "tax"]):
            return TEXT_WARN
        return TEXT

    def fit_text(self, text: str, width: int, font: pygame.font.Font) -> str:
        if font.size(text)[0] <= width:
            return text
        trimmed = text
        while trimmed and font.size(trimmed + "...")[0] > width:
            trimmed = trimmed[:-1]
        return trimmed + "..." if trimmed else ""

    def blit_text(self, font: pygame.font.Font, text: str, pos: Tuple[int, int], color: Tuple[int, int, int]) -> None:
        self.screen.blit(font.render(text, True, color), pos)


def load_engine() -> SimulationEngine:
    return SimulationEngine()


def main() -> None:
    pygame.init()
    pygame.font.init()
    engine = load_engine()
    frontend = PygameFrontend(engine)
    frontend.run()


if __name__ == "__main__":
    main()
