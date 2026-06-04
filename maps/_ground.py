"""
maps/_ground.py
===============
Shared ground-plane builder.

ROOT CAUSE of the "transparent ground" bug: none of the map builders created
a floor, and systems/terrain_stream.py (the only thing that *could* make ground)
was never instantiated by core/game.py. So the only thing behind the buildings
was the Sky() — the world was literally see-through, and the player's downward
"am I on the ground?" raycast hit nothing.

This module provides one function, `build_ground(...)`, that every map calls.
It creates a single large textured slab whose TOP face sits at `y_top` (default
0.0). Buildings are placed at y = height/2 assuming ground at y=0, so a *flat*
plane is the correct match (procedural rolling terrain would make them clip).

It is intentionally ONE entity + ONE box collider, so it costs almost nothing
and gives the gravity/camera raycasts a real surface to land on.
"""

from ursina import Entity, Vec3, color
from config_loader import CFG
from systems.tex_gen import get_texture


def build_ground(center=Vec3(0, 0, 0), full_size=300, map_key=None,
                 texture='concrete', tint=(80, 82, 88), y_top=None,
                 thickness=4.0):
    """Create a flat floor slab covering the play area.

    Args:
        center:     world center (Vec3).
        full_size:  total width/depth of the slab in world units.
        map_key:    optional key into CFG['ground'] (e.g. 'megacity') to pull
                    texture/tint/margin defaults from config.
        texture:    procedural texture name (overridden by config if map_key set).
        tint:       (r,g,b) multiply tint (overridden by config if map_key set).
        y_top:      surface height. Defaults to CFG['ground']['y_top'] or 0.0.
        thickness:  slab depth (so the collider has real volume).

    Returns:
        The ground Entity (tagged 'ground').
    """
    gcfg = CFG.get('ground', {})
    if y_top is None:
        y_top = gcfg.get('y_top', 0.0)
    tile_repeat = gcfg.get('tile_repeat', 0.25)

    if map_key and map_key in gcfg:
        mc = gcfg[map_key]
        texture = mc.get('texture', texture)
        tint = tuple(mc.get('tint', tint))

    tex = get_texture(texture)
    reps = max(1, int(full_size * tile_repeat))

    ground = Entity(
        model='cube',
        position=center + Vec3(0, y_top - thickness / 2.0, 0),
        scale=(full_size, thickness, full_size),
        color=color.rgb(*tint),
        texture=tex,
        texture_scale=(reps, reps),
        collider='box',
        tag='ground',
    )
    # NOTE: we deliberately do NOT give the ground an `hp` attribute, so
    # hasattr(ent,'hp') stays False and weapons/crosshair never treat the
    # floor as a damageable target.
    print(f"[GROUND] map={map_key} size={full_size} y_top={y_top} tex={texture} reps={reps}")
    return ground
