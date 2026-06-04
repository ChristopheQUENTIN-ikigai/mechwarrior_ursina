"""
ai/squad.py
===========
Deprecated. Kept as a shim so older code paths still work.
EnemyMech now lives in entities/enemy_mech.py and registers itself
as 'patrol_mech' via @registry.enemy.

The 'spawn_enemy_squad' helper is still useful for ad-hoc spawning
outside the scenario JSON system.
"""

import random
from ursina import Vec3
from config_loader import CFG
from entities.enemy_mech import EnemyMech


def spawn_enemy_squad(pos, count=None):
    ecfg = CFG['enemies']
    n = count if count is not None else ecfg['squad_size']
    spawned = []
    for _ in range(n):
        e = EnemyMech(pos + Vec3(random.randint(-10, 10), 0,
                                 random.randint(-10, 10)))
        spawned.append(e)
    return spawned
