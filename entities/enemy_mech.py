"""
entities/enemy_mech.py
======================
Base enemy mech, registered as 'patrol_mech'.

Scenarios reference enemies by id in their JSON:
    "enemy_groups": [{ "type": "patrol_mech", "count": 4, ... }]

To add a new enemy variant, subclass and register:

    @registry.enemy('sniper_mech')
    class SniperMech(EnemyMech):
        def __init__(self, pos):
            super().__init__(pos)
            self.attack_range = 80
            self.fire_cooldown_max = 3.0
"""

import random
from ursina import Entity, Vec3, color, time, scene, destroy, raycast

from config_loader import CFG
from systems.weapons import Projectile
from systems.tex_gen import get_texture
from core.events import bus
from core.registry import registry


# Cache the player entity so every enemy doesn't rescan the whole scene each
# frame (that was O(entities * enemies) per frame). Validated cheaply each call;
# rescans only when the cached reference is gone (e.g. new scenario).
_player_ref = None


def _get_player():
    global _player_ref
    p = _player_ref
    try:
        if p is not None and p.enabled:
            return p
    except Exception:
        pass
    _player_ref = None
    for e in scene.entities:
        if hasattr(e, 'weapons') and not isinstance(e, EnemyMech):
            _player_ref = e
            return e
    return None


@registry.enemy('patrol_mech')
class EnemyMech(Entity):

    def __init__(self, pos, **overrides):
        ecfg = dict(CFG['enemies'])
        ecfg.update(overrides)  # scenarios can pass per-enemy overrides

        super().__init__(
            model='cube', color=color.orange,
            scale=(2, 4, 2), position=pos,
            collider='box',
            texture=get_texture('enemy'),
        )
        self.hp = ecfg['hp']
        self.max_hp = ecfg['hp']
        self.speed = ecfg['speed']
        self.attack_range = ecfg['attack_range']
        self.chase_range = ecfg['chase_range']
        self.fire_cooldown = 0
        self.fire_cooldown_max = ecfg['fire_cooldown']
        self.proj_speed = ecfg['projectile_speed']
        self.proj_damage = ecfg['projectile_damage']
        self.state = 'patrol'
        self.patrol_target = self.position + Vec3(
            random.randint(-20, 20), 0, random.randint(-20, 20),
        )

        # Rest on the ground rather than floating / sinking. Floor top comes
        # from config; clamp so the cube's base sits on it.
        self._ground_y = CFG.get('ground', {}).get('y_top', 0.0)
        floor = self._ground_y + self.scale_y / 2.0
        if self.y < floor:
            self.y = floor

    def _find_player(self):
        return _get_player()

    def _has_line_of_sight(self, player):
        """True if nothing solid sits between this enemy and the player."""
        origin = self.world_position + Vec3(0, 2, 0)
        target = player.world_position + Vec3(0, 1, 0)
        delta = target - origin
        dist = delta.length()
        if dist < 0.001:
            return True
        hit = raycast(origin, delta.normalized(), distance=dist, ignore=(self,))
        if not hit.hit:
            return True
        ent = hit.entity
        return ent is player or ent in getattr(player, '_parts', ())

    def update(self):
        if self.hp <= 0:
            return

        player = self._find_player()
        if not player:
            return

        dist = (player.position - self.position).length()
        self.fire_cooldown = max(0, self.fire_cooldown - time.dt)

        if dist < self.attack_range:
            self.state = 'attack'
        elif dist < self.chase_range:
            self.state = 'chase'
        else:
            self.state = 'patrol'

        if self.state == 'patrol':
            d = self.patrol_target - self.position
            if d.length() < 3:
                self.patrol_target = self.position + Vec3(
                    random.randint(-20, 20), 0, random.randint(-20, 20),
                )
            else:
                self.look_at_2d(self.patrol_target)
                self.position += self.forward * self.speed * 0.5 * time.dt

        elif self.state == 'chase':
            self.look_at_2d(player.position)
            self.position += self.forward * self.speed * time.dt

        elif self.state == 'attack':
            self.look_at_2d(player.position)
            self.position += self.right * self.speed * 0.3 * time.dt
            if self.fire_cooldown <= 0 and self._has_line_of_sight(player):
                self._fire_at_player(player)
                self.fire_cooldown = self.fire_cooldown_max

        # Keep planted on the floor (movement is horizontal, but clamp anyway).
        floor = self._ground_y + self.scale_y / 2.0
        if self.y < floor:
            self.y = floor

        # Damage tint
        self.color = color.red if self.hp < self.max_hp * 0.4 else color.orange

    def _fire_at_player(self, player):
        """Spawn an enemy projectile aimed at the player's center mass."""
        muzzle = self.world_position + Vec3(0, 2, 0) + self.forward * 2
        target = player.world_position + Vec3(0, 1, 0)
        aim = target - muzzle
        aim = aim.normalized() if aim.length() > 0.001 else self.forward
        Projectile(
            muzzle, aim,
            self.proj_speed, self.proj_damage,
            color.red, 0.3, 'cube',
            owner=self,
        )

    def take_damage(self, amount, source=None):
        self.hp -= amount
        if self.hp <= 0:
            bus.publish('enemy.killed', enemy=self, by=source)
            destroy(self)
