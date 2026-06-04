"""
systems/weapons.py
==================
Config-driven weapon system supporting 4 firing types:
  - projectile : travels in a straight line (gatling)
  - hitscan    : instant beam (railgun, sniper)
  - salvo      : fires N projectiles in sequence (rocketpod)
  - homing     : projectile that steers toward a locked target (heatseeker)

Each weapon reads its config block (including a 'hardpoint' key naming an arm/
shoulder slot on the player mech). Projectiles spawn at that hardpoint's
world position, NOT at the torso center. Cooldowns prevent rapid spam.
"""

from ursina import (
    Entity, Vec3, raycast, color, time, destroy, lerp, invoke,
    distance as ursina_distance,
)
import math
import random

from config_loader import CFG


# =============================================================================
# Helpers
# =============================================================================

def _aim_direction():
    """Direction the camera is currently looking — single source of truth for aim."""
    from ursina import camera
    return camera.forward


def _hardpoint_world_pos(mech, hardpoint_name):
    """Return the world position of a named hardpoint, falling back to torso."""
    hp = getattr(mech, 'hardpoints', {}).get(hardpoint_name)
    if hp is not None:
        return hp.world_position
    return mech.torso.world_position


def _spread(direction, deg):
    """Apply a small random angular spread (in degrees) to a unit direction."""
    if deg <= 0:
        return direction
    rad = math.radians(deg)
    yaw = random.uniform(-rad, rad)
    pitch = random.uniform(-rad, rad)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    # rotate around Y then X — small-angle, order doesn't matter much
    x = direction.x * cy + direction.z * sy
    z = -direction.x * sy + direction.z * cy
    y = direction.y * cp - z * sp
    z = direction.y * sp + z * cp
    return Vec3(x, y, z).normalized()


def _find_homing_target(origin, forward, lock_range, cone_deg):
    """Pick the nearest entity with hp inside a cone in front of the player."""
    from ursina import scene
    cos_cone = math.cos(math.radians(cone_deg))
    best = None
    best_dist = lock_range
    for ent in scene.entities:
        hp = getattr(ent, 'hp', None)
        if not isinstance(hp, (int, float)):
            continue
        delta = ent.world_position - origin
        d = delta.length()
        if d < 0.5 or d > best_dist:
            continue
        unit = delta / d
        dot = unit.x * forward.x + unit.y * forward.y + unit.z * forward.z
        if dot < cos_cone:
            continue
        if d < best_dist:
            best_dist = d
            best = ent
    return best


def _damage_entity(target, amount, source=None):
    """Apply damage to a target, preferring its take_damage() hook so that
    enemy.killed / player.killed / player.damaged events get published.
    Falls back to a raw hp decrement for entities without the hook.
    """
    if target is None:
        return
    hook = getattr(target, 'take_damage', None)
    if callable(hook):
        hook(amount, source)
        return
    hp = getattr(target, 'hp', None)
    if isinstance(hp, (int, float)):
        target.hp = hp - amount
        if target.hp <= 0:
            destroy(target)


# =============================================================================
# Projectiles
# =============================================================================

class Projectile(Entity):
    """Plain-vanilla straight-line projectile."""
    def __init__(self, pos, direction, speed, damage, col, scale_v, model, owner=None):
        super().__init__(model=model, scale=scale_v, color=col, position=pos)
        self.dir = direction
        self.speed = speed
        self.damage = damage
        self.life = 4
        self.owner = owner
        # Ignore the projectile itself, its shooter, and the shooter's body
        # parts — prevents a round detonating on the muzzle/own legs and stops
        # enemies from killing themselves with their own fire.
        ig = [self]
        if owner is not None:
            ig.append(owner)
            ig.extend(getattr(owner, '_parts', ()))
        self._ignore = tuple(ig)

    def update(self):
        step = self.speed * time.dt
        hit = raycast(self.position, self.dir, distance=step + 0.5, ignore=self._ignore)
        if hit.hit:
            self._on_hit(hit)
            return
        self.position += self.dir * step
        self.life -= time.dt
        if self.life <= 0:
            destroy(self)

    def _on_hit(self, hit):
        target = hit.entity
        if isinstance(getattr(target, 'hp', None), (int, float)):
            _damage_entity(target, self.damage, self.owner)
        elif getattr(target, 'tag', None) == 'building' and not getattr(target, 'batched', False):
            # cosmetic damage only for individually-spawned buildings
            target.color = lerp(target.color, color.dark_gray, 0.3)
            target.scale_y *= 0.95
        destroy(self)


class HomingProjectile(Projectile):
    """Steers toward a locked target each frame."""
    def __init__(self, pos, direction, speed, damage, col, scale_v, model,
                 target, turn_rate_deg, owner=None):
        super().__init__(pos, direction, speed, damage, col, scale_v, model, owner=owner)
        self.target = target
        self.turn_rate = math.radians(turn_rate_deg)
        self.life = 6

    def update(self):
        if self.target is not None and self.target.enabled:
            desired = (self.target.world_position - self.world_position)
            if desired.length() > 0.01:
                desired = desired.normalized()
                # rotate self.dir toward desired by at most turn_rate * dt
                cur = self.dir.normalized()
                dot = max(-1.0, min(1.0, cur.x*desired.x + cur.y*desired.y + cur.z*desired.z))
                angle = math.acos(dot)
                max_step = self.turn_rate * time.dt
                if angle <= max_step:
                    self.dir = desired
                else:
                    t = max_step / angle
                    self.dir = Vec3(
                        cur.x + (desired.x - cur.x) * t,
                        cur.y + (desired.y - cur.y) * t,
                        cur.z + (desired.z - cur.z) * t,
                    ).normalized()
        super().update()


class HitscanBeam(Entity):
    """A short-lived visual beam from origin to hit point (or far point)."""
    def __init__(self, origin, end, col, thickness, lifetime):
        mid = (origin + end) * 0.5
        delta = end - origin
        length = delta.length()
        super().__init__(
            model='cube', color=col, position=mid,
            scale=(thickness, thickness, max(length, 0.01)),
        )
        if length > 0.01:
            self.look_at(end)
        self.life = lifetime

    def update(self):
        self.life -= time.dt
        a = max(0, min(1, self.life / 0.3))
        c = self.color
        self.color = color.rgba(c.r * 255, c.g * 255, c.b * 255, int(255 * a))
        if self.life <= 0:
            destroy(self)


# =============================================================================
# Weapon class — one class, behavior selected by config 'type'
# =============================================================================

def _resolve_weapon_cfg(key):
    """Look up a weapon config: CFG first, then registry (for mod-added weapons)."""
    if key in CFG.get('weapons', {}):
        return CFG['weapons'][key]
    try:
        from core.registry import registry
        return registry.get_weapon(key)
    except (ImportError, KeyError):
        raise KeyError(f'Weapon {key!r} not found in CFG or registry')


class Weapon:
    def __init__(self, mech, key):
        self.mech = mech
        self.key = key
        self.cfg = _resolve_weapon_cfg(key)
        self.type = self.cfg['type']
        self.hardpoint = self.cfg.get('hardpoint', 'arm_right')
        self.cooldown = self.cfg.get('cooldown', 0.2)
        self.continuous = self.cfg.get('continuous', False)
        self._cd_remaining = 0.0
        self._charging = False
        print(f'[WEAPON] {key}: type={self.type} hardpoint={self.hardpoint} '
              f'cooldown={self.cooldown}s continuous={self.continuous}')

    # --- frame tick: drain cooldown ---
    def tick(self, dt):
        if self._cd_remaining > 0:
            self._cd_remaining -= dt

    # --- public fire ---
    def fire(self):
        if self._cd_remaining > 0 or self._charging:
            return
        if self.mech.overheated:
            return

        if self.type == 'hitscan':
            self._fire_hitscan()
        elif self.type == 'projectile':
            self._fire_projectile()
        elif self.type == 'salvo':
            self._fire_salvo()
        elif self.type == 'homing':
            self._fire_homing()
        else:
            print(f'[WEAPON] unknown type {self.type}')
            return

        self._cd_remaining = self.cooldown

    # ----- type implementations -----

    def _fire_projectile(self):
        c = self.cfg
        self.mech.add_heat(c['heat'])
        origin = _hardpoint_world_pos(self.mech, self.hardpoint)
        aim = _spread(_aim_direction(), c.get('spread_deg', 0))
        Projectile(
            origin + aim * 1.2, aim,
            c['speed'], c['damage'],
            color.rgb(*c['color']), c['scale'], c['model'],
            owner=self.mech,
        )

    def _fire_salvo(self):
        c = self.cfg
        n = c.get('salvo_count', 4)
        interval = c.get('salvo_interval', 0.1)
        self.mech.add_heat(c['heat'])  # one heat hit for the whole salvo
        for i in range(n):
            invoke(self._spawn_salvo_round, delay=i * interval)

    def _spawn_salvo_round(self):
        c = self.cfg
        origin = _hardpoint_world_pos(self.mech, self.hardpoint)
        aim = _spread(_aim_direction(), c.get('spread_deg', 4))
        Projectile(
            origin + aim * 1.2, aim,
            c['speed'], c['damage'],
            color.rgb(*c['color']), c['scale'], c['model'],
            owner=self.mech,
        )

    def _fire_hitscan(self):
        c = self.cfg
        charge = c.get('charge_time', 0.0)
        if charge > 0:
            self._charging = True
            invoke(self._do_hitscan, delay=charge)
        else:
            self._do_hitscan()

    def _do_hitscan(self):
        self._charging = False
        c = self.cfg
        self.mech.add_heat(c['heat'])
        origin = _hardpoint_world_pos(self.mech, self.hardpoint)
        aim = _aim_direction()
        ignore = (self.mech,) + tuple(getattr(self.mech, '_parts', ()))
        hit = raycast(origin, aim, distance=2000, ignore=ignore)
        end = hit.world_point if hit.hit else origin + aim * 2000
        HitscanBeam(
            origin, end,
            color.rgb(*c['beam_color']),
            c.get('beam_thickness', 0.1),
            c.get('beam_lifetime', 0.2),
        )
        if hit.hit and isinstance(getattr(hit.entity, 'hp', None), (int, float)):
            _damage_entity(hit.entity, c['damage'], self.mech)

    def _fire_homing(self):
        c = self.cfg
        self.mech.add_heat(c['heat'])
        origin = _hardpoint_world_pos(self.mech, self.hardpoint)
        aim = _aim_direction()
        target = _find_homing_target(
            origin, aim,
            c.get('lock_range', 100),
            c.get('lock_cone_deg', 25),
        )
        HomingProjectile(
            origin + aim * 1.2, aim,
            c['speed'], c['damage'],
            color.rgb(*c['color']), c['scale'], c['model'],
            target, c.get('turn_rate_deg_per_sec', 120),
            owner=self.mech,
        )
        if target is None:
            print(f'[{self.key.upper()}] no lock — fired dumb')


# Backwards-compat shims — old class names referenced elsewhere.
# Now everything goes through Weapon(mech, key).
def make_weapons(mech, loadout=None):
    """Return a dict {key: Weapon} for the requested loadout.

    If `loadout` is None, all weapons in CFG['weapons'] are instantiated.
    Otherwise `loadout` is a list of weapon ids (which may include mod-
    added weapons resolved via the registry).
    """
    if loadout is None:
        loadout = list(CFG.get('weapons', {}).keys())
    return {key: Weapon(mech, key) for key in loadout}
