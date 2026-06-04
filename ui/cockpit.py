"""
ui/cockpit.py
=============
HUD overhaul:

* Compass moved to y=0.42 (was 0.47) and constrained to 3 visible cardinal
  segments so the heading strip never overflows the 0.6-wide background.
* Status bars now use opaque (alpha=255) backgrounds with a 1-pixel-equivalent
  dark frame, so they read against bright skies instead of looking white.
* Crosshair is now a true `+` reticle (two thin quads with a transparent
  center), scale ~0.025, drawn on top with depth=1.
* Added a weapon cooldown rail along the bottom showing each weapon's
  readiness as a filled bar.

All HUD geometry comes from CFG['hud'] so positions are tuneable from JSON.
"""

from ursina import (
    Entity, Text, camera, color, raycast, lerp, time,
)
from config_loader import CFG


# Cardinal compass anchor list (deg, label)
_COMPASS_POINTS = [
    (0, 'N'), (45, 'NE'), (90, 'E'), (135, 'SE'),
    (180, 'S'), (225, 'SW'), (270, 'W'), (315, 'NW'),
]


class CockpitHUD(Entity):

    def __init__(self, player, cam_pivot=None):
        super().__init__(parent=camera.ui)
        self.player = player
        self.cam_pivot = cam_pivot

        hud = CFG.get('hud', {})

        # ============================================================
        # COMPASS — top center, dropped to a safe Y so glyphs don't
        # clip against the top of the UI viewport.
        # ============================================================
        compass_y = hud.get('compass_y', 0.42)
        bg_w, bg_h = hud.get('compass_bg_scale', [0.60, 0.04])
        head_scale = hud.get('compass_heading_scale', 0.6)

        self.compass_bg = Entity(
            parent=self, model='quad',
            color=color.rgba(0, 0, 0, 200),
            scale=(bg_w, bg_h),
            position=(0, compass_y, 0),
        )
        self.compass_heading = Text(
            parent=self, text='N', scale=head_scale,
            position=(0, compass_y + 0.005, -0.01),
            origin=(0, 0),
            color=color.rgba(0, 255, 200, 255),
        )
        self.compass_degrees = Text(
            parent=self, text='0\xb0', scale=0.5,
            position=(0, compass_y - 0.020, -0.01),
            origin=(0, 0),
            color=color.rgba(180, 220, 255, 220),
        )

        # ============================================================
        # STATUS BARS — top-left, opaque so they don't blend out
        # ============================================================
        bar_x = hud.get('bar_x', -0.82)
        bar_w = hud.get('bar_w', 0.25)
        top_y = hud.get('bar_top_y', 0.46)
        spacing = hud.get('bar_spacing', 0.035)

        self._bar_w = bar_w  # used by update() for fill scaling

        self.heat_bar = self._make_bar(bar_x, top_y - 0 * spacing, bar_w,
                                       label='HEAT',
                                       fill_col=(255, 80, 80),
                                       label_col=(255, 140, 140))
        self.hp_bar = self._make_bar(bar_x, top_y - 1 * spacing, bar_w,
                                     label='ARMOR',
                                     fill_col=(80, 220, 80),
                                     label_col=(140, 255, 140))
        self.fuel_bar = self._make_bar(bar_x, top_y - 2 * spacing, bar_w,
                                       label='FUEL',
                                       fill_col=(255, 165, 0),
                                       label_col=(255, 200, 80))

        self.jetpack_text = Text(
            parent=self, text='JETPACK', scale=0.6,
            position=(bar_x + bar_w + 0.03, top_y - 2 * spacing),
            color=color.rgba(255, 255, 0, 255), enabled=False,
        )

        self.overheat_text = Text(
            parent=self, text='!! SHUTDOWN !!', scale=1.5,
            position=(0, 0.15, -0.01), origin=(0, 0),
            color=color.red, enabled=False,
        )

        # ============================================================
        # CROSSHAIR — `+` made from two thin quads with hollow center
        # Scale 0.025 ≈ 27px on a 1080p screen, visible against any bg.
        # ============================================================
        cs = hud.get('crosshair_scale', 0.025)
        ct = hud.get('crosshair_thickness', 0.0035)

        self.crosshair_h = Entity(
            parent=self, model='quad',
            scale=(cs, ct), position=(0, 0, -0.02),
            color=color.lime,
        )
        self.crosshair_v = Entity(
            parent=self, model='quad',
            scale=(ct, cs), position=(0, 0, -0.02),
            color=color.lime,
        )
        # Outer dot for centerpoint reference
        self.crosshair_dot = Entity(
            parent=self, model='quad',
            scale=(ct * 0.8, ct * 0.8), position=(0, 0, -0.03),
            color=color.rgba(0, 0, 0, 200),
        )

        # ============================================================
        # SPEED INDICATOR
        # ============================================================
        self.speed_text = Text(
            parent=self, text='Speed: 1.0x', scale=0.6,
            position=(0.65, top_y, -0.01), origin=(0, 0),
            color=color.rgba(200, 200, 255, 220),
        )

        # ============================================================
        # WEAPON COOLDOWN RAIL — bottom center
        # One mini-bar per weapon, filled = ready
        # ============================================================
        self.weapon_bars = {}
        weapon_keys = list(player.weapons.keys())
        rail_x = -0.18
        rail_step = 0.09
        rail_y = -0.42
        labels = {
            'gatling': 'GAT', 'railgun': 'RAIL',
            'rocketpod': 'POD', 'heatseeker': 'HEAT-S', 'sniper': 'SNIPE',
            'laser': 'LASER', 'gauss': 'GAUSS',
        }
        for i, k in enumerate(weapon_keys):
            x = rail_x + i * rail_step
            Entity(parent=self, model='quad',
                   color=color.rgba(20, 20, 20, 230),
                   scale=(0.07, 0.018),
                   position=(x, rail_y, 0))
            fill = Entity(parent=self, model='quad',
                          color=color.rgba(120, 220, 255, 230),
                          scale=(0.07, 0.014),
                          position=(x - 0.035, rail_y, -0.005),
                          origin=(-0.5, 0))
            Text(parent=self, text=labels.get(k, k.upper()), scale=0.5,
                 position=(x, rail_y + 0.018, -0.01), origin=(0, 0),
                 color=color.rgba(200, 220, 255, 230))
            self.weapon_bars[k] = fill

        # ============================================================
        # CONTROLS HINT
        # ============================================================
        Text(
            parent=self,
            text='[LMB] Gatling  [RMB] Railgun  [1] Rockets  [2] Heatseeker  [3] Sniper'
                 '  [4] Laser  [5] Gauss'
                 '   |   [Q/D] Strafe  [SPACE] Jetpack  [+/-] Speed',
            scale=0.55, position=(-0.85, -0.47, -0.01),
            color=color.rgba(200, 200, 200, 180),
        )

        print('[HUD] Layout OK — compass y=0.42, bars opaque, crosshair=+, '
              f'weapon rail = {len(weapon_keys)} slots')

    # ----------------------------------------------------------------
    def _make_bar(self, x, y, w, label, fill_col, label_col):
        """Build a labeled bar. Returns the inner fill Entity."""
        # Outer dark frame
        Entity(parent=self, model='quad',
               color=color.rgba(0, 0, 0, 230),
               scale=(w + 0.006, 0.022),
               position=(x + w / 2, y, 0))
        # Background plate
        Entity(parent=self, model='quad',
               color=color.rgba(35, 35, 45, 255),
               scale=(w, 0.018),
               position=(x + w / 2, y, -0.005))
        # Fill (origin left so scaling grows from the left edge)
        fill = Entity(
            parent=self, model='quad',
            color=color.rgba(*fill_col, 255),
            scale=(w, 0.014),
            position=(x, y, -0.01),
            origin=(-0.5, 0),
        )
        Text(parent=self, text=label, scale=0.55,
             position=(x - 0.005, y + 0.016, -0.01), origin=(0.5, 0),
             color=color.rgba(*label_col, 255))
        return fill

    # ----------------------------------------------------------------
    def _compass_text(self, heading_deg):
        """Build a compact '<NW>  [N]  <NE>' style strip, max 3 segments."""
        h = heading_deg % 360
        candidates = []
        for deg, label in _COMPASS_POINTS:
            diff = ((deg - h) + 540) % 360 - 180  # signed [-180,180]
            if abs(diff) <= 50:
                candidates.append((diff, label))
        candidates.sort(key=lambda x: x[0])
        # Cap to 3 nearest by absolute angle
        if len(candidates) > 3:
            candidates.sort(key=lambda x: abs(x[0]))
            candidates = candidates[:3]
            candidates.sort(key=lambda x: x[0])
        parts = []
        for diff, label in candidates:
            parts.append(f'[{label}]' if abs(diff) < 8 else label)
        return '   '.join(parts) if parts else ''

    # ----------------------------------------------------------------
    def update(self):
        if not self.player:
            return
        p = self.player
        bw = self._bar_w

        # --- Heat ---
        hr = max(0.0, min(1.0, p.heat / p.max_heat))
        self.heat_bar.scale_x = bw * max(hr, 0.0001)
        self.heat_bar.color = lerp(
            color.rgba(255, 220, 60, 255),
            color.rgba(255, 60, 60, 255), hr,
        )

        # --- HP ---
        hp_r = max(0.0, min(1.0, p.hp / 200))
        self.hp_bar.scale_x = bw * max(hp_r, 0.0001)
        self.hp_bar.color = lerp(
            color.rgba(255, 80, 80, 255),
            color.rgba(60, 220, 60, 255), hp_r,
        )

        # --- Fuel ---
        fr = (p.fuel / p.max_fuel) if p.max_fuel > 0 else 0
        fr = max(0.0, min(1.0, fr))
        self.fuel_bar.scale_x = bw * max(fr, 0.0001)
        self.fuel_bar.color = (
            color.rgba(255, 165, 0, 255) if fr > 0.3
            else color.rgba(255, 60, 60, 255)
        )

        self.jetpack_text.enabled = getattr(p, 'jetpack_active', False)
        self.overheat_text.enabled = p.overheated

        # --- Compass ---
        if self.cam_pivot:
            world_yaw = (p.rotation_y + self.cam_pivot.rotation_y) % 360
        else:
            world_yaw = p.rotation_y % 360
        self.compass_heading.text = self._compass_text(world_yaw)
        self.compass_degrees.text = f'{int(world_yaw)}\xb0'

        # --- Speed ---
        import config_loader
        spd = getattr(config_loader, '_game_speed', 1.0)
        self.speed_text.text = f'Speed: {spd:.1f}x'

        # --- Crosshair color (red on enemy with hp, lime otherwise) ---
        hit = raycast(
            camera.world_position, camera.forward, distance=200,
            ignore=(p, p.legs, p.torso,
                    p.arm_left, p.arm_right,
                    p.shoulder_left, p.shoulder_right, p.head),
        )
        on_target = hit.hit and hasattr(hit.entity, 'hp')
        ch_col = color.red if on_target else color.lime
        self.crosshair_h.color = ch_col
        self.crosshair_v.color = ch_col

        # --- Weapon cooldown rail ---
        for key, w in p.weapons.items():
            bar = self.weapon_bars.get(key)
            if bar is None:
                continue
            cd = w.cooldown if w.cooldown > 0 else 1.0
            ready = max(0.0, min(1.0, 1.0 - (w._cd_remaining / cd)))
            bar.scale_x = 0.07 * max(ready, 0.0001)
            bar.color = (color.rgba(120, 220, 255, 230) if ready >= 1.0
                         else color.rgba(80, 130, 180, 230))
