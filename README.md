# Life Sim — Procedural Society Simulation Engine

A deeply interconnected city-life simulation where hundreds of autonomous citizens live, work, study, commit crimes, raise families, invest in stocks, and interact with one another — all driven by intersecting economic, legal, social, and psychological systems. The world is procedurally generated from a seed, and every citizen is a first-class simulation agent with their own genetics, personality, memories, relationships, and daily schedule.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Module Breakdown](#module-breakdown)
- [Simulation Systems](#simulation-systems)
- [Getting Started](#getting-started)
- [Controls](#controls)
- [Save / Load](#save--load)
- [Design Philosophy](#design-philosophy)
- [Extending the Simulation](#extending-the-simulation)
- [Dependencies](#dependencies)
- [License](#license)

---

## Overview

Life Sim is not a game with a win condition — it is an open-ended sandbox engine that models the emergent behaviour of a procedural city. Every citizen wakes up, follows a schedule, commutes to work, socialises, pays taxes, and responds to stress, debt, reputation, and the law. Systems reinforce one another: high unemployment drives crime, crime drives policing, policing drives incarceration, incarceration drives debt and reputation damage, and those in turn feed back into employment difficulty and further stress.

The simulation runs hour-by-hour with a full daily cycle that processes finance, hiring, education, crime, courts, and macro-level economic shifts. A built-in event engine watches cross-system state and injects consequences — recessions, weather disruptions, stress spirals, and community goodwill — back into the world.

Two frontends are provided:
- A **curses-based terminal UI** for lightweight, SSH-friendly monitoring
- A **Pygame graphical frontend** with texture support, weather overlays, menus, and click-to-inspect

---

## Key Features

| Domain | Details |
|---|---|
| **Procedural World** | Terrain, districts, roads, rail, transit lines, buildings, companies, housing, and job markets — all generated deterministically from a seed |
| **Autonomous Citizens** | Each person has genetics, personality (7 axes), skills (12 types), work traits, relationships, memories, schedules, finances, and a daily routine |
| **Interconnected Systems** | Finance, crime, law, education, employment, reputation, stock market, and social events all feed into and react to one another |
| **Full Life Cycle** | Citizens age yearly, form relationships, marry, have children, advance in careers, accumulate debt, go to prison, or go bankrupt |
| **Dynamic Economy** | Companies hire, lay off, go bankrupt, and expand. Stock prices derive from company fundamentals. Housing markets respond to district desirability |
| **Law & Justice** | Crimes are generated from pressure and location. Police investigate, courts convict or acquit, prisoners serve time and are released |
| **Weather & Seasons** | Seasonal weather affects citizen mood, energy, and stress. Storms disrupt districts and increase crime |
| **Save / Load** | Full serialisation with pickle or msgpack, autosave every 7 in-game days, and manual save/load via hotkeys |
| **Two Frontends** | Terminal (curses) and graphical (Pygame) — both consume the same `SimulationEngine` |

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Frontends                          │
│  ┌──────────────┐        ┌───────────────────────┐   │
│  │   ui.py      │        │  pygame_frontend.py   │   │
│  │  (curses)    │        │     (Pygame)          │   │
│  └──────┬───────┘        └──────────┬────────────┘   │
│         │                           │                │
│         └───────────┬───────────────┘                │
│                     ▼                                │
│  ┌──────────────────────────────────────────────┐    │
│  │              engine.py                        │    │
│  │  SimulationEngine · Calendar · Weather        │    │
│  │  EventEngine · News · Timeline · Save/Load    │    │
│  └───────┬────────────────────┬─────────────────┘    │
│          │                    │                      │
│          ▼                    ▼                      │
│  ┌──────────────┐   ┌──────────────────────────┐    │
│  │  entities.py │   │      systems.py          │    │
│  │  Person      │   │  Reputation · Finance    │    │
│  │  Population  │   │  Education · Company     │    │
│  │  Household   │   │  Crime · Law · Stock     │    │
│  │  Genetics    │   │  Social · Simulation     │    │
│  │  Personality │   │  Systems (orchestrator)   │    │
│  └──────┬───────┘   └───────────┬──────────────┘    │
│         │                       │                    │
│         └───────────┬───────────┘                    │
│                     ▼                                │
│  ┌──────────────────────────────────────────────┐    │
│  │              world.py                         │    │
│  │  WorldMap · Tile · District · Building        │    │
│  │  Company · TransitLine · Housing · Jobs       │    │
│  │  Economy · Routing · Spatial Indexes          │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │              dump.py                          │    │
│  │  Save file analysis & data extraction utility │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### `world.py` — The Procedural City

The `WorldMap` is the physical foundation of the simulation. It owns the terrain grid, districts, buildings, companies, transport lines, housing and job markets, and lightweight spatial queries. It does not directly own AI logic for people, but provides the physical structure on top of which the life simulation runs.

- **Tiles**: Each tile has terrain type (water, park, rural, suburban, urban, industrial, road, rail), elevation, moisture, zone, property value, commute factor, and occupancy tracking
- **Districts**: Macro-areas with wealth, crime heat, transit scores, desirability, zoning mix, and average rent/home prices
- **Buildings**: Houses, apartments, shops, offices, factories, schools, colleges, police stations, courts, prisons, hospitals, transit stations, warehouses — each with capacity, quality, rent, and service scores
- **Companies**: Procedurally generated employers across 12 sectors (retail, logistics, manufacturing, software, healthcare, education, food, transport, construction, finance, media, public service) with market value, cash, payroll, demand/supply balance, bankruptcy risk, and stock symbols
- **Transit**: Metro lines with stops that reduce commute time for nearby tiles
- **Routing**: BFS-based pathfinding with route caching and road/rail movement cost bonuses

The world is fully deterministic from its seed, enabling reproducible simulations.

### `entities.py` — Autonomous Citizens

The `Person` class is the heart of the simulation. Every citizen is a long-running autonomous agent — no citizen is simulation-special; the UI can inspect any person, but the world logic treats everyone uniformly.

Key subsystems within each person:

| Subsystem | Details |
|---|---|
| **Genetics** | Vitality, cognition, stature, metabolism, stress sensitivity, addiction risk, longevity |
| **Personality** | Discipline, sociability, risk tolerance, empathy, ambition, impulsiveness, resilience |
| **Skills** | 12 skill keys (software, service, logistics, engineering, medicine, teaching, transport, finance, communication, law, fitness, craft) with practice and decay |
| **Work Traits** | Work ethic, reliability, teamwork, adaptability, learning drive |
| **Relationships** | Affinity, trust, romance, respect, familiarity, rivalry, gossip knowledge — each tracked per-pair |
| **Memories** | Categorised memory records (career, social, education, law, finance, life) with emotional impact |
| **Schedule** | 24-hour daily schedule: sleep, commute, work, school, socialise, exercise, errands, clinic visits, rest |
| **Finance** | Cash, bank balance, debt, assets, investment accounts, salary, pay cycle, living costs |
| **Movement** | A* routing with vehicle speed bonuses (none, bike, car, bus pass) and hourly position updates |

Citizens age yearly, form romantic relationships, marry, have children, graduate from school or college, earn certifications, and experience the full range of life events.

### `systems.py` — Interacting Simulation Systems

The goal is not to provide isolated mini-games, but to let law, economy, social reputation, education, and finance reinforce one another over long simulation runs.

| System | Role |
|---|---|
| `ReputationSystem` | Gossip spreads through social contact; public reputation drifts based on karma, stress, arrest record, and debt |
| `FinanceSystem` | Daily pay processing, monthly housing costs, tax withholding, debt interest, savings growth, annual tax filings |
| `EducationSystem` | School and college programmes, skill growth, tuition, enrollment, graduation, and certification |
| `CompanySystem` | Hiring waves, job matching, promotions, layoffs, bankruptcy, company productivity tracking, sector-specific roles |
| `CrimeSystem` | Crime driven by pressure, location, personality, and financial desperation; generates cases with evidence and witnesses |
| `LawSystem` | Police investigation, court dockets, conviction/acquittal, sentencing, prison terms, background checks |
| `StockMarketSystem` | Equity prices derived from company fundamentals; citizen investment behaviour (buy/sell) |
| `SocialEventSystem` | Births, public meltdowns, social gatherings, community goodwill |

`SimulationSystems` orchestrates all of the above, running them in the correct order each day and returning a structured report of events.

### `engine.py` — The Simulation Runtime

`SimulationEngine` is the main entry point. It owns:

- **Calendar**: Year, month, day, hour tracking with season-aware weather
- **Weather**: 7 condition types (clear, cloudy, rain, storm, fog, heatwave, cold snap) with temperature, wind, precipitation, and severity
- **EventEngine**: Watches cross-system state and injects macro events — recession pressure from high unemployment, weather disruptions, stress spirals, community goodwill, company expansion signals
- **News & Timeline**: Categorised event logging for the UI
- **Save/Load**: Full serialisation with pickle or msgpack (auto-detected), schema versioning, state stabilisation on load
- **Autosave**: Every 7 in-game days

The engine steps hour-by-hour. At midnight (hour 0), it runs the full daily cycle: world tick, population update, all systems, event ingestion, and story events.

### `ui.py` — Terminal Frontend

A curses-based, information-dense interface inspired by classic strategy and management games. The layout shows:

- **Header**: Calendar, weather, selected citizen status, macro metrics
- **Left panel**: Selected citizen details (vitals, finances, skills, memories) + relationships
- **Centre**: ASCII city map with terrain glyphs, building markers, citizen dots, and landmark indicators
- **Right panel**: Systems metrics, news feed, company summaries, timeline events
- **Footer**: Controls, tick counter, frame info, pause state

Colour-coded lines highlight positive events (green), warnings (yellow), and danger (red).

### `pygame_frontend.py` — Graphical Frontend

A Pygame-based renderer that reuses the existing `SimulationEngine` without altering simulation logic. Features include:

- **Threaded simulation**: The engine runs on a background thread, while the main thread handles rendering and input
- **Snapshot architecture**: Each frame captures a read-only snapshot of engine state, avoiding lock contention
- **Texture support**: Terrain textures, building sprites, and citizen sprites loaded from a `textures/` directory
- **Weather overlays**: Semi-transparent tints applied over the map based on current weather
- **Zoom**: Adjustable tile size via scroll wheel or bracket keys
- **Click-to-inspect**: Click any tile to select a citizen or view tile info
- **Overlay panels**: Citizen details, relationships, systems, news, companies, timeline, and help — toggled via keyboard or menu bar
- **Menu bar**: View, Map, and Sim dropdown menus for mouse-driven interaction

### `dump.py` — Save File Analysis

A utility script for loading save files and extracting structured data. Functions include:

- `load_save()` — Handles both gzip-compressed and plain pickle saves
- `build_summary()` — Extracts a high-level summary (world dimensions, population count, building/company counts)
- `expand_tiles()` — Decompresses the compact tile format into full tile dictionaries
- `build_full_dump()` — Produces a complete, expanded dump of the save state

---

## Simulation Systems in Detail

### Crime → Law → Reputation Loop

1. **Crime generation** is driven by `crime_tendency` (derived from personality), local `crime_pressure` (from the tile's district), and personal stress. Financial desperation amplifies the probability
2. **Police investigation** scores each case based on evidence strength, witness count, and the suspect's public reputation
3. **Court resolution** weighs evidence, severity, public attention, and judge bias. Convictions result in prison time, reputation damage, and stress spikes
4. **Prison** tracks sentence countdowns; inmates lose happiness daily
5. **Background checks** penalise arrest records and debt, making re-entry into the workforce harder
6. **Reputation decay** — citizens with arrest records or high debt lose public reputation, which feeds back into detection probability and employment

### Employment Cycle

1. Companies generate **hiring waves** based on staffing gaps, demand pressure, and expansion desire
2. Unemployed citizens **seek jobs** by scoring themselves against open postings (skill match, discipline, ambition, education, commute distance)
3. **Promotions** reward high-performing employees with salary raises
4. **Layoffs** target low performers, especially when company health declines
5. **Bankruptcy** fires all employees and removes the company from the world
6. The **stock market** reflects company fundamentals — stock prices move with productivity, demand/supply balance, and bankruptcy risk

### Education & Career Advancement

1. **School programmes** build the `communication` skill; **college programmes** offer software, finance, engineering, and law tracks
2. Skill gains are multiplied by education level (college > certificate > school > none)
3. Graduation provides large skill boosts and improved work traits (adaptability, learning drive)
4. Higher education levels unlock better **job eligibility scores**, creating a path from school to career

### Finance & Taxation

1. **Daily pay** splits 35% to cash, 65% to bank
2. **Monthly housing costs** are charged against cash, then bank, then debt
3. **Debt accumulates interest** at 0.06% daily; high debt drives stress
4. **Annual tax filings** calculate owed vs. withheld amounts and issue refunds or additional liabilities
5. **Savings** earn a small daily return on bank balances above $1,000

---

## Getting Started

### Prerequisites

- Python 3.10+
- `pygame` (optional, for graphical frontend)
- `msgpack` (optional, for more compact saves)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd life-sim

# (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install optional dependencies
pip install pygame msgpack
```

### Running the Simulation

**Terminal UI (default):**
```bash
python engine.py
```

**Pygame graphical frontend:**
```bash
python pygame_frontend.py
```

**Analyse a save file:**
```bash
python dump.py
```

---

## Controls

### Terminal UI (curses)

| Key | Action |
|---|---|
| Arrow keys / WASD | Pan the map |
| Space | Pause / Resume |
| + / - | Speed up / Slow down |
| Tab | Cycle to next citizen |
| C | Centre camera on selected citizen |
| N / M | Scroll news up / down |
| T / G | Scroll timeline up / down |
| F5 | Save simulation |
| F9 | Load simulation |
| Q | Quit |

### Pygame Frontend

| Key / Input | Action |
|---|---|
| Arrow keys / WASD | Pan the map |
| Space | Pause / Resume |
| + / - | Speed up / Slow down |
| [ / ] | Zoom out / Zoom in |
| Tab | Cycle citizen (opens citizen panel) |
| C | Centre camera on selected citizen |
| N / M | Scroll news |
| T / G | Scroll timeline |
| F1 | Toggle help panel |
| F5 | Save simulation |
| F9 | Load simulation |
| Q / Escape | Quit |
| Mouse click on map | Select citizen or inspect tile |
| Scroll wheel on map | Zoom in / out |
| Menu bar | View, Map, and Sim dropdown menus |

---

## Save / Load

The simulation automatically saves every 7 in-game days to `life_sim_save.pkl`. Manual save/load is available via F5/F9.

- **Format**: Pickle by default; msgpack is used automatically if the `msgpack` package is installed
- **Container**: Saves include a magic header (`RLS_SAVE_V2`) and codec identifier for forward compatibility
- **Gzip**: Gzip-compressed saves are detected and decompressed automatically on load
- **State stabilisation**: Loaded saves undergo soft-capping of extreme financial values, company restructuring, and economy normalisation to prevent degenerate states from long runs

---

## Design Philosophy

1. **No special agents** — Every citizen is simulated identically. The UI selects one for inspection, but the engine treats them uniformly
2. **Systems reinforce each other** — Crime is not a standalone mini-game; it emerges from stress, poverty, and personality, and feeds into law, reputation, and employment
3. **Explicit over compact** — The code is deliberately verbose so the simulation can be expanded rather than treated like a toy
4. **Deterministic from seed** — The entire world and its companies are generated from a seed, enabling reproducible runs
5. **Spatial economy** — Companies exist in buildings, not as abstract rows. Commute time is distance-driven. Property values depend on district wealth, transit access, and crime
6. **Frontend-agnostic engine** — The `SimulationEngine` has no UI dependencies. Both the curses and Pygame frontends consume it through the same interface

---

## Extending the Simulation

The architecture is designed for extension. Here are natural entry points:

- **New systems**: Subclass or add to `SimulationSystems` and register new tick logic in `tick_daily()`
- **New person attributes**: Add fields to `Person.__init__()` and update `_serialize()` / `_deserialize()` methods
- **New building types**: Add to `BUILDING_TYPES` in `world.py` and update `_spawn_building_for_tile()` and `_generate_companies()`
- **New company sectors**: Add to `COMPANY_SECTORS` and update `_skill_for_sector()`, `_title_for_sector()`, and `_generate_job_market()`
- **New frontend**: Import `SimulationEngine` and build any interface — web, REST API, headless batch runner
- **New events**: Extend `EventEngine.tick()` to watch additional cross-system conditions and inject new timeline events
- **Alternate map generators**: Replace `WorldMap.generate_world()` or individual steps (terrain, districts, roads) while keeping the same data structures

---

## Dependencies

| Package | Required | Purpose |
|---|---|---|
| Python 3.10+ | Yes | Runtime |
| `curses` | Yes (bundled on most systems) | Terminal UI |
| `pygame` | No | Graphical frontend |
| `msgpack` | No | Compact save file serialisation |

---

## License

This project is provided as-is for educational and experimental purposes. See the repository for license details.
