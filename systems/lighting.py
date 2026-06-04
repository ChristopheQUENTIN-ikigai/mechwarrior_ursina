"""
systems/lighting.py
===================
Sky + sun + moon + ambient light, with named presets for scenarios.

Scenarios pick a preset by name in their JSON ("lighting": "day_clear").
Add a new preset = add an entry to LIGHTING_PRESETS, no code elsewhere
needs to change.

Each preset describes:
    sky_color (rgba) — base sky tint, omit to use default Ursina sky
    ambient (rgba)
    sun:    {direction, elevation_deg, distance, size, color, glow_layers}
    moon:   same shape (optional)

A LightingRig instance owns the entities and exposes update_celestial_follow()
which the camera_rig calls each frame to keep sun/moon at fixed sky positions.
"""

import math
from ursina import Entity, Sky, DirectionalLight, AmbientLight, Vec3, color


# =============================================================================
# Presets — extend freely
# =============================================================================
LIGHTING_PRESETS = {
    'day_clear': {
        'ambient': [110, 110, 130, 255],
        'sun': {
            'enabled': True, 'direction': 'east', 'elevation_deg': 45,
            'distance': 500, 'size': 30, 'color': [255, 230, 80],
            'glow_layers': [(2.5, 50), (5, 20), (8, 8)],
        },
        'moon': {
            'enabled': True, 'direction': 'west', 'elevation_deg': 45,
            'distance': 500, 'size': 15, 'color': [200, 210, 255],
            'glow_layers': [(2.0, 30), (4.0, 12)],
        },
    },
    'dusk_orange': {
        'ambient': [120, 90, 80, 255],
        'sun': {
            'enabled': True, 'direction': 'west', 'elevation_deg': 12,
            'distance': 500, 'size': 50, 'color': [255, 140, 60],
            'glow_layers': [(2.5, 80), (5, 40), (10, 15)],
        },
        'moon': {
            'enabled': True, 'direction': 'east', 'elevation_deg': 25,
            'distance': 500, 'size': 18, 'color': [220, 220, 255],
            'glow_layers': [(2.0, 30), (4.0, 12)],
        },
    },
    'night_moon': {
        'ambient': [40, 45, 70, 255],
        'sun':  {'enabled': False},
        'moon': {
            'enabled': True, 'direction': 'south', 'elevation_deg': 60,
            'distance': 500, 'size': 24, 'color': [220, 230, 255],
            'glow_layers': [(2.5, 60), (5, 25), (8, 10)],
        },
    },
    'arena_neutral': {
        # Flat well-lit ambient for arena duels — no harsh shadows
        'ambient': [180, 180, 190, 255],
        'sun': {
            'enabled': True, 'direction': 'east', 'elevation_deg': 80,
            'distance': 500, 'size': 25, 'color': [255, 250, 230],
            'glow_layers': [(2.0, 30), (4, 12)],
        },
        'moon': {'enabled': False},
    },
    'canyon_overcast': {
        'ambient': [130, 130, 140, 255],
        'sun': {
            'enabled': True, 'direction': 'east', 'elevation_deg': 70,
            'distance': 500, 'size': 28, 'color': [220, 220, 230],
            'glow_layers': [(2.0, 25), (4, 10)],
        },
        'moon': {'enabled': False},
    },
}


# =============================================================================
class LightingRig:
    def __init__(self, preset_name='day_clear'):
        if preset_name not in LIGHTING_PRESETS:
            print(f'[LIGHT] Unknown preset {preset_name!r}, falling back to day_clear')
            preset_name = 'day_clear'
        self.preset_name = preset_name
        self.preset = LIGHTING_PRESETS[preset_name]

        self.sky = Sky()
        self._celestials = []  # [(entity, offset_vec3)]
        self.sun_pos = Vec3(0, 100, 0)

        # Sun
        sun_cfg = self.preset.get('sun', {})
        if sun_cfg.get('enabled', False):
            _, self.sun_pos = self._make_celestial(sun_cfg, name='sun')

        # Moon
        moon_cfg = self.preset.get('moon', {})
        if moon_cfg.get('enabled', False):
            self._make_celestial(moon_cfg, name='moon')

        # Directional + ambient lights
        self.dir_light = DirectionalLight()
        self.dir_light.look_at(Vec3(0, 0, 0) - self.sun_pos)

        amb = self.preset.get('ambient', [110, 110, 130, 255])
        self.ambient = AmbientLight(color=color.rgba(*amb))

        # Render bin fix: keep sky in background, celestials in fixed bin
        self._fix_render_bins()

        print(f'[LIGHT] preset={preset_name}  celestials={len(self._celestials)}')

    # ------------------------------------------------------------
    def _make_celestial(self, cfg, name='body'):
        dir_map = {'north': (0, 1), 'south': (0, -1),
                   'east': (1, 0),  'west': (-1, 0)}
        direction = cfg.get('direction', 'east')
        dx, dz = dir_map.get(direction, (1, 0))
        elev = math.radians(cfg.get('elevation_deg', 45))
        dist = cfg.get('distance', 500)
        size = cfg.get('size', 30)
        col_rgb = cfg.get('color', [255, 230, 80])

        y = math.sin(elev) * dist
        horiz = math.cos(elev) * dist
        offset = Vec3(dx * horiz, y, dz * horiz)

        body = Entity(
            model='sphere', scale=size, position=offset,
            color=color.rgb(*col_rgb),
            lit=False, unlit=True, double_sided=True,
        )
        self._celestials.append((body, Vec3(offset)))

        for glow_scale, glow_alpha in cfg.get('glow_layers', []):
            g = Entity(
                model='sphere', scale=size * glow_scale, position=offset,
                color=color.rgba(col_rgb[0], col_rgb[1], col_rgb[2], glow_alpha),
                lit=False, unlit=True, double_sided=True,
            )
            self._celestials.append((g, Vec3(offset)))

        print(f'[LIGHT][{name.upper()}] dir={direction} elev={cfg.get("elevation_deg")} '
              f'dist={dist} size={size}')
        return body, offset

    def _fix_render_bins(self):
        try:
            self.sky.setDepthWrite(False)
            self.sky.setBin('background', 0)
            for ent, _ in self._celestials:
                ent.setBin('fixed', 10)
                ent.setDepthWrite(False)
                ent.setDepthTest(False)
        except Exception as e:
            print(f'[LIGHT] render-bin setup failed: {e}')

    # ------------------------------------------------------------
    def update_celestial_follow(self, cam_world_pos):
        """Reposition all celestial bodies relative to camera each frame."""
        for ent, offset in self._celestials:
            ent.world_position = cam_world_pos + offset

    # ------------------------------------------------------------
    def teardown(self):
        from ursina import destroy
        for ent, _ in self._celestials:
            destroy(ent)
        self._celestials.clear()
        if self.sky:
            destroy(self.sky)
        self.sky = None
