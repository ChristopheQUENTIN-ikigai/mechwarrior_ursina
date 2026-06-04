"""
entities/player_mech.py
=======================
Mech body assembly (legs / torso / head / 2 arms / 2 shoulder pods)
plus a `hardpoints` dict mapping slot name -> empty Entity at the muzzle.

Hardpoint names:
    arm_left, arm_right       -> arm-mounted weapons (gatling, railgun, sniper)
    shoulder_left, shoulder_right -> shoulder-mounted (rocketpod, heatseeker)

Weapons spawn projectiles at hardpoints[slot].world_position, so a
gatling barks from the right arm muzzle while a heatseeker leaves
the left shoulder pod.
"""

from ursina import Entity, Vec3, raycast, color, time, camera
import math

from config_loader import CFG, any_held
from systems.weapons import make_weapons
from systems.tex_gen import get_texture

_dbg_frame = 0


class PlayerMech(Entity):

    def __init__(self, loadout=None):
        pcfg = CFG['player']
        super().__init__(position=Vec3(*pcfg['spawn_position']))

        # ---------------- BODY ----------------
        # Legs are the rotating base. Their scale of (2,2,2) is preserved.
        self.legs = Entity(
            parent=self, model='cube', scale=(2, 2, 2),
            texture=get_texture('mech_legs'), color=color.azure,
        )

        # Torso sits on top of the legs and is the parent for everything
        # that swings with the camera (head, arms, shoulders, hardpoints).
        self.torso = Entity(
            parent=self.legs, y=2, model='cube', scale=(2, 2, 2),
            texture=get_texture('mech_torso'), color=color.blue,
        )

        # Note: torso scale (2,2,2) inherits from legs, so torso world scale
        # is (2*2, 2*2, 2*2) = (4,4,4). Children of torso need to compensate
        # — we use absolute world_scale via setting their .scale relative
        # to torso's local space (1 unit = 4 world units). To keep this
        # readable we attach decorative parts directly to `self.legs` (so
        # 1 unit = 2 world units) instead of nesting under torso.

        # Head — small cube above torso. Parent it to torso so it tilts
        # with the upper body even though we don't actually animate that.
        self.head = Entity(
            parent=self.torso,
            model='cube',
            position=(0, 0.55, 0.15),     # local to torso
            scale=(0.5, 0.35, 0.55),
            color=color.rgb(40, 60, 90),
        )

        # Arms — vertical slabs hanging off the torso sides.
        # In torso local space, x=±0.55 puts them just outside the torso cube.
        self.arm_right = Entity(
            parent=self.torso,
            model='cube',
            position=(0.65, 0.0, 0.0),
            scale=(0.35, 1.05, 0.4),
            color=color.rgb(60, 70, 110),
        )
        self.arm_left = Entity(
            parent=self.torso,
            model='cube',
            position=(-0.65, 0.0, 0.0),
            scale=(0.35, 1.05, 0.4),
            color=color.rgb(60, 70, 110),
        )

        # Shoulder pods — chunky boxes sitting on top of the arms.
        self.shoulder_right = Entity(
            parent=self.torso,
            model='cube',
            position=(0.55, 0.45, -0.05),
            scale=(0.55, 0.35, 0.6),
            color=color.rgb(90, 50, 50),
        )
        self.shoulder_left = Entity(
            parent=self.torso,
            model='cube',
            position=(-0.55, 0.45, -0.05),
            scale=(0.55, 0.35, 0.6),
            color=color.rgb(50, 90, 50),
        )

        # ---------------- HARDPOINTS ----------------
        # Empty Entity at each muzzle. Children of the relevant body part
        # so they swing with it. Z is forward in Ursina => positive Z =
        # in front of the part.
        self.hardpoints = {
            'arm_right':       Entity(parent=self.arm_right,      position=(0, -0.5, 0.6)),
            'arm_left':        Entity(parent=self.arm_left,       position=(0, -0.5, 0.6)),
            'shoulder_right':  Entity(parent=self.shoulder_right, position=(0, 0, 0.55)),
            'shoulder_left':   Entity(parent=self.shoulder_left,  position=(0, 0, 0.55)),
        }

        # Every body part in one tuple — the single ignore set for all raycasts
        # (movement, gravity, aiming, HUD, weapon hitscan) so the mech can never
        # collide with or shoot itself.
        self._parts = [
            self.legs, self.torso, self.head,
            self.arm_left, self.arm_right,
            self.shoulder_left, self.shoulder_right,
            *self.hardpoints.values(),
        ]

        # ---------------- STATS ----------------
        self.speed = pcfg['speed']
        self.strafe_speed = pcfg.get('strafe_speed', 4.5)
        self.turn_speed = pcfg['turn_speed']
        self.collision_margin = pcfg['collision_margin']

        self.hp = pcfg['hp']
        self.heat = 0
        self.max_heat = pcfg['max_heat']
        self.heat_dissipation = pcfg['heat_dissipation']
        self.overheated = False

        # Jetpack / gravity
        self.gravity = pcfg.get('gravity', 20)
        self.jetpack_thrust = pcfg.get('jetpack_thrust', 18)
        self.velocity_y = 0
        self.grounded = False
        self.fuel = pcfg.get('max_fuel', 100)
        self.max_fuel = pcfg.get('max_fuel', 100)
        self.fuel_burn_rate = pcfg.get('fuel_burn_rate', 25)
        self.fuel_regen_rate = pcfg.get('fuel_regen_rate', 10)
        self.jetpack_active = False

        # ---------------- WEAPONS ----------------
        # weapons is a dict keyed by config name: 'gatling','railgun',...
        self.weapons = make_weapons(self, loadout=loadout)

        # cam_pivot is set by main.py after construction; used so the
        # torso (and therefore arms/hardpoints) yaw with the mouse look.
        self.cam_pivot = None

        print(f'[MECH] Spawned at {self.position}')
        print(f'[MECH] Hardpoints: {list(self.hardpoints.keys())}')

    # =========================================================
    # Frame update
    # =========================================================
    def update(self):
        global _dbg_frame
        _dbg_frame += 1

        # --- weapon cooldowns ---
        for w in self.weapons.values():
            w.tick(time.dt)

        # --- heat dissipation ---
        self.heat = max(0, self.heat - time.dt * self.heat_dissipation)
        if self.overheated and self.heat <= 0:
            self.overheated = False

        if self.overheated:
            self._apply_gravity()
            return

        # ---- movement (camera-relative, XZ plane only) ----
        cam_fwd_raw = camera.forward
        cam_right_raw = camera.right
        cam_fwd = Vec3(cam_fwd_raw.x, 0, cam_fwd_raw.z)
        cam_right = Vec3(cam_right_raw.x, 0, cam_right_raw.z)
        if cam_fwd.length() > 0.001:
            cam_fwd = cam_fwd.normalized()
        if cam_right.length() > 0.001:
            cam_right = cam_right.normalized()

        move_dir = Vec3(0, 0, 0)
        if any_held('forward'):       move_dir += cam_fwd
        if any_held('backward'):      move_dir -= cam_fwd
        if any_held('strafe_left'):   move_dir -= cam_right
        if any_held('strafe_right'):  move_dir += cam_right
        if move_dir.length() > 0:
            move_dir = move_dir.normalized()

        if move_dir.length() > 0:
            blocked = False
            for offset in [Vec3(0, 1, 0), Vec3(-1, 1, 0), Vec3(1, 1, 0)]:
                hit = raycast(
                    self.position + offset, move_dir,
                    distance=(self.speed * time.dt) + self.collision_margin,
                    ignore=(self, self.legs, self.torso,
                            self.arm_left, self.arm_right,
                            self.shoulder_left, self.shoulder_right,
                            self.head),
                )
                if hit.hit:
                    blocked = True
                    break
            if not blocked:
                self.position += move_dir * self.speed * time.dt

        # --- turning (legs yaw) ---
        if any_held('turn_left'):
            self.rotation_y -= self.turn_speed * time.dt
        if any_held('turn_right'):
            self.rotation_y += self.turn_speed * time.dt

        # --- torso yaws with camera so arms/hardpoints aim where you look ---
        if self.cam_pivot is not None:
            # Local yaw of torso relative to legs = cam_pivot yaw - legs yaw
            self.torso.rotation_y = self.cam_pivot.rotation_y - self.rotation_y
            # Slight pitch follow so muzzles tip up/down a bit
            self.torso.rotation_x = self.cam_pivot.rotation_x * 0.4

        self._apply_gravity()

    # =========================================================
    def _apply_gravity(self):
        dt = time.dt
        self.jetpack_active = any_held('jetpack') and self.fuel > 0
        if self.jetpack_active:
            self.velocity_y += self.jetpack_thrust * dt
            self.fuel = max(0, self.fuel - self.fuel_burn_rate * dt)
        else:
            self.velocity_y -= self.gravity * dt
        self.y += self.velocity_y * dt

        ground_hit = raycast(
            self.position + Vec3(0, 50, 0), Vec3(0, -1, 0),
            distance=100,
            ignore=(self, self.legs, self.torso,
                    self.arm_left, self.arm_right,
                    self.shoulder_left, self.shoulder_right, self.head),
        )
        ground_y = ground_hit.world_point.y + 2 if ground_hit.hit else 2

        if self.y <= ground_y:
            self.y = ground_y
            self.velocity_y = 0
            self.grounded = True
        else:
            self.grounded = False

        if self.grounded and not self.jetpack_active:
            self.fuel = min(self.max_fuel, self.fuel + self.fuel_regen_rate * dt)

    # =========================================================
    # NOTE: weapon firing is wired entirely through InputRouter
    # (core/game.py::_wire_input), which binds only the weapons the player
    # actually carries. The old Entity.input() handler here hard-referenced
    # self.weapons['rocketpod'/'heatseeker'/'sniper'] and crashed with a
    # KeyError on partial loadouts (e.g. arena_duel), besides double-firing
    # everything. It has been removed.
    # =========================================================
    def add_heat(self, amount):
        self.heat += amount
        if self.heat >= self.max_heat:
            self.overheated = True
        try:
            from core.events import bus
            bus.publish('player.heat_changed', player=self, heat=self.heat)
        except ImportError:
            pass

    def take_damage(self, amount, source=None):
        self.hp -= amount
        try:
            from core.events import bus
            if self.hp <= 0:
                bus.publish('player.killed', player=self, by=source)
            else:
                bus.publish('player.damaged', player=self, amount=amount, by=source)
        except ImportError:
            pass

    # Continuous-fire support: any weapon flagged "continuous" in config fires
    # while its bound key is held (its own cooldown limits the rate of fire).
    # Called by Game.update() each frame after the player is built.
    def update_continuous_fire(self):
        if self.overheated:
            return
        for wkey, w in self.weapons.items():
            if getattr(w, 'continuous', False) and any_held(f'fire_{wkey}'):
                w.fire()
