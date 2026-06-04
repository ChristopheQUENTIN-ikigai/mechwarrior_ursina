"""
core/game.py
============
Game orchestrator.

Owns the Ursina app, all subsystems, and the active scenario. main.py
is just a thin bootstrapper that constructs Game(), calls .run().

Order of operations in start_scenario():
    1. (optional) reset event bus
    2. teardown previous scenario if any
    3. load scenario file (JSON [+ optional .py])
    4. build map     (registry.maps[scenario.map])
    5. build lighting (systems.lighting LightingRig with preset)
    6. spawn player + camera rig + HUD
    7. scenario.on_load()
    8. scenario.on_player_spawn()
    9. scenario.on_start()  (default: spawn enemy_groups)
   10. begin frame loop  (handled by Ursina)

The Game instance exposes update() which Ursina calls each frame; that
in turn calls scenario.on_update(dt).
"""

import config_loader
from config_loader import CFG
from ursina import Ursina, application, window, mouse, time, Vec3

from core.events import bus
from core.registry import registry
from core.scenario import load_scenario


class _MapContext:
    """Passed to map builder functions."""
    def __init__(self, center, params):
        self.center = center
        self.params = params


class Game:
    def __init__(self, scenario='megacity_skirmish', mods=None, config=None,
                 verbose_events=False):
        # NOTE: config arg is reserved for future per-instance config files;
        # for now the global CFG already loaded by config_loader is used.
        self.scenario_id = scenario
        self.mods = mods or []
        self.verbose_events = verbose_events

        # Ursina app
        self.app = Ursina()

        # Window
        win_cfg = CFG['window']
        window.title = win_cfg['title']
        window.fullscreen = win_cfg['fullscreen']
        window.exit_button.visible = False
        mouse.locked = CFG['mouse']['locked']

        # Game speed bridge (HUD reads from config_loader._game_speed)
        config_loader._game_speed = CFG.get('game_speed', 2.0)

        # Held during a scenario
        self.scenario = None
        self.player = None
        self.lighting = None
        self.cam_rig = None
        self.hud = None
        self.input_router = None
        self.map_meta = None
        self.scenario_time = 0.0

        # Pre-import built-in registries: maps and entities
        # (importing the package triggers all map @decorators)
        import maps                       # noqa: F401
        import entities.enemy_mech        # noqa: F401

        # Load mods (registers more weapons/enemies/maps/scenarios)
        if self.mods:
            from core.mod_loader import load_mods
            load_mods(self.mods)

        if self.verbose_events:
            bus.enable_logging(True)

        print(f'[GAME] Built. Registry summary: {registry.summary()}')

    # ============================================================
    def start_scenario(self, scenario_id=None):
        """Load and start a scenario by id. Tears down any existing one."""
        sid = scenario_id or self.scenario_id

        if self.scenario is not None:
            self._teardown_scenario()

        # 1. Reset event bus (drops handlers from previous scenario)
        bus.reset()
        if self.verbose_events:
            bus.enable_logging(True)

        # 2. Load
        self.scenario = load_scenario(sid)
        self.scenario.game = self
        self.scenario_time = 0.0
        self.scenario_id = sid

        # 3. Build map
        from systems.lighting import LightingRig
        from systems.camera_rig import CameraRig
        from systems.input_router import InputRouter
        from entities.player_mech import PlayerMech
        from ui.cockpit import CockpitHUD

        center = Vec3(0, 0, 0)
        map_id = self.scenario.get('map', 'megacity')
        builder = registry.get_map(map_id)
        ctx = _MapContext(center=center, params=self.scenario.get('map_params', {}))
        self.map_meta = builder(ctx)
        bus.publish('map.loaded', map=self.map_meta)

        # 4. Lighting
        light_preset = self.scenario.get('lighting', 'day_clear')
        self.lighting = LightingRig(light_preset)

        # 5. Player + scenario hooks: on_load before player spawn
        self.scenario.on_load()

        # Player
        loadout = self.scenario.get('player_loadout', None)
        spawn = self.scenario.get('player_spawn', None)
        self.player = PlayerMech(loadout=loadout)
        if spawn is not None:
            self.player.position = Vec3(*spawn)
        self.player.rotation_y = self.scenario.get('player_heading', 0)
        bus.publish('player.spawned', player=self.player)

        # 6. Camera rig (after player)
        cam_cfg = CFG['camera']
        ignore_for_cam = (
            self.player, self.player.legs, self.player.torso,
            self.player.arm_left, self.player.arm_right,
            self.player.shoulder_left, self.player.shoulder_right,
            self.player.head,
        )
        self.cam_rig = CameraRig(self.player, cam_cfg, ignore_entities=ignore_for_cam)
        self.player.cam_pivot = self.cam_rig.pivot   # so torso yaws with cam

        # 7. HUD
        self.hud = CockpitHUD(self.player, self.cam_rig.pivot)

        # 8. Input router — bind actions to handlers
        self.input_router = InputRouter(CFG['keybinds'])
        self._wire_input()

        # 9. Scenario lifecycle
        self.scenario.on_player_spawn()
        bus.publish('scenario.started', scenario=self.scenario)
        # Subscribe scenario to all events (it can override on_event)
        bus.subscribe('*', self._scenario_event_pump)
        self.scenario.on_start()

        print(f'[GAME] Scenario {sid!r} live')

    # ============================================================
    def _wire_input(self):
        ir = self.input_router

        # Quit / fullscreen
        ir.on('quit',       application.quit)
        ir.on('fullscreen', lambda: setattr(window, 'fullscreen',
                                            not window.fullscreen))

        # Camera zoom
        ir.on('zoom_in',    self.cam_rig.zoom_in)
        ir.on('zoom_out',   self.cam_rig.zoom_out)

        # Game speed (numeric +/-)
        def speed_up():
            config_loader._game_speed = min(10.0, config_loader._game_speed + 0.5)
            print(f'[SPEED] {config_loader._game_speed:.1f}x')
        def speed_down():
            config_loader._game_speed = max(0.5, config_loader._game_speed - 0.5)
            print(f'[SPEED] {config_loader._game_speed:.1f}x')
        ir.on('speed_up',   speed_up)
        ir.on('speed_down', speed_down)

        # Weapons — bind every carried weapon to its 'fire_<key>' action if
        # that action has a keybind. Weapon keys and keybind names line up by
        # convention (gatling -> fire_gatling, laser -> fire_laser, ...), so
        # new and mod-added weapons bind automatically. Continuous weapons also
        # fire while held via PlayerMech.update_continuous_fire().
        keybinds = CFG.get('keybinds', {})
        for wkey, weapon in self.player.weapons.items():
            action = f'fire_{wkey}'
            if action in keybinds:
                ir.on(action, weapon.fire)
            else:
                print(f'[GAME] weapon {wkey!r} has no keybind '
                      f'(add "{action}" under config.json keybinds to use it)')

    # ============================================================
    def _scenario_event_pump(self, _event=None, **payload):
        """Forward all events to scenario.on_event()."""
        if self.scenario:
            try:
                self.scenario.on_event(_event, payload)
            except Exception as e:
                print(f'[GAME] scenario.on_event raised: {e}')

    # ============================================================
    def _teardown_scenario(self):
        """Destroy entities and reset state for next scenario."""
        from ursina import scene, destroy

        if self.scenario:
            try:
                self.scenario.on_unload()
            except Exception as e:
                print(f'[GAME] scenario.on_unload raised: {e}')

        # Destroy gameplay entities. Camera/HUD live on camera.ui or as
        # children of player; destroying player cascades.
        targets_to_destroy = []
        for e in list(scene.entities):
            tag = getattr(e, 'tag', None)
            if tag in ('building', 'wall', 'pillar', 'cliff', 'rock'):
                targets_to_destroy.append(e)
            elif hasattr(e, 'hp') and e is not self.player:
                targets_to_destroy.append(e)

        for e in targets_to_destroy:
            destroy(e)

        if self.player:
            destroy(self.player)
        if self.hud:
            destroy(self.hud)
        if self.lighting:
            self.lighting.teardown()

        self.scenario = None
        self.player = None
        self.hud = None
        self.lighting = None
        self.cam_rig = None
        self.input_router = None
        self.map_meta = None

    # ============================================================
    def update(self):
        """Per-frame tick. Called by Ursina via the global update() in main.py."""
        application.time_scale = config_loader._game_speed
        dt = time.dt

        # Continuous-fire hook (gatling, etc.)
        if self.player:
            self.player.update_continuous_fire()

        # Camera
        if self.cam_rig:
            self.cam_rig.update(dt, mouse.velocity, CFG['mouse'])

        # Celestial follow
        if self.lighting and self.cam_rig:
            self.lighting.update_celestial_follow(self.cam_rig.world_position)

        # Scenario logic (advances scenario_time)
        if self.scenario:
            self.scenario_time += dt
            self.scenario.on_update(dt)

    # ============================================================
    def dispatch_input(self, key):
        """Forward Ursina input(key) callbacks to the router."""
        if self.input_router:
            self.input_router.dispatch(key)

    # ============================================================
    def run(self):
        self.start_scenario()
        # Wire global update/input to the Ursina app via main.py
        # main.py owns the `def update():` and `def input(key):` symbols
        # and forwards to game.update() / game.dispatch_input().
        self.app.run()
