"""
mock_ursina.py — a minimal, headless stand-in for the `ursina` package.

It implements just enough of Ursina's surface (Vec3 math, Entity lifecycle,
color, raycast, time, destroy/invoke, camera/scene/held_keys) to import and
exercise the project's *logic* modules (weapons, enemy AI, scenario rules,
tex_gen) without a GPU or Panda3D.

Install into sys.modules under the name 'ursina' BEFORE importing project code:

    import mock_ursina; mock_ursina.install()
"""
import sys
import math
import types


# ---------------------------------------------------------------------------
# Vec3 — full arithmetic + the handful of helpers the codebase uses
# ---------------------------------------------------------------------------
class Vec3:
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if hasattr(x, '__len__') and not isinstance(x, str):
            x, y, z = (list(x) + [0, 0, 0])[:3]
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    # iteration / indexing
    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __getitem__(self, i):
        return (self.x, self.y, self.z)[i]

    def __len__(self):
        return 3

    # arithmetic
    def __add__(self, o):
        o = _as_vec(o)
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    __radd__ = __add__

    def __sub__(self, o):
        o = _as_vec(o)
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __rsub__(self, o):
        o = _as_vec(o)
        return Vec3(o.x - self.x, o.y - self.y, o.z - self.z)

    def __mul__(self, s):
        if isinstance(s, (int, float)):
            return Vec3(self.x * s, self.y * s, self.z * s)
        o = _as_vec(s)
        return Vec3(self.x * o.x, self.y * o.y, self.z * o.z)

    __rmul__ = __mul__

    def __truediv__(self, s):
        if isinstance(s, (int, float)):
            return Vec3(self.x / s, self.y / s, self.z / s)
        o = _as_vec(s)
        return Vec3(self.x / o.x, self.y / o.y, self.z / o.z)

    def __neg__(self):
        return Vec3(-self.x, -self.y, -self.z)

    def __eq__(self, o):
        try:
            o = _as_vec(o)
        except Exception:
            return NotImplemented
        return (abs(self.x - o.x) < 1e-9 and abs(self.y - o.y) < 1e-9
                and abs(self.z - o.z) < 1e-9)

    def __repr__(self):
        return f'Vec3({self.x:.3f}, {self.y:.3f}, {self.z:.3f})'

    # helpers
    def length(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self):
        L = self.length()
        if L == 0:
            return Vec3(0, 0, 0)
        return Vec3(self.x / L, self.y / L, self.z / L)

    def dot(self, o):
        o = _as_vec(o)
        return self.x * o.x + self.y * o.y + self.z * o.z


def _as_vec(o):
    if isinstance(o, Vec3):
        return o
    if isinstance(o, (int, float)):
        return Vec3(o, o, o)
    return Vec3(*o)


Vec2 = Vec3  # good enough for tests


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------
class Color:
    def __init__(self, r=1.0, g=1.0, b=1.0, a=1.0, name=''):
        self.r, self.g, self.b, self.a = r, g, b, a
        self._name = name

    def __repr__(self):
        return f'Color({self._name or ""} {self.r:.2f},{self.g:.2f},{self.b:.2f},{self.a:.2f})'


class _ColorModule:
    # named colors used in the codebase
    red = Color(1, 0, 0, 1, 'red')
    orange = Color(1, 0.6, 0, 1, 'orange')
    dark_gray = Color(0.3, 0.3, 0.3, 1, 'dark_gray')
    light_gray = Color(0.75, 0.75, 0.75, 1, 'light_gray')
    gray = Color(0.5, 0.5, 0.5, 1, 'gray')
    white = Color(1, 1, 1, 1, 'white')
    black = Color(0, 0, 0, 1, 'black')
    azure = Color(0, 0.5, 1, 1, 'azure')
    blue = Color(0, 0, 1, 1, 'blue')
    yellow = Color(1, 1, 0, 1, 'yellow')
    green = Color(0, 1, 0, 1, 'green')
    lime = Color(0.75, 1, 0, 1, 'lime')
    cyan = Color(0, 1, 1, 1, 'cyan')
    magenta = Color(1, 0, 1, 1, 'magenta')
    violet = Color(0.5, 0, 1, 1, 'violet')
    brown = Color(0.5, 0.3, 0.1, 1, 'brown')
    gold = Color(1, 0.84, 0, 1, 'gold')
    pink = Color(1, 0.75, 0.8, 1, 'pink')
    clear = Color(0, 0, 0, 0, 'clear')

    @staticmethod
    def rgb(r, g, b, a=255):
        return Color(r / 255, g / 255, b / 255, (a / 255 if a > 1 else a), 'rgb')

    @staticmethod
    def rgba(r, g, b, a=255):
        return Color(r / 255, g / 255, b / 255, a / 255, 'rgba')

    @staticmethod
    def color(h, s, v, a=1.0):
        return Color(v, v, v, a, 'hsv')


color = _ColorModule()


# ---------------------------------------------------------------------------
# time / held_keys / window / application / mouse
# ---------------------------------------------------------------------------
class _Time:
    dt = 1.0 / 60.0


time = _Time()


class _HeldKeys(dict):
    def __missing__(self, k):
        return 0


held_keys = _HeldKeys()


class _Scene:
    def __init__(self):
        self.entities = []


scene = _Scene()


class _Camera:
    def __init__(self):
        self.position = Vec3(0, 0, 0)
        self.forward = Vec3(0, 0, 1)
        self.world_position = Vec3(0, 0, 0)
        self.fov = 90
        self.parent = None
        self.rotation = Vec3(0, 0, 0)

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)


camera = _Camera()


class _Mouse:
    locked = False
    visible = True
    velocity = Vec3(0, 0, 0)
    position = Vec3(0, 0, 0)


mouse = _Mouse()


class _Window:
    title = ''
    borderless = False
    fullscreen = False
    exit_button = types.SimpleNamespace(visible=True)
    fps_counter = types.SimpleNamespace(enabled=True)
    color = color.black

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)


window = _Window()


class _Application:
    paused = False

    def quit(self):
        pass


application = _Application()


# ---------------------------------------------------------------------------
# Entity — base class; auto-registers into scene.entities
# ---------------------------------------------------------------------------
class Entity:
    def __init__(self, **kwargs):
        # position
        pos = kwargs.pop('position', None)
        if pos is None:
            pos = Vec3(0, 0, 0)
        else:
            pos = _as_vec(pos)
        object.__setattr__(self, 'position', pos)

        # scale -> scale + scale_x/y/z
        sc = kwargs.pop('scale', 1)
        self._set_scale(sc)

        # rotation/orientation defaults
        object.__setattr__(self, 'rotation', Vec3(0, 0, 0))
        object.__setattr__(self, 'rotation_y', 0.0)
        object.__setattr__(self, '_forward', Vec3(0, 0, 1))
        object.__setattr__(self, '_right', Vec3(1, 0, 0))

        self.enabled = True
        self.parent = kwargs.pop('parent', None)
        self.model = kwargs.pop('model', None)
        self.color = kwargs.pop('color', color.white)
        self.texture = kwargs.pop('texture', None)
        self.collider = kwargs.pop('collider', None)
        self.tag = kwargs.pop('tag', None)
        # absorb any other kwargs as plain attributes
        for k, v in kwargs.items():
            setattr(self, k, v)

        scene.entities.append(self)

    # --- scale plumbing ---
    def _set_scale(self, sc):
        if isinstance(sc, (int, float)):
            v = Vec3(sc, sc, sc)
        else:
            v = _as_vec(sc)
        object.__setattr__(self, 'scale', v)
        object.__setattr__(self, 'scale_x', v.x)
        object.__setattr__(self, 'scale_y', v.y)
        object.__setattr__(self, 'scale_z', v.z)

    def __setattr__(self, k, v):
        # keep position.y mirror (self.y) and scale components coherent
        if k == 'scale':
            self._set_scale(v)
            return
        if k in ('scale_x', 'scale_y', 'scale_z'):
            object.__setattr__(self, k, v)
            s = self.scale
            comp = {'scale_x': 'x', 'scale_y': 'y', 'scale_z': 'z'}[k]
            setattr(s, comp, v)
            return
        if k == 'x':
            self.position.x = v
            return
        if k == 'y':
            self.position.y = v
            return
        if k == 'z':
            self.position.z = v
            return
        object.__setattr__(self, k, v)

    # position component shortcuts
    @property
    def x(self):
        return self.position.x

    @property
    def y(self):
        return self.position.y

    @property
    def z(self):
        return self.position.z

    @property
    def world_position(self):
        return self.position

    @world_position.setter
    def world_position(self, v):
        object.__setattr__(self, 'position', _as_vec(v))

    @property
    def forward(self):
        return self._forward

    @property
    def right(self):
        return self._right

    @property
    def up(self):
        return Vec3(0, 1, 0)

    # orientation helpers used by enemy AI / projectiles / beams
    def look_at(self, target, axis='forward'):
        t = target.world_position if isinstance(target, Entity) else _as_vec(target)
        d = (t - self.position)
        if d.length() > 1e-9:
            object.__setattr__(self, '_forward', d.normalized())

    def look_at_2d(self, target, axis='forward'):
        t = target.world_position if isinstance(target, Entity) else _as_vec(target)
        d = t - self.position
        d.y = 0.0
        if d.length() > 1e-9:
            f = d.normalized()
            object.__setattr__(self, '_forward', f)
            # right = forward rotated -90 deg about Y
            object.__setattr__(self, '_right', Vec3(f.z, 0, -f.x))

    def rotate(self, *a, **k):
        pass

    def animate_position(self, *a, **k):
        pass

    def combine(self, *a, **k):
        # batching no-op for headless tests; mark so callers can detect it ran
        self._combined = True
        return self


# Common Entity-like subclasses referenced via `from ursina import *`
class Sky(Entity):
    pass


class Text(Entity):
    def __init__(self, text='', **kwargs):
        super().__init__(**kwargs)
        self.text = text


class Button(Entity):
    pass


class DirectionalLight(Entity):
    def look_at(self, *a, **k):
        pass


class AmbientLight(Entity):
    pass


class PointLight(Entity):
    pass


class Mesh:
    def __init__(self, *a, **k):
        self.vertices = k.get('vertices', [])
        self.triangles = k.get('triangles', [])


class Texture:
    def __init__(self, *a, **k):
        self.filtering = None


def load_texture(*a, **k):
    return Texture()


class Shader:
    def __init__(self, *a, **k):
        pass


def load_model(*a, **k):
    return None


# ---------------------------------------------------------------------------
# raycast — programmable via mock_ursina.RAYCAST_HOOK
# ---------------------------------------------------------------------------
class HitInfo:
    def __init__(self, hit=False, entity=None, point=None, distance=0.0, normal=None):
        self.hit = hit
        self.entity = entity
        self.world_point = point if point is not None else Vec3(0, 0, 0)
        self.point = self.world_point
        self.distance = distance
        self.world_normal = normal if normal is not None else Vec3(0, 1, 0)
        self.normal = self.world_normal


# Tests set this to a callable(origin, direction, distance, ignore) -> HitInfo.
RAYCAST_HOOK = None


def raycast(origin, direction=None, distance=9999, ignore=(), traverse_target=None,
            debug=False, **kwargs):
    if RAYCAST_HOOK is not None:
        return RAYCAST_HOOK(_as_vec(origin),
                            _as_vec(direction) if direction is not None else Vec3(0, 0, 1),
                            distance, ignore)
    return HitInfo(hit=False)


# ---------------------------------------------------------------------------
# destroy / invoke / lerp / clamp / distance
# ---------------------------------------------------------------------------
def destroy(entity, delay=0):
    try:
        entity.enabled = False
    except Exception:
        pass
    try:
        scene.entities.remove(entity)
    except (ValueError, AttributeError):
        pass


# By default invoke runs the callback IMMEDIATELY (synchronous) so charge-up
# and salvo logic execute deterministically inside a single test step.
INVOKE_IMMEDIATE = True
_PENDING = []


def invoke(func, *args, delay=0, **kwargs):
    if INVOKE_IMMEDIATE:
        return func(*args, **kwargs)
    _PENDING.append((delay, func, args, kwargs))
    return types.SimpleNamespace(cancel=lambda: None)


def run_pending():
    """Execute deferred invokes (when INVOKE_IMMEDIATE is False)."""
    global _PENDING
    items = sorted(_PENDING, key=lambda t: t[0])
    _PENDING = []
    for _, f, a, k in items:
        f(*a, **k)


def lerp(a, b, t):
    if isinstance(a, Color) and isinstance(b, Color):
        return Color(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t,
                     a.b + (b.b - a.b) * t, a.a + (b.a - a.a) * t)
    if isinstance(a, Vec3) or isinstance(b, Vec3):
        a, b = _as_vec(a), _as_vec(b)
        return a + (b - a) * t
    return a + (b - a) * t


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(a, b):
    pa = a.world_position if isinstance(a, Entity) else _as_vec(a)
    pb = b.world_position if isinstance(b, Entity) else _as_vec(b)
    return (pa - pb).length()


def distance_2d(a, b):
    pa = a.world_position if isinstance(a, Entity) else _as_vec(a)
    pb = b.world_position if isinstance(b, Entity) else _as_vec(b)
    d = pa - pb
    d.y = 0
    return d.length()


class Ursina:
    def __init__(self, *a, **k):
        pass

    def run(self):
        pass


def held_keys_reset():
    held_keys.clear()


# ---------------------------------------------------------------------------
# installation
# ---------------------------------------------------------------------------
def install():
    """Register this module (and submodules) as the 'ursina' package."""
    mod = types.ModuleType('ursina')
    g = globals()
    for name in (
        'Vec3', 'Vec2', 'Color', 'color', 'time', 'held_keys', 'scene',
        'camera', 'mouse', 'window', 'application', 'Entity', 'Sky', 'Text',
        'Button', 'DirectionalLight', 'AmbientLight', 'PointLight', 'Mesh',
        'Texture', 'load_texture', 'load_model', 'Shader', 'raycast',
        'HitInfo', 'destroy', 'invoke', 'lerp', 'clamp', 'distance',
        'distance_2d', 'Ursina',
    ):
        setattr(mod, name, g[name])
    mod.__all__ = [n for n in dir(mod) if not n.startswith('_')]
    sys.modules['ursina'] = mod

    # Minimal submodule shims some code paths may import.
    shapes = types.ModuleType('ursina.shaders')
    shapes.lit_with_shadows_shader = object()
    shapes.unlit_shader = object()
    sys.modules['ursina.shaders'] = shapes
    mod.shaders = shapes

    prefab = types.ModuleType('ursina.prefabs')
    sys.modules['ursina.prefabs'] = prefab

    # 'noise' module (used by terrain_stream) — provide a stub so imports work.
    if 'noise' not in sys.modules:
        noise = types.ModuleType('noise')
        noise.pnoise2 = lambda *a, **k: 0.0
        noise.snoise2 = lambda *a, **k: 0.0
        sys.modules['noise'] = noise

    return mod
