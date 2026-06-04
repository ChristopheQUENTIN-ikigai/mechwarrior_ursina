"""
systems/camera_rig.py
=====================
Third-person camera follow rig.

Builds a pivot Entity parented to a target (the player), parents the
Ursina camera to that pivot, and exposes:
    update(dt, mouse_velocity)  - apply mouse look, smooth zoom, collide
    zoom_in() / zoom_out()       - cycle zoom by config 'zoom_speed'

The rig owns no game state — pure presentation. Scenarios can swap rigs
(e.g. cockpit-view subclass) without touching anything else.
"""

from ursina import Entity, camera, raycast, lerp, clamp, Vec3


class CameraRig:
    def __init__(self, target, cfg, ignore_entities=()):
        """
        target: Entity to follow (usually the player mech)
        cfg: dict from CFG['camera']
        ignore_entities: tuple of entities raycast should ignore
        """
        self.target = target
        self.cfg = cfg
        self.ignore = tuple(ignore_entities)

        self.pivot = Entity(parent=target, y=cfg['pivot_height'])
        self.pivot.rotation_y = 0
        camera.parent = self.pivot
        camera.rotation = (cfg.get('pitch', 15), 0, 0)

        self._cam_distance = cfg['default_distance']
        self._cam_current_dist = self._cam_distance
        camera.position = (0, cfg['height_offset'], -self._cam_distance)
        print(f'[CAM] dist={self._cam_distance} pivot_h={cfg["pivot_height"]}')

    # ------------------------------------------------------------
    def zoom_in(self):
        c = self.cfg
        self._cam_distance = max(c['min_distance'],
                                 self._cam_distance - c['zoom_speed'])

    def zoom_out(self):
        c = self.cfg
        self._cam_distance = min(c['max_distance'],
                                 self._cam_distance + c['zoom_speed'])

    # ------------------------------------------------------------
    def update(self, dt, mouse_velocity, mouse_cfg):
        c = self.cfg

        # --- Mouse look on pivot ---
        self.pivot.rotation_y += mouse_velocity[0] * mouse_cfg['sensitivity_x']
        self.pivot.rotation_x -= mouse_velocity[1] * mouse_cfg['sensitivity_y']
        self.pivot.rotation_x = clamp(
            self.pivot.rotation_x, c['pitch_min'], c['pitch_max'],
        )

        # --- Smooth zoom ---
        self._cam_current_dist = lerp(
            self._cam_current_dist, self._cam_distance,
            dt * c['zoom_smooth'],
        )
        base_h = c['height_offset']
        extra_h = (self._cam_current_dist - c['min_distance']) * c.get('height_per_zoom', 0.3)
        target_offset = Vec3(0, base_h + extra_h, -self._cam_current_dist)

        # --- Camera collision (push closer if wall in the way) ---
        origin = self.target.world_position + Vec3(0, c['pivot_height'], 0)
        cam_world = camera.world_position
        delta = cam_world - origin
        dist = delta.length()
        if dist > 0.1:
            direction = delta.normalized()
            hit = raycast(origin, direction, distance=dist, ignore=self.ignore)
            if hit.hit:
                safe = hit.world_point - self.pivot.world_position
                camera.position = lerp(
                    camera.position, safe * 0.85,
                    dt * c['collision_smooth'],
                )
            else:
                camera.position = lerp(
                    camera.position, target_offset,
                    dt * c['return_smooth'],
                )

    # ------------------------------------------------------------
    @property
    def world_position(self):
        return camera.world_position
