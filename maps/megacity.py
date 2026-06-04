"""
maps/megacity.py
================
Procedural megacity map. Registered as 'megacity'.

Map builder signature:
    build(ctx) -> dict
where ctx has:
    .center      Vec3
    .params      dict (from scenario JSON 'map_params')
and the returned dict carries:
    'spawn_points' : list[Vec3]   - candidate spawn locations (player & enemies)
    'bounds'       : (min_xz, max_xz)  - playable area
    'count'        : int          - n props placed (debug)
"""

import random
from ursina import Entity, Vec3, color

from config_loader import CFG
from systems.tex_gen import get_texture
from core.registry import registry
from maps._ground import build_ground


def _pick_building_type(types_cfg):
    entries = list(types_cfg.items())
    weights = [v['weight'] for _, v in entries]
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for name, cfg in entries:
        cumulative += cfg['weight']
        if r <= cumulative:
            return name, cfg
    return entries[-1]


def _render_buildings(center, specs, tex_cache, batch):
    """Render building specs either batched (few draw calls) or one-per-entity.

    OPTIMIZATION: in Ursina/Panda3D every Entity is its own draw call + node.
    A few hundred building cubes => a few hundred draw calls (this is why the
    HUD showed 184 entities / 146 colliders). Entity.combine() merges child
    meshes into ONE mesh; we group by texture (one texture per draw) so the
    whole city collapses to roughly one entity *per texture* plus a single
    mesh collider each.

    Per-building color survives as baked vertex colors. The trade-off: a
    batched slab can't be individually tinted/shrunk when shot (it's one mesh),
    so weapons skip the cosmetic hit-flash on batched buildings. Set
    config.json city.batch=false to fall back to fully individual buildings.
    """
    # group specs by texture name
    groups = {}
    for offset, scale, col, tex_name in specs:
        groups.setdefault(tex_name, []).append((offset, scale, col))

    if not batch:
        for tex_name, items in groups.items():
            tex = tex_cache.get(tex_name)
            for offset, scale, col in items:
                Entity(model='cube', position=center + offset, scale=scale,
                       color=col, texture=tex, collider='box', tag='building')
        return

    for tex_name, items in groups.items():
        tex = tex_cache.get(tex_name)
        parent = Entity(position=center, tag='building')
        for offset, scale, col in items:
            Entity(parent=parent, model='cube', position=offset,
                   scale=scale, color=col)
        try:
            parent.combine()                      # merge children -> one mesh
            parent.texture = tex
            parent.collider = 'mesh'              # one collider for the batch
            parent.batched = True                 # weapons skip per-hit tint
        except Exception as e:
            # combine() unavailable/failed: keep children as real entities so
            # the city still renders & collides (just unbatched).
            print(f'[MAP][megacity] combine() failed for {tex_name!r}: {e} '
                  f'-> falling back to individual buildings')
            for child in list(parent.children):
                child.texture = tex
                child.collider = 'box'
                child.tag = 'building'
            parent.batched = False


@registry.map('megacity')
def build_megacity(ctx):
    cfg = CFG['city']
    params = ctx.params or {}
    center = ctx.center
    size = params.get('size', cfg['size'])
    spacing = params.get('building_spacing', cfg['building_spacing'])
    density = params.get('fill_density', cfg.get('fill_density', 0.55))
    ex_x = params.get('exclusion_x', cfg['exclusion_x'])
    ex_z = params.get('exclusion_z', cfg['exclusion_z'])
    types_cfg = cfg['building_types']

    tex_cache = {n['texture']: get_texture(n['texture']) for n in types_cfg.values()}

    color_palettes = {
        'skyscraper':   [color.rgb(50, 60, 80), color.rgb(60, 70, 100), color.rgb(70, 80, 110)],
        'office':       [color.rgb(90, 90, 100), color.rgb(100, 100, 110), color.rgb(110, 105, 95)],
        'house_small':  [color.rgb(160, 140, 110), color.rgb(140, 120, 100), color.rgb(170, 155, 130), color.rgb(120, 140, 120)],
        'house_medium': [color.rgb(150, 130, 100), color.rgb(130, 130, 140), color.rgb(160, 145, 120)],
        'hospital':     [color.rgb(200, 200, 210), color.rgb(180, 190, 200)],
        'factory':      [color.rgb(100, 95, 85), color.rgb(90, 85, 80), color.rgb(110, 100, 90)],
        'manufacture':  [color.rgb(85, 80, 75), color.rgb(95, 90, 85)],
        'station':      [color.rgb(140, 140, 150), color.rgb(130, 135, 145)],
        'airport':      [color.rgb(170, 170, 180), color.rgb(160, 165, 175)],
        'food_shop':    [color.rgb(180, 130, 80), color.rgb(170, 100, 60), color.rgb(150, 140, 90)],
        'warehouse':    [color.rgb(100, 100, 95), color.rgb(110, 105, 100)],
    }
    default_colors = [color.rgb(100, 100, 110), color.rgb(90, 90, 100)]

    placed = []
    safety_gap = 6
    count = 0

    # ------------------------------------------------------------------
    # Ground first — this is the fix for the see-through world. A single
    # flat slab whose top is at y=0 (matching building base placement).
    # ------------------------------------------------------------------
    ground_margin = CFG.get('ground', {}).get('megacity', {}).get('margin', 60)
    build_ground(center=center, full_size=(size + ground_margin) * 2,
                 map_key='megacity')

    # Collect building *specs* (don't spawn entities yet) so we can either
    # batch them per-texture (few draw calls) or spawn them individually.
    # Each spec: (local_offset Vec3, scale tuple, color, texture_name)
    specs = []
    for gx in range(-size, size, spacing):
        for gz in range(-size, size, spacing):
            if abs(gx) < ex_x and abs(gz) < ex_z:
                continue
            if random.random() > density:
                continue

            btype_name, btype = _pick_building_type(types_cfg)
            w = random.uniform(btype['w_min'], btype['w_max'])
            d = random.uniform(btype['d_min'], btype['d_max'])
            h = random.uniform(btype['h_min'], btype['h_max'])
            ox = random.uniform(-1, 1)
            oz = random.uniform(-1, 1)
            bx = gx + ox
            bz = gz + oz
            hw = w / 2 + safety_gap
            hd = d / 2 + safety_gap

            overlap = False
            for px, pz, phw, phd in placed:
                if abs(bx - px) < (hw + phw) and abs(bz - pz) < (hd + phd):
                    overlap = True
                    break
            if overlap:
                continue
            placed.append((bx, bz, w / 2, d / 2))

            palette = color_palettes.get(btype_name, default_colors)
            col = random.choice(palette)
            specs.append((Vec3(bx, h / 2, bz), (w, h, d), col, btype['texture']))
            count += 1

    batch = CFG['city'].get('batch', True)
    _render_buildings(center, specs, tex_cache, batch)

    print(f'[MAP][megacity] {count} buildings, size={size*2}, spacing={spacing}, '
          f'batched={batch}')

    return {
        'spawn_points': [
            center + Vec3(0, 2, 0),
            center + Vec3(80, 2, 60),
            center + Vec3(-60, 2, 70),
        ],
        'bounds': (-size, size),
        'count': count,
    }
