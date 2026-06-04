"""
core/scenario.py
================
Hybrid JSON+Python scenario system.

A scenario is defined by TWO files in scenarios/:
    foo.json    - declarative parameters (map id, lighting, enemy comp, win cond)
    foo.py      - optional Python class with logic hooks (subclass Scenario)

If only the JSON exists, a default Scenario is used (no custom logic).
If both exist, the .py registers itself via @registry.scenario(id) and
the JSON is passed to its __init__ via the `params` dict.

JSON schema (see scenarios/megacity_skirmish.json for example):
{
    "id": "megacity_skirmish",
    "title": "Megacity Skirmish",
    "description": "Patrol a procedural city, hunt enemy squads.",
    "map": "megacity",                   # registry.maps key
    "map_params": { "size": 120 },       # passed to map builder
    "lighting": "day_clear",             # systems/lighting.py preset
    "player_spawn": [0, 2, 0],
    "player_loadout": ["gatling","railgun","rocketpod","heatseeker","sniper"],
    "enemy_groups": [                    # spawn definitions
        { "type": "patrol_mech", "count": 4, "at": [80, 0, 60], "spread": 10 }
    ],
    "win_condition": { "type": "kill_all" },
    "lose_condition": { "type": "player_dead" },
    "hud_overlays": []
}

Lifecycle hooks (override in subclass):
    on_load()       - after map+lighting built, before player spawned
    on_player_spawn() - after player is in world
    on_start()      - after everything is up, before first frame
    on_update(dt)   - every frame
    on_event(name, payload) - every event bus message (if subscribed)
    on_unload()     - cleanup before next scenario
"""

import json
import os
from core.events import bus
from core.registry import registry


class Scenario:
    """Base scenario. Override hooks for custom logic.

    Subclasses are constructed with the parsed JSON `params` dict.
    The Game object is injected after construction (self.game).
    """

    def __init__(self, params):
        self.params = params
        self.id = params.get('id', 'unknown')
        self.title = params.get('title', self.id)
        self.game = None              # set by Game.start_scenario
        self._spawned_enemies = []
        self._completed = False

    # ===== convenience accessors =====
    def get(self, key, default=None):
        return self.params.get(key, default)

    # ===== lifecycle hooks (override) =====
    def on_load(self):
        """After map + lighting built, before player spawn. Default: no-op."""
        pass

    def on_player_spawn(self):
        """Player is in the world. Apply scenario-specific player tweaks here."""
        pass

    def on_start(self):
        """All systems live. Last chance before first frame.
        Default behaviour: spawn the enemy_groups declared in JSON.
        Override if you want custom waves / scripted spawns.
        """
        self._default_spawn_enemies()

    def on_update(self, dt):
        """Per-frame logic. Default: check win/lose conditions."""
        if self._completed:
            return
        self._check_conditions()

    def on_event(self, name, payload):
        """Dispatched for every event bus message. Default: no-op.
        Subscribed automatically by Game when scenario is loaded.
        """
        pass

    def on_unload(self):
        """Cleanup. Default: no-op (Game handles entity cleanup)."""
        pass

    # ===== default implementations subclasses can call =====
    def _default_spawn_enemies(self):
        """Spawn enemies declared in JSON 'enemy_groups'."""
        from ursina import Vec3
        import random
        groups = self.params.get('enemy_groups', [])
        for g in groups:
            kind = g.get('type', 'patrol_mech')
            count = g.get('count', 1)
            at = Vec3(*g.get('at', [0, 0, 0]))
            spread = g.get('spread', 8)
            cls = registry.get_enemy(kind)
            for _ in range(count):
                offset = Vec3(
                    random.uniform(-spread, spread),
                    0,
                    random.uniform(-spread, spread),
                )
                ent = cls(at + offset)
                self._spawned_enemies.append(ent)
                bus.publish('enemy.spawned', enemy=ent, spawner=self)
        print(f'[SCEN] {self.id}: spawned {len(self._spawned_enemies)} enemies')

    def _check_conditions(self):
        """Evaluate win/lose conditions from JSON."""
        win = self.params.get('win_condition', {})
        lose = self.params.get('lose_condition', {})

        if self._eval_condition(lose):
            self._complete(won=False)
            return
        if self._eval_condition(win):
            self._complete(won=True)

    def _eval_condition(self, cond):
        if not cond:
            return False
        ctype = cond.get('type', '')
        if ctype == 'kill_all':
            return all((not e.enabled or e.hp <= 0) for e in self._spawned_enemies)
        if ctype == 'player_dead':
            p = self.game.player if self.game else None
            return p is None or p.hp <= 0
        if ctype == 'survive_seconds':
            return (self.game.scenario_time or 0) >= cond.get('seconds', 60)
        if ctype == 'reach_position':
            from ursina import Vec3
            target = Vec3(*cond.get('at', [0, 0, 0]))
            radius = cond.get('radius', 5)
            p = self.game.player
            return p and (p.world_position - target).length() <= radius
        return False

    def _complete(self, won):
        if self._completed:
            return
        self._completed = True
        bus.publish('scenario.completed', scenario=self, won=won)
        print(f'[SCEN] {self.id}: COMPLETE  won={won}')

    @property
    def completed(self):
        return self._completed


# =============================================================================
# Loading
# =============================================================================

def load_scenario(scenario_id, scenarios_dir='scenarios'):
    """Load a scenario by id from <scenarios_dir>/<id>.json (+ optional .py).

    The .py is imported (which may register a class via @registry.scenario).
    Then we look up the class in registry; if missing, fall back to the
    default Scenario base class.
    """
    json_path = os.path.join(scenarios_dir, f'{scenario_id}.json')
    py_path   = os.path.join(scenarios_dir, f'{scenario_id}.py')

    if not os.path.exists(json_path):
        raise FileNotFoundError(f'Scenario JSON not found: {json_path}')

    with open(json_path, 'r') as f:
        params = json.load(f)

    # Import the .py if it exists — it registers its class via decorator
    if os.path.exists(py_path):
        import importlib
        importlib.import_module(f'{scenarios_dir}.{scenario_id}')

    cls = registry.scenarios.get(scenario_id, Scenario)
    return cls(params)
