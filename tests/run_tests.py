"""
run_tests.py — headless logic tests for mech2_v2.

Installs the mock 'ursina', then imports and exercises the real project
logic modules. Run:  python3 run_tests.py
"""
import sys
import os
import math

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, HERE)        # mock_ursina
sys.path.insert(0, PROJECT)     # project modules

import mock_ursina
mock_ursina.install()

import ursina as U  # the mock

# ---- now safe to import project logic ----
from config_loader import CFG, any_held
import systems.weapons as W
from systems.weapons import (
    Weapon, Projectile, HomingProjectile, _spread, _find_homing_target,
    _damage_entity,
)
import entities.enemy_mech as EM
from entities.enemy_mech import EnemyMech
from core.events import bus
import core.scenario as SC


# ---------------------------------------------------------------------------
# tiny test framework
# ---------------------------------------------------------------------------
_passed = 0
_failed = 0
_fails = []


def check(name, cond, detail=''):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f'  PASS  {name}')
    else:
        _failed += 1
        _fails.append(name)
        print(f'  FAIL  {name}   {detail}')


def section(t):
    print(f'\n=== {t} ===')


def reset_scene():
    """Clear scene + enemy player-cache between tests."""
    U.scene.entities.clear()
    EM._player_ref = None
    mock_ursina.RAYCAST_HOOK = None
    U.held_keys.clear()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeMech(U.Entity):
    """Minimal stand-in for PlayerMech: heat/overheat + hardpoints + parts."""
    def __init__(self, pos=(0, 0, 0)):
        super().__init__(position=pos)
        self.overheated = False
        self.heat = 0.0
        self.max_heat = 100.0
        self.torso = U.Entity(position=pos)
        self.hardpoints = {
            'arm_right': U.Entity(position=(pos[0] + 0.6, pos[1], pos[2])),
            'arm_left': U.Entity(position=(pos[0] - 0.6, pos[1], pos[2])),
        }
        self._parts = [self.torso] + list(self.hardpoints.values())

    def add_heat(self, amount):
        self.heat += amount
        if self.heat >= self.max_heat:
            self.overheated = True


# ===========================================================================
section('1. config + weapon resolution')
# ===========================================================================
reset_scene()
weap = CFG['weapons']
check('all 7 weapons present',
      set(['gatling', 'railgun', 'rocketpod', 'heatseeker', 'sniper',
           'laser', 'gauss']).issubset(weap.keys()),
      str(list(weap.keys())))

m = FakeMech()
U.camera.forward = U.Vec3(0, 0, 1)
made = {k: Weapon(m, k) for k in weap.keys()}
check('laser resolves, type hitscan, continuous=True',
      made['laser'].type == 'hitscan' and made['laser'].continuous is True)
check('gauss resolves, type hitscan, continuous=False',
      made['gauss'].type == 'hitscan' and made['gauss'].continuous is False)
check('gauss has charge_time > 0', made['gauss'].cfg.get('charge_time', 0) > 0)
check('every weapon has a known type',
      all(made[k].type in ('projectile', 'hitscan', 'salvo', 'homing')
          for k in made))


# ===========================================================================
section('2. _spread direction math')
# ===========================================================================
d = U.Vec3(0, 0, 1)
check('spread deg=0 is identity', _spread(d, 0) == d)
s = _spread(d, 5)
check('spread output is unit length', abs(s.length() - 1.0) < 1e-6,
      f'len={s.length()}')
ang = math.degrees(math.acos(max(-1, min(1, s.dot(d)))))
check('spread stays within ~2x requested cone', ang <= 10.5, f'angle={ang:.2f}')


# ===========================================================================
section('3. homing target acquisition (cone + nearest)')
# ===========================================================================
reset_scene()
near = U.Entity(position=(0, 0, 10)); near.hp = 50
far = U.Entity(position=(0, 0, 60)); far.hp = 50
off = U.Entity(position=(40, 0, 3)); off.hp = 50      # outside cone
nohp = U.Entity(position=(0, 0, 5))                    # no hp -> ignored
tgt = _find_homing_target(U.Vec3(0, 0, 0), U.Vec3(0, 0, 1),
                          lock_range=100, cone_deg=25)
check('picks nearest in-cone target', tgt is near, f'got {tgt}')
tgt2 = _find_homing_target(U.Vec3(0, 0, 0), U.Vec3(0, 0, 1),
                           lock_range=8, cone_deg=25)
check('returns None when nothing in range', tgt2 is None, f'got {tgt2}')


# ===========================================================================
section('4. homing projectile steers toward target')
# ===========================================================================
reset_scene()
mock_ursina.RAYCAST_HOOK = lambda o, d, dist, ig: U.HitInfo(hit=False)  # never detonate
target = U.Entity(position=(30, 0, 5)); target.hp = 100
proj = HomingProjectile(
    pos=U.Vec3(0, 0, 0), direction=U.Vec3(0, 0, 1),
    speed=20, damage=10, col=U.color.red, scale_v=0.3, model='cube',
    target=target, turn_rate_deg=240, owner=None,
)
def _desired_dot():
    des = (target.world_position - proj.world_position)
    if des.length() < 1e-6:
        return 1.0
    des = des.normalized()
    return proj.dir.normalized().dot(des)

start_dot = _desired_dot()
best_dot = start_dot
for _ in range(120):
    proj.update()
    best_dot = max(best_dot, _desired_dot())
    if not proj.enabled:
        break
check('heading converges toward target', best_dot > 0.99,
      f'start={start_dot:.3f} best={best_dot:.3f}')


# ===========================================================================
section('5. weapon cooldown / heat / overheat gating')
# ===========================================================================
reset_scene()
m = FakeMech()
U.camera.forward = U.Vec3(0, 0, 1)
gat = Weapon(m, 'gatling')

n0 = len(U.scene.entities)
gat.fire()
n1 = len(U.scene.entities)
check('fire spawns a projectile', n1 > n0)
check('heat applied on fire', m.heat == CFG['weapons']['gatling']['heat'],
      f'heat={m.heat}')
check('cooldown engaged after fire', gat._cd_remaining > 0)

n_before = len(U.scene.entities)
gat.fire()  # should be blocked (still cooling)
check('second immediate fire blocked by cooldown',
      len(U.scene.entities) == n_before)

gat.tick(10.0)  # drain cooldown
check('tick drains cooldown', gat._cd_remaining <= 0)
n_before = len(U.scene.entities)
gat.fire()
check('fires again after cooldown drained',
      len(U.scene.entities) > n_before)

# overheat gating
m.overheated = True
n_before = len(U.scene.entities)
gat.tick(10.0)
gat.fire()
check('overheated mech cannot fire',
      len(U.scene.entities) == n_before)
m.overheated = False

# gauss charge path still deals damage + sets cooldown (invoke immediate)
reset_scene()
m = FakeMech()
U.camera.forward = U.Vec3(0, 0, 1)
dummy = U.Entity(position=(0, 0, 30)); dummy.hp = 500
mock_ursina.RAYCAST_HOOK = lambda o, d, dist, ig: U.HitInfo(
    hit=True, entity=dummy, point=U.Vec3(0, 0, 30), distance=30)
gauss = Weapon(m, 'gauss')
hp_before = dummy.hp
gauss.fire()
check('charged gauss deals damage through charge path',
      dummy.hp == hp_before - CFG['weapons']['gauss']['damage'],
      f'hp {hp_before}->{dummy.hp}')
check('gauss not stuck in charging state', gauss._charging is False)
check('gauss cooldown engaged', gauss._cd_remaining > 0)


# ===========================================================================
section('6. damage routes through take_damage -> events fire')
# ===========================================================================
reset_scene()
events = []
unsub1 = bus.subscribe('enemy.killed', lambda **kw: events.append(('enemy.killed', kw)))
unsub2 = bus.subscribe('player.killed', lambda **kw: events.append(('player.killed', kw)))
unsub3 = bus.subscribe('player.damaged', lambda **kw: events.append(('player.damaged', kw)))

enemy = EnemyMech(U.Vec3(0, 0, 0))
enemy.hp = 10
_damage_entity(enemy, 5, source='tester')   # non-lethal
check('non-lethal hit reduces hp via take_damage', enemy.hp == 5)
check('no kill event on non-lethal',
      not any(e[0] == 'enemy.killed' for e in events))
_damage_entity(enemy, 99, source='tester')  # lethal
check('enemy.killed published on lethal damage',
      any(e[0] == 'enemy.killed' for e in events))
check('dead enemy destroyed (disabled)', enemy.enabled is False)

# Player events via the REAL PlayerMech.take_damage
reset_scene()
events.clear()
from entities.player_mech import PlayerMech
player = PlayerMech(loadout=['gatling', 'laser', 'gauss'])
start_hp = player.hp
player.take_damage(5, source='tester')
check('player.damaged fires on non-lethal',
      any(e[0] == 'player.damaged' for e in events))
check('player still alive after non-lethal', player.hp == start_hp - 5)
player.take_damage(99999, source='tester')
check('player.killed fires on lethal',
      any(e[0] == 'player.killed' for e in events))
check('player entity NOT destroyed on death (scenario handles lose)',
      player.enabled is True)
check('player carries laser+gauss in loadout',
      'laser' in player.weapons and 'gauss' in player.weapons)


# ===========================================================================
section('7. enemy AI: FSM transitions + line-of-sight gating')
# ===========================================================================
reset_scene()
# a "player" the enemy can find: any entity with .weapons that isn't an EnemyMech
class FakePlayer(U.Entity):
    def __init__(self, pos):
        super().__init__(position=pos)
        self.weapons = {}
        self.hp = 100
        self._parts = []

pl = FakePlayer(U.Vec3(0, 0, 0))
enemy = EnemyMech(U.Vec3(0, 0, 0))
enemy.attack_range = 20
enemy.chase_range = 60
enemy.fire_cooldown = 0

# clear LOS by default
mock_ursina.RAYCAST_HOOK = lambda o, d, dist, ig: U.HitInfo(hit=False)

# patrol: far away
pl.world_position = U.Vec3(0, 0, 200)
enemy.world_position = U.Vec3(0, 0, 0)
enemy.update()
check('state=patrol when out of chase range', enemy.state == 'patrol',
      enemy.state)

# chase: within chase but outside attack
pl.world_position = U.Vec3(0, 0, 40)
enemy.world_position = U.Vec3(0, 0, 0)
enemy.update()
check('state=chase within chase range', enemy.state == 'chase', enemy.state)

# attack: within attack range, with LOS -> fires
pl.world_position = U.Vec3(0, 0, 10)
enemy.world_position = U.Vec3(0, 0, 0)
enemy.fire_cooldown = 0
n_before = len(U.scene.entities)
enemy.update()
check('state=attack within attack range', enemy.state == 'attack', enemy.state)
check('enemy fires when it has line-of-sight',
      len(U.scene.entities) > n_before)

# attack but LOS blocked by a wall -> must NOT fire
wall = U.Entity(position=(0, 0, 5)); wall.tag = 'building'
mock_ursina.RAYCAST_HOOK = lambda o, d, dist, ig: U.HitInfo(
    hit=True, entity=wall, point=U.Vec3(0, 0, 5), distance=5)
enemy.fire_cooldown = 0
n_before = len(U.scene.entities)
enemy.update()
check('enemy does NOT fire when LOS blocked',
      len(U.scene.entities) == n_before)

# enemy rests on the configured ground plane, not floating/sinking
reset_scene()
gy = CFG.get('ground', {}).get('y_top', 0.0)
e2 = EnemyMech(U.Vec3(0, -50, 0))   # spawned underground
check('enemy clamped to floor on spawn',
      abs(e2.y - (gy + e2.scale_y / 2.0)) < 1e-6, f'y={e2.y}')


# ===========================================================================
section('8. scenario win/lose condition evaluation')
# ===========================================================================
reset_scene()


class FakeGame:
    def __init__(self):
        self.player = None
        self.scenario_time = 0.0


def make_scenario(params):
    s = SC.Scenario.__new__(SC.Scenario)
    s.params = params
    s.id = 'test'
    s._completed = False
    s._spawned_enemies = []
    s.game = FakeGame()
    return s

# kill_all
s = make_scenario({'win_condition': {'type': 'kill_all'}})
a = EnemyMech(U.Vec3(0, 0, 0)); b = EnemyMech(U.Vec3(0, 0, 0))
s._spawned_enemies = [a, b]
check('kill_all False while enemies alive', s._eval_condition(s.params['win_condition']) is False)
a.hp = 0; b.enabled = False
check('kill_all True when all dead/disabled', s._eval_condition(s.params['win_condition']) is True)

# player_dead
s = make_scenario({'lose_condition': {'type': 'player_dead'}})
s.game.player = FakePlayer(U.Vec3(0, 0, 0)); s.game.player.hp = 100
check('player_dead False while alive', s._eval_condition(s.params['lose_condition']) is False)
s.game.player.hp = 0
check('player_dead True at 0 hp', s._eval_condition(s.params['lose_condition']) is True)
s.game.player = None
check('player_dead True when player missing', s._eval_condition(s.params['lose_condition']) is True)

# survive_seconds
s = make_scenario({'win_condition': {'type': 'survive_seconds', 'seconds': 30}})
s.game.scenario_time = 10
check('survive_seconds False before time', s._eval_condition(s.params['win_condition']) is False)
s.game.scenario_time = 31
check('survive_seconds True after time', s._eval_condition(s.params['win_condition']) is True)

# reach_position
s = make_scenario({'win_condition': {'type': 'reach_position', 'at': [10, 0, 0], 'radius': 5}})
s.game.player = FakePlayer(U.Vec3(0, 0, 0))
check('reach_position False when far', s._eval_condition(s.params['win_condition']) is False)
s.game.player.world_position = U.Vec3(12, 0, 0)
check('reach_position True within radius', s._eval_condition(s.params['win_condition']) is True)


# ===========================================================================
section('9. procedural textures (numpy path) via tex_gen')
# ===========================================================================
reset_scene()
import systems.tex_gen as TG
check('numpy is the active texture backend', TG._HAVE_NUMPY is True)
for nm in ('building', 'building_glass', 'concrete', 'metal', 'enemy', 'mech_torso'):
    tex = TG.get_texture(nm)
    check(f'texture "{nm}" generated', tex is not None)
# direct array checks
arr = TG._window_array(64, 64, (90, 90, 100), (200, 200, 140), 6, 4)
check('window array shape (64,64,4)', arr.shape == (64, 64, 4))
check('window array dtype uint8', str(arr.dtype) == 'uint8')
check('window array RGBA alpha = 255', bool((arr[..., 3] == 255).all()))
g = TG._grid_array(32, 32, (60, 80, 110), (100, 130, 160), 8)
check('grid array values in 0..255',
      int(g.min()) >= 0 and int(g.max()) <= 255)


# ---------------------------------------------------------------------------
print('\n' + '=' * 52)
print(f'RESULT: {_passed} passed, {_failed} failed')
if _fails:
    print('FAILED:', ', '.join(_fails))
print('=' * 52)
sys.exit(1 if _failed else 0)
