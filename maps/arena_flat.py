"""
maps/arena_flat.py
==================
Clean flat arena bounded by stone walls. Good for duels and weapon testing.
Registered as 'arena_flat'.

Params:
    radius       (default 60) - half-width of the arena
    wall_height  (default 12)
    pillars      (default 6)  - number of cover pillars scattered inside
"""

import random
import math
from ursina import Entity, Vec3, color
from core.registry import registry
from config_loader import CFG
from maps._ground import build_ground


@registry.map('arena_flat')
def build_arena_flat(ctx):
    p = ctx.params or {}
    center = ctx.center
    radius = p.get('radius', 60)
    wall_h = p.get('wall_height', 12)
    n_pillars = p.get('pillars', 6)

    # Floor first (fixes see-through arena).
    margin = CFG.get('ground', {}).get('arena_flat', {}).get('margin', 12)
    build_ground(center=center, full_size=(radius + margin) * 2,
                 map_key='arena_flat')

    # Outer perimeter — 4 thick walls forming a square arena
    wall_thickness = 2
    walls_color = color.rgb(120, 120, 130)
    Entity(model='cube', position=center + Vec3(0, wall_h/2, radius),
           scale=(radius*2, wall_h, wall_thickness),
           color=walls_color, collider='box', tag='wall')
    Entity(model='cube', position=center + Vec3(0, wall_h/2, -radius),
           scale=(radius*2, wall_h, wall_thickness),
           color=walls_color, collider='box', tag='wall')
    Entity(model='cube', position=center + Vec3(radius, wall_h/2, 0),
           scale=(wall_thickness, wall_h, radius*2),
           color=walls_color, collider='box', tag='wall')
    Entity(model='cube', position=center + Vec3(-radius, wall_h/2, 0),
           scale=(wall_thickness, wall_h, radius*2),
           color=walls_color, collider='box', tag='wall')

    # Inner cover pillars
    placed = []
    pillar_colors = [color.rgb(80, 80, 90), color.rgb(100, 100, 110), color.rgb(110, 90, 80)]
    attempts = 0
    while len(placed) < n_pillars and attempts < n_pillars * 10:
        attempts += 1
        ang = random.uniform(0, math.tau)
        r = random.uniform(8, radius - 8)
        px = math.cos(ang) * r
        pz = math.sin(ang) * r
        # avoid duel spawn points
        if abs(px) < 20 and abs(pz) > radius - 10:
            continue
        too_close = any(((px-ox)**2 + (pz-oz)**2) < 100 for ox, oz in placed)
        if too_close:
            continue
        placed.append((px, pz))
        h = random.uniform(4, 8)
        w = random.uniform(2, 4)
        Entity(model='cube',
               position=center + Vec3(px, h/2, pz),
               scale=(w, h, w),
               color=random.choice(pillar_colors),
               collider='box', tag='pillar')

    print(f'[MAP][arena_flat] radius={radius} pillars={len(placed)}')
    return {
        'spawn_points': [
            center + Vec3(0, 2, -radius + 8),   # player
            center + Vec3(0, 2,  radius - 8),   # opponent
        ],
        'bounds': (-radius, radius),
        'count': 4 + len(placed),
    }
