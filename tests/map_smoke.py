"""map_smoke.py — verify ground plane + building batch/unbatch under mock."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)))
import mock_ursina; mock_ursina.install()
import ursina as U
from config_loader import CFG

_p = _f = 0
def check(name, cond, d=''):
    global _p, _f
    if cond: _p += 1; print(f'  PASS  {name}')
    else: _f += 1; print(f'  FAIL  {name}  {d}')

def reset():
    U.scene.entities.clear()

# ---- ground builder ----
print('=== ground plane ===')
reset()
from maps._ground import build_ground
g = build_ground(center=U.Vec3(0, 0, 0), full_size=200, map_key='megacity')
check('ground entity created', g is not None)
check('ground tagged "ground"', g.tag == 'ground')
check('ground has NO hp attr (weapons skip it)', not hasattr(g, 'hp'))
check('ground top sits at y_top=0',
      abs((g.y + g.scale_y / 2.0) - CFG['ground']['y_top']) < 1e-6,
      f'top={g.y + g.scale_y/2.0}')
check('ground has a box collider', g.collider == 'box')

# ---- megacity: batched (default) ----
print('\n=== megacity build (batched) ===')
reset()
CFG['city']['batch'] = True
import importlib, random
random.seed(1)
import maps.megacity as MC
ctx = types.SimpleNamespace(center=U.Vec3(0, 0, 0), params={'size': 40})
MC.build_megacity(ctx)
ents = U.scene.entities
grounds = [e for e in ents if getattr(e, 'tag', None) == 'ground']
batched_parents = [e for e in ents if getattr(e, 'batched', None) is True]
check('exactly one ground slab', len(grounds) == 1, f'n={len(grounds)}')
check('combine() ran -> batched parent entities exist',
      len(batched_parents) >= 1, f'n={len(batched_parents)}')
check('batched parents carry a texture', all(p.texture is not None for p in batched_parents))
total_batched = len(grounds) + len(batched_parents)
print(f'  (info) batched scene: {len(ents)} entities total, '
      f'{len(batched_parents)} batched draw-groups + 1 ground')

# ---- megacity: unbatched fallback ----
print('\n=== megacity build (unbatched) ===')
reset()
CFG['city']['batch'] = False
random.seed(1)
ctx = types.SimpleNamespace(center=U.Vec3(0, 0, 0), params={'size': 40})
MC.build_megacity(ctx)
ents = U.scene.entities
buildings = [e for e in ents if getattr(e, 'tag', None) == 'building']
check('unbatched path spawns individual buildings', len(buildings) >= 1,
      f'n={len(buildings)}')
check('individual buildings have box colliders',
      all(b.collider == 'box' for b in buildings))
check('individual buildings are NOT marked batched',
      all(getattr(b, 'batched', False) is False for b in buildings))
print(f'  (info) unbatched scene: {len(buildings)} building entities '
      f'(each its own draw call+collider)')

# restore default
CFG['city']['batch'] = True

print('\n' + '=' * 44)
print(f'MAP SMOKE: {_p} passed, {_f} failed')
print('=' * 44)
sys.exit(1 if _f else 0)
