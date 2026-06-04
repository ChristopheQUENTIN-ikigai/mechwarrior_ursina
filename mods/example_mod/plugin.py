"""
mods/example_mod/plugin.py
==========================
Demonstration mod. Importing this module registers:
    weapon  : 'plasma_cannon'    (slow projectile, AoE-ish, scary heat)
    enemy   : 'heavy_mech'       (more HP, less speed, harder hitter)
    scenario: 'mod_demo'         (uses both)

Players reference these by id in scenarios:
    "player_loadout": [..., "plasma_cannon"]
    "enemy_groups":   [{ "type": "heavy_mech", ... }]

The plasma cannon is just a config dict — Weapon(mech, key) handles the rest.
The heavy_mech is a subclass of EnemyMech with stat overrides.
"""

from ursina import Vec3, color
from core.registry import registry
from entities.enemy_mech import EnemyMech


# ============================================================
# Weapon: plasma cannon
# ============================================================
registry.register_weapon_config('plasma_cannon', {
    'type': 'projectile',
    'hardpoint': 'arm_left',
    'speed': 22, 'damage': 90, 'heat': 40,
    'cooldown': 1.6,
    'spread_deg': 0.5,
    'color': [80, 255, 200], 'scale': 0.7, 'model': 'sphere',
})
print('[MOD][example_mod] registered weapon: plasma_cannon')


# ============================================================
# Enemy: heavy mech
# ============================================================
@registry.enemy('heavy_mech')
class HeavyMech(EnemyMech):
    def __init__(self, pos, **kw):
        super().__init__(pos, **kw)
        self.hp = 220
        self.max_hp = 220
        self.speed = 1.8
        self.attack_range = 55
        self.fire_cooldown_max = 1.0
        self.proj_damage = 28
        self.scale = (3.2, 5.0, 3.2)
        self.color = color.rgb(180, 60, 60)


# ============================================================
# Scenario: mod_demo (registered via decorator pattern from JSON loader)
# Note: scenarios are normally loaded by id from scenarios/<id>.json.
# A mod can ship its own scenario JSON — drop it in scenarios/ or extend
# the loader to look in mod folders. For now we just register the class
# and provide an inline params dict.
# ============================================================
from core.scenario import Scenario


@registry.scenario('mod_demo')
class ModDemoScenario(Scenario):
    """Run with: python main.py --scenario mod_demo --mods example_mod
    (Requires a scenarios/mod_demo.json exists, OR Game falls back to
    these inline defaults — see Game.start_scenario.)
    """
    DEFAULT_PARAMS = {
        'id': 'mod_demo',
        'title': 'Mod Demo',
        'map': 'arena_flat',
        'map_params': {'radius': 70, 'pillars': 6},
        'lighting': 'dusk_orange',
        'player_spawn': [0, 2, -55],
        'player_loadout': ['gatling', 'railgun', 'plasma_cannon'],
        'enemy_groups': [
            {'type': 'patrol_mech', 'count': 3, 'at': [0, 0, 30], 'spread': 12},
            {'type': 'heavy_mech',  'count': 1, 'at': [0, 0, 55], 'spread': 0},
        ],
        'win_condition':  {'type': 'kill_all'},
        'lose_condition': {'type': 'player_dead'},
    }
