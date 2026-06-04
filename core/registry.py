"""
core/registry.py
================
Central registry for pluggable game content.

Four registries live here:
    registry.weapons     - id -> dict (config block, used by Weapon class)
    registry.enemies     - id -> class (enemy mech subclass)
    registry.maps        - id -> callable (build_map(ctx) -> dict)
    registry.scenarios   - id -> class (Scenario subclass)

A weapon entry is just a config dict (like CFG['weapons']['gatling']).
A map entry is a function that, given a context object, builds the world
and returns metadata (spawn points, bounds, etc.).
A scenario entry is a Scenario subclass (see core/scenario.py).
An enemy entry is a class that takes (pos, **kwargs) in its __init__.

Decorators are provided for ergonomic registration:

    from core.registry import registry

    @registry.scenario('arena_duel')
    class ArenaDuel(Scenario):
        ...

    @registry.map('canyon')
    def build_canyon(ctx):
        ...

    @registry.enemy('sniper_mech')
    class SniperMech(EnemyMech):
        ...

Mods just import this module and use the decorators — registrations
happen at import time, before Game.start_scenario is called.
"""


class Registry:
    def __init__(self):
        self.weapons = {}
        self.enemies = {}
        self.maps = {}
        self.scenarios = {}

    # ----- decorator factories -----
    def weapon(self, id_):
        """Register a weapon config dict."""
        def deco(cfg_dict):
            self.weapons[id_] = cfg_dict
            print(f'[REG] weapon: {id_}')
            return cfg_dict
        return deco

    def enemy(self, id_):
        """Register an enemy class. The class should accept (pos, **kw)."""
        def deco(cls):
            self.enemies[id_] = cls
            print(f'[REG] enemy: {id_} -> {cls.__name__}')
            return cls
        return deco

    def map(self, id_):
        """Register a map builder function `build(ctx) -> dict`."""
        def deco(fn):
            self.maps[id_] = fn
            print(f'[REG] map: {id_}')
            return fn
        return deco

    def scenario(self, id_):
        """Register a Scenario subclass."""
        def deco(cls):
            self.scenarios[id_] = cls
            print(f'[REG] scenario: {id_} -> {cls.__name__}')
            return cls
        return deco

    # ----- direct registration (non-decorator) -----
    def register_weapon_config(self, id_, cfg):
        self.weapons[id_] = cfg

    # ----- lookup helpers with friendly errors -----
    def get_scenario(self, id_):
        if id_ not in self.scenarios:
            raise KeyError(
                f'Unknown scenario {id_!r}. Available: '
                f'{sorted(self.scenarios.keys())}'
            )
        return self.scenarios[id_]

    def get_map(self, id_):
        if id_ not in self.maps:
            raise KeyError(
                f'Unknown map {id_!r}. Available: '
                f'{sorted(self.maps.keys())}'
            )
        return self.maps[id_]

    def get_enemy(self, id_):
        if id_ not in self.enemies:
            raise KeyError(
                f'Unknown enemy {id_!r}. Available: '
                f'{sorted(self.enemies.keys())}'
            )
        return self.enemies[id_]

    def get_weapon(self, id_):
        if id_ not in self.weapons:
            raise KeyError(
                f'Unknown weapon {id_!r}. Available: '
                f'{sorted(self.weapons.keys())}'
            )
        return self.weapons[id_]

    def summary(self):
        # Also surface CFG['weapons'] so the picture isn't misleading:
        # registry.weapons holds mod-added weapons, but built-ins live in CFG.
        try:
            from config_loader import CFG
            cfg_weapons = sorted(CFG.get('weapons', {}).keys())
        except Exception:
            cfg_weapons = []
        return {
            'weapons (cfg)': cfg_weapons,
            'weapons (mod)': sorted(self.weapons.keys()),
            'enemies':       sorted(self.enemies.keys()),
            'maps':          sorted(self.maps.keys()),
            'scenarios':     sorted(self.scenarios.keys()),
        }


# Module-level singleton
registry = Registry()
