"""
maps/canyon.py
==============
Linear canyon corridor: two long ridge walls with rocky cover scattered
along the floor. Good for ambush / convoy / patrol scenarios.

Registered as 'canyon'.

Params:
    length      (default 200) - corridor length along Z
    width       (default 50)  - corridor width along X
    wall_height (default 25)
    rocks       (default 25)  - cover boulders
"""

import random
from ursina import Entity, Vec3, color
from core.registry import registry
from config_loader import CFG
from maps._ground import build_ground


@registry.map('canyon')
def build_canyon(ctx):
    p = ctx.params or {}
    center = ctx.center
    length = p.get('length', 200)
    width = p.get('width', 50)
    wall_h = p.get('wall_height', 25)
    n_rocks = p.get('rocks', 25)

    # Canyon floor first (fixes see-through corridor).
    margin = CFG.get('ground', {}).get('canyon', {}).get('margin', 30)
    build_ground(center=center, full_size=(max(length, width) + margin) * 2,
                 map_key='canyon')

    rock_palette = [color.rgb(110, 90, 70), color.rgb(120, 100, 80),
                    color.rgb(95, 80, 65), color.rgb(130, 110, 90)]
    cliff_palette = [color.rgb(100, 80, 60), color.rgb(120, 95, 70)]

    # Two long jagged cliff walls (built as a series of cubes for visual variety)
    seg = 8
    half_w = width / 2
    for z in range(-length, length, seg):
        for side in (-1, 1):
            jitter_x = random.uniform(-1.5, 1.5)
            jitter_h = random.uniform(-3, 5)
            Entity(
                model='cube',
                position=center + Vec3(side * (half_w + jitter_x),
                                       (wall_h + jitter_h) / 2,
                                       z + random.uniform(-1, 1)),
                scale=(seg + 2, wall_h + jitter_h, seg + 2),
                color=random.choice(cliff_palette),
                collider='box', tag='cliff',
            )

    # End caps so canyon is closed
    for z_end in (-length - 4, length + 4):
        Entity(model='cube',
               position=center + Vec3(0, wall_h/2, z_end),
               scale=(width + 8, wall_h + 6, 6),
               color=cliff_palette[0],
               collider='box', tag='cliff')

    # Floor rocks for cover
    placed = []
    for _ in range(n_rocks * 4):
        if len(placed) >= n_rocks:
            break
        x = random.uniform(-half_w + 3, half_w - 3)
        z = random.uniform(-length + 10, length - 10)
        too_close = any(((x-ox)**2 + (z-oz)**2) < 36 for ox, oz in placed)
        if too_close:
            continue
        placed.append((x, z))
        h = random.uniform(2, 4.5)
        w = random.uniform(2, 4)
        Entity(model='cube',
               position=center + Vec3(x, h/2, z),
               scale=(w, h, w * random.uniform(0.8, 1.3)),
               color=random.choice(rock_palette),
               collider='box', tag='rock')

    print(f'[MAP][canyon] length={length*2} width={width} rocks={len(placed)}')
    return {
        'spawn_points': [
            center + Vec3(0, 2, -length + 12),    # player at south end
            center + Vec3(0, 2, 0),               # mid-canyon
            center + Vec3(0, 2, length - 12),     # north ambush
        ],
        'bounds': (-length, length),
        'count': len(placed),
    }
