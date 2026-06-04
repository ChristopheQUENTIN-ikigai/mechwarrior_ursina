# Mech Tactical Arena — Architecture & Modding Guide

## Layout

```
mech2/
├── main.py                   # CLI entrypoint, ~60 lines
├── config.json               # global defaults (window, camera, weapons, HUD)
├── config_loader.py          # JSON → CFG dict + keybinds
│
├── core/                     # engine glue (no game-specific logic)
│   ├── game.py               # Game orchestrator: holds systems + scenario
│   ├── scenario.py           # Scenario base class + JSON loader
│   ├── registry.py           # plugin registry (weapons/enemies/maps/scenarios)
│   ├── events.py             # synchronous pub/sub bus
│   └── mod_loader.py         # discovers and loads mods/<id>/mod.json
│
├── systems/                  # reusable subsystems
│   ├── lighting.py           # named lighting presets, sun/moon, ambient
│   ├── camera_rig.py         # 3rd-person follow rig with mouse look + zoom
│   ├── input_router.py       # action -> handler dispatch (replaces global input)
│   ├── terrain_stream.py     # ground tile streaming
│   ├── tex_gen.py            # procedural textures
│   └── weapons.py            # Weapon class with 4 firing types (registry-aware)
│
├── entities/
│   ├── player_mech.py        # PlayerMech with arms, shoulder pods, hardpoints
│   └── enemy_mech.py         # EnemyMech registered as 'patrol_mech'
│
├── ai/
│   └── squad.py              # legacy shim (spawn_enemy_squad helper)
│
├── ui/
│   ├── cockpit.py            # HUD: compass, bars, crosshair, weapon rail
│   └── loadout.py            # (placeholder)
│
├── maps/                     # map builders, register via @registry.map
│   ├── megacity.py
│   ├── arena_flat.py
│   └── canyon.py
│
├── scenarios/                # JSON params + optional .py logic
│   ├── megacity_skirmish.json
│   ├── arena_duel.json
│   ├── canyon_ambush.json
│   ├── wave_defense.json
│   ├── wave_defense.py       # custom logic via Scenario subclass
│   └── mod_demo.json
│
└── mods/
    └── example_mod/
        ├── mod.json          # manifest (id, version, entrypoint)
        └── plugin.py         # imports trigger registry decorators
```

## Running

```bash
python main.py                             # default scenario (megacity_skirmish)
python main.py --scenario arena_duel
python main.py --scenario wave_defense
python main.py --scenario canyon_ambush
python main.py --scenario mod_demo --mods example_mod
python main.py --mods all                  # autoload every mod in mods/
python main.py --list                      # show available scenarios + mods
python main.py -v                          # verbose event bus logging
```

## Core flow

1. `main.py` parses CLI, builds `Game(scenario, mods, ...)`.
2. `Game.__init__` constructs the Ursina app, configures the window, eagerly
   imports `maps/` and `entities.enemy_mech` (firing all built-in `@registry.*`
   decorators), then loads any requested mods (more registrations).
3. `Game.start_scenario()` loads `<id>.json` (and `<id>.py` if it exists),
   builds the map via `registry.maps[scenario.map]`, builds the lighting via
   `LightingRig(scenario.lighting)`, spawns the player with the scenario's
   loadout, builds the camera rig and HUD, wires input via `InputRouter`, and
   calls `scenario.on_load()` → `on_player_spawn()` → `on_start()`.
4. Per-frame, Ursina calls module-level `update()` (which forwards to
   `Game.update()`), which advances `scenario_time`, ticks the cam rig,
   updates celestials, and calls `scenario.on_update(dt)`.
5. Ursina's `input(key)` forwards to `Game.dispatch_input(key)` →
   `InputRouter.dispatch(key)`, which fans out to registered handlers.

## Adding things

### New weapon

Add a config block to `config.json` under `"weapons"`:

```json
"flamer": {
    "type": "projectile", "hardpoint": "arm_left",
    "speed": 25, "damage": 6, "heat": 2.5, "cooldown": 0.05,
    "spread_deg": 4, "color": [255,140,40], "scale": 0.3, "model": "sphere"
}
```

Bind a key in `config.json` keybinds: `"fire_flamer": "4"`. Add a `weapon_actions`
entry in `core/game.py::_wire_input` mapping `'flamer' -> 'fire_flamer'` (or
let the fallback `f'fire_{wkey}'` pick it up automatically). Add `"flamer"` to
the `player_loadout` of any scenario JSON.

### New map

Create `maps/whatever.py`:

```python
from core.registry import registry

@registry.map('whatever')
def build(ctx):
    # ctx.center: Vec3, ctx.params: dict from scenario JSON
    # ... place Entity()s ...
    return {'spawn_points': [...], 'bounds': (-r, r), 'count': n}
```

Add `from . import whatever` to `maps/__init__.py`. Reference by id in any
scenario JSON: `"map": "whatever"`.

### New enemy

Subclass `EnemyMech` in `entities/`:

```python
from core.registry import registry
from entities.enemy_mech import EnemyMech

@registry.enemy('sniper_mech')
class SniperMech(EnemyMech):
    def __init__(self, pos, **kw):
        super().__init__(pos, **kw)
        self.attack_range = 80
        self.fire_cooldown_max = 3.0
```

Reference in a scenario JSON: `"type": "sniper_mech"`.

### New scenario

Pure JSON (no logic):

```json
// scenarios/my_mission.json
{
    "id": "my_mission",
    "title": "...",
    "map": "canyon",
    "map_params": { "length": 150 },
    "lighting": "night_moon",
    "player_spawn": [0, 2, -100],
    "player_loadout": ["gatling", "sniper"],
    "enemy_groups": [{ "type": "patrol_mech", "count": 5, "at": [0,0,50], "spread": 20 }],
    "win_condition":  { "type": "kill_all" },
    "lose_condition": { "type": "player_dead" }
}
```

Run with `python main.py --scenario my_mission`.

Custom logic? Add `scenarios/my_mission.py`:

```python
from core.scenario import Scenario
from core.registry import registry

@registry.scenario('my_mission')
class MyMission(Scenario):
    def on_start(self):
        super().on_start()  # spawns enemy_groups
        # ... custom hooks ...
    def on_update(self, dt):
        super().on_update(dt)  # default win/lose check
        # ... custom logic ...
    def on_event(self, name, payload):
        if name == 'enemy.killed':
            print('frag!', payload)
```

### New lighting preset

Add to `LIGHTING_PRESETS` in `systems/lighting.py`. Reference in scenario JSON
via `"lighting": "your_preset"`.

### New mod

Create `mods/your_mod/`:

```
mods/your_mod/
├── mod.json
└── plugin.py
```

`mod.json`:

```json
{
    "id": "your_mod", "name": "Your Mod", "version": "0.1.0",
    "author": "...", "description": "...",
    "entrypoint": "mods.your_mod.plugin"
}
```

`plugin.py` uses any combination of:

- `registry.register_weapon_config(id, cfg_dict)` for weapons
- `@registry.enemy(id)` on a class
- `@registry.map(id)` on a function
- `@registry.scenario(id)` on a `Scenario` subclass
- `bus.subscribe('event.name', handler)` for game-event reactions

Run with `python main.py --mods your_mod` (or `--mods all`).

## Win/Lose conditions

Built-in condition types (in `Scenario._eval_condition`):

| Type              | Params                          | Triggers when                |
|-------------------|---------------------------------|------------------------------|
| `kill_all`        | —                               | All scenario enemies dead    |
| `player_dead`     | —                               | `player.hp <= 0`             |
| `survive_seconds` | `seconds: int`                  | `scenario_time >= seconds`   |
| `reach_position`  | `at: [x,y,z]`, `radius: float`  | Player within radius of `at` |

Add new types by overriding `Scenario._eval_condition` in a subclass.

## Event bus

Conventional event names are listed in `core/events.py` docstring. Handlers
are sync, exceptions are caught. Use `bus.subscribe('*', fn)` for a
catch-all (handler receives `_event=name` plus payload).

## Trade-offs left as exercises

The architecture intentionally stops short of a few things:

- **Save/load**: no serialization. State lives in entities; persistence
  would mean defining a snapshot schema per entity type.
- **Networking**: single-player only. The event bus is local; multiplayer
  would need an authoritative server bus.
- **Hot-reload mods**: mods are loaded once at startup. Reloading would
  need per-mod cleanup hooks plus careful entity ownership tracking.
- **Mod sandbox**: mods run with full Python privileges. Don't load mods
  from untrusted sources.
