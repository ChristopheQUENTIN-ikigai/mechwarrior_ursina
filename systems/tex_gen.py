"""
Procedural texture generator for rapid prototyping.
Generates placeholder textures in-memory using Ursina-native Texture.
When real textures exist in the asset_path, those are loaded instead.

Usage:
    from systems.tex_gen import get_texture
    entity.texture = get_texture('building')
"""

from ursina import Texture, color as c, load_texture
import os
import random
from config_loader import CFG

try:
    import numpy as np
    _HAVE_NUMPY = True
except ImportError:
    _HAVE_NUMPY = False

_tex_cfg = CFG['textures']
_asset_path = _tex_cfg['asset_path']
_use_procedural = _tex_cfg['use_procedural']

_cache = {}


def _texture_from_array(arr):
    """Turn an (H, W, 4) uint8 RGBA numpy array into an Ursina Texture."""
    try:
        from PIL import Image as PILImage
        img = PILImage.fromarray(arr, 'RGBA')
        tex = Texture(img)
        tex.filtering = None
        return tex
    except Exception:
        pass
    # Fallback: Panda3D PNMImage
    try:
        from panda3d.core import PNMImage, Texture as P3DTexture
        h, w = arr.shape[0], arr.shape[1]
        pnm = PNMImage(w, h, 4)
        pnm.set_maxval(255)
        pnm.add_alpha()
        for y in range(h):
            for x in range(w):
                r, g, b, a = (int(v) for v in arr[y, x])
                pnm.set_xel_val(x, y, r, g, b)
                pnm.set_alpha_val(x, y, a)
        p3d_tex = P3DTexture()
        p3d_tex.load(pnm)
        p3d_tex.set_magfilter(P3DTexture.FT_nearest)
        p3d_tex.set_minfilter(P3DTexture.FT_nearest)
        return p3d_tex
    except Exception:
        return None


def _asset_exists(name):
    """Check if a real texture file exists in the assets folder."""
    for ext in ('.png', '.jpg', '.jpeg', '.bmp'):
        path = os.path.join(_asset_path, name + ext)
        if os.path.isfile(path):
            return path
    return None


def _clamp(v):
    return max(0, min(255, v))


def _build_texture(width, height, pixel_func):
    """Build an Ursina Texture from a function that returns (r,g,b,a) per pixel.

    pixel_func(x, y) -> (r, g, b, a) with values 0-255.
    Uses Texture(Image(...)) with pillow if available, otherwise falls back
    to a simple colored Texture.
    """
    try:
        from PIL import Image as PILImage
        img = PILImage.new('RGBA', (width, height))
        pixels = img.load()
        for y in range(height):
            for x in range(width):
                pixels[x, y] = pixel_func(x, y)
        tex = Texture(img)
        tex.filtering = None
        return tex
    except ImportError:
        pass

    # Fallback: try Ursina's Texture with set_pixel (Panda3D PNMImage)
    try:
        from panda3d.core import PNMImage, Texture as P3DTexture
        pnm = PNMImage(width, height, 4)  # 4 channels = RGBA
        pnm.set_maxval(255)
        pnm.add_alpha()
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixel_func(x, y)
                pnm.set_xel_val(x, y, r, g, b)
                pnm.set_alpha_val(x, y, a)
        p3d_tex = P3DTexture()
        p3d_tex.load(pnm)
        p3d_tex.set_magfilter(P3DTexture.FT_nearest)
        p3d_tex.set_minfilter(P3DTexture.FT_nearest)
        return p3d_tex
    except Exception:
        pass

    # Last resort: return None (entity will just use its color)
    return None


def _base_array(width, height, rgb, variance):
    """(H, W, 4) uint8 RGBA filled with rgb + per-pixel uniform noise."""
    base = np.empty((height, width, 4), dtype=np.int16)
    if variance > 0:
        noise = np.random.randint(-variance, variance + 1, size=(height, width, 1))
    else:
        noise = 0
    base[..., 0] = rgb[0]
    base[..., 1] = rgb[1]
    base[..., 2] = rgb[2]
    base[..., :3] += noise
    base[..., 3] = 255
    np.clip(base, 0, 255, out=base)
    return base.astype(np.uint8)


def _grid_array(width, height, base_rgb, line_rgb, grid_step):
    arr = _base_array(width, height, base_rgb, 8)
    xs = np.arange(width)
    ys = np.arange(height)
    col_line = (xs % grid_step) < 2
    row_line = (ys % grid_step) < 2
    mask = col_line[None, :] | row_line[:, None]
    n = np.random.randint(-8, 9, size=(height, width))
    for ch in range(3):
        chan = np.clip(line_rgb[ch] + n, 0, 255).astype(np.uint8)
        arr[..., ch][mask] = chan[mask]
    return arr


def _noise_array(width, height, base_rgb, variance):
    return _base_array(width, height, base_rgb, variance)


def _stripe_array(width, height, color_a, color_b, stripe_width):
    arr = _base_array(width, height, color_a, 0)
    ys = np.arange(height)
    band_b = ((ys // stripe_width) % 2) == 1
    n = np.random.randint(-5, 6, size=(height, width))
    for ch in range(3):
        a_chan = np.clip(color_a[ch] + n, 0, 255).astype(np.uint8)
        b_chan = np.clip(color_b[ch] + n, 0, 255).astype(np.uint8)
        arr[..., ch] = np.where(band_b[:, None], b_chan, a_chan)
    return arr


def _window_array(width, height, wall_rgb, window_rgb, rows, cols):
    arr = _base_array(width, height, wall_rgb, 6)
    win_w = width // (cols + 1)
    win_h = height // (rows + 1)
    margin_x = win_w // 3
    margin_y = win_h // 3
    dark = (30, 30, 40)
    for row in range(rows):
        for col in range(cols):
            lit = random.random() < 0.6
            rgb = window_rgb if lit else dark
            x0 = (col + 1) * win_w - win_w // 2 + margin_x
            y0 = (row + 1) * win_h - win_h // 2 + margin_y
            x1 = min(width, x0 + win_w - margin_x * 2)
            y1 = min(height, y0 + win_h - margin_y * 2)
            x0 = max(0, x0)
            y0 = max(0, y0)
            arr[y0:y1, x0:x1, 0] = rgb[0]
            arr[y0:y1, x0:x1, 1] = rgb[1]
            arr[y0:y1, x0:x1, 2] = rgb[2]
            arr[y0:y1, x0:x1, 3] = 255
    return arr


def _make_grid_texture(width, height, base_rgb, line_rgb, grid_step):
    """Grid/panel pattern."""
    if _HAVE_NUMPY:
        tex = _texture_from_array(_grid_array(width, height, base_rgb, line_rgb, grid_step))
        if tex is not None:
            return tex

    br, bg, bb = base_rgb
    lr, lg, lb = line_rgb

    def pixel(x, y):
        n = random.randint(-8, 8)
        if x % grid_step < 2 or y % grid_step < 2:
            return (_clamp(lr + n), _clamp(lg + n), _clamp(lb + n), 255)
        return (_clamp(br + n), _clamp(bg + n), _clamp(bb + n), 255)

    return _build_texture(width, height, pixel)


def _make_noise_texture(width, height, base_rgb, variance):
    """Noisy organic texture (terrain, dirt, concrete)."""
    if _HAVE_NUMPY:
        tex = _texture_from_array(_noise_array(width, height, base_rgb, variance))
        if tex is not None:
            return tex

    br, bg, bb = base_rgb

    def pixel(x, y):
        v = random.randint(-variance, variance)
        return (_clamp(br + v), _clamp(bg + v), _clamp(bb + v), 255)

    return _build_texture(width, height, pixel)


def _make_stripe_texture(width, height, color_a, color_b, stripe_width):
    """Horizontal stripe pattern (mechs, industrial panels)."""
    if _HAVE_NUMPY:
        tex = _texture_from_array(_stripe_array(width, height, color_a, color_b, stripe_width))
        if tex is not None:
            return tex

    def pixel(x, y):
        n = random.randint(-5, 5)
        if (y // stripe_width) % 2 == 0:
            r, g, b = color_a
        else:
            r, g, b = color_b
        return (_clamp(r + n), _clamp(g + n), _clamp(b + n), 255)

    return _build_texture(width, height, pixel)


def _make_window_texture(width, height, wall_rgb, window_rgb, rows, cols):
    """Building facade with lit windows."""
    if _HAVE_NUMPY:
        tex = _texture_from_array(_window_array(width, height, wall_rgb, window_rgb, rows, cols))
        if tex is not None:
            return tex

    wr, wg, wb = wall_rgb
    win_w = width // (cols + 1)
    win_h = height // (rows + 1)
    margin_x = win_w // 3
    margin_y = win_h // 3

    # Pre-compute window rectangles
    windows = []
    for row in range(rows):
        for col in range(cols):
            lit = random.random() < 0.6
            x0 = (col + 1) * win_w - win_w // 2 + margin_x
            y0 = (row + 1) * win_h - win_h // 2 + margin_y
            x1 = x0 + win_w - margin_x * 2
            y1 = y0 + win_h - margin_y * 2
            windows.append((x0, y0, x1, y1, lit))

    def pixel(x, y):
        # Check if inside any window
        for x0, y0, x1, y1, lit in windows:
            if x0 <= x < x1 and y0 <= y < y1:
                if lit:
                    lr, lg, lb = window_rgb
                else:
                    lr, lg, lb = (30, 30, 40)
                return (lr, lg, lb, 255)
        # Wall
        n = random.randint(-6, 6)
        return (_clamp(wr + n), _clamp(wg + n), _clamp(wb + n), 255)

    return _build_texture(width, height, pixel)


# ===================== PUBLIC API =====================

def get_texture(name):
    """Get a texture by name. Uses asset file if available, else procedural.

    Supported names:
        'building'        - concrete facade with windows
        'building_glass'  - glass/steel skyscraper
        'ground'          - earthy terrain
        'grass'           - green terrain
        'concrete'        - flat concrete
        'mech_legs'       - industrial panel for mech legs
        'mech_torso'      - striped panel for mech torso
        'enemy'           - orange-red industrial
        'metal'           - generic metal plate
    """
    if name in _cache:
        return _cache[name]

    # Check for real asset first
    asset_file = _asset_exists(name)
    if asset_file and not _use_procedural:
        tex = load_texture(asset_file)
        _cache[name] = tex
        return tex

    # Generate procedural placeholder
    tex = _generate(name)
    _cache[name] = tex
    return tex


def _generate(name):
    """Generate a procedural texture by name."""
    if name == 'building':
        return _make_window_texture(
            64, 64,
            wall_rgb=(90, 90, 100),
            window_rgb=(200, 200, 140),
            rows=6, cols=4
        )

    elif name == 'building_glass':
        return _make_grid_texture(
            64, 64,
            base_rgb=(60, 80, 110),
            line_rgb=(100, 130, 160),
            grid_step=8
        )

    elif name in ('ground', 'concrete'):
        return _make_noise_texture(
            64, 64,
            base_rgb=(120, 115, 100),
            variance=15
        )

    elif name == 'grass':
        return _make_noise_texture(
            64, 64,
            base_rgb=(60, 100, 45),
            variance=20
        )

    elif name == 'mech_legs':
        return _make_grid_texture(
            32, 32,
            base_rgb=(50, 90, 130),
            line_rgb=(30, 60, 90),
            grid_step=8
        )

    elif name == 'mech_torso':
        return _make_stripe_texture(
            32, 32,
            color_a=(40, 60, 120),
            color_b=(30, 45, 90),
            stripe_width=4
        )

    elif name == 'enemy':
        return _make_stripe_texture(
            32, 32,
            color_a=(180, 100, 30),
            color_b=(140, 70, 20),
            stripe_width=4
        )

    elif name == 'metal':
        return _make_grid_texture(
            32, 32,
            base_rgb=(140, 140, 150),
            line_rgb=(100, 100, 110),
            grid_step=8
        )

    # --- Residential ---
    elif name == 'house':
        # Small house: warm brick-like with a few small windows
        return _make_window_texture(
            32, 32,
            wall_rgb=(155, 120, 85),
            window_rgb=(180, 200, 220),
            rows=2, cols=2
        )

    elif name == 'house_medium':
        # Medium residential: stucco with more windows
        return _make_window_texture(
            48, 48,
            wall_rgb=(140, 135, 120),
            window_rgb=(190, 200, 170),
            rows=3, cols=3
        )

    # --- Public facilities ---
    elif name == 'hospital':
        # White/clean with a red cross pattern via grid
        return _make_grid_texture(
            64, 64,
            base_rgb=(200, 200, 210),
            line_rgb=(180, 60, 60),
            grid_step=16
        )

    elif name == 'factory':
        # Dark industrial with wide corrugated stripes
        return _make_stripe_texture(
            64, 64,
            color_a=(95, 90, 80),
            color_b=(75, 70, 65),
            stripe_width=6
        )

    elif name == 'manufacture':
        # Heavy industry: dark metal grid panels
        return _make_grid_texture(
            64, 64,
            base_rgb=(80, 75, 70),
            line_rgb=(50, 50, 55),
            grid_step=10
        )

    elif name == 'station':
        # Train/bus station: concrete with horizontal band stripes
        return _make_stripe_texture(
            64, 64,
            color_a=(140, 140, 150),
            color_b=(120, 120, 130),
            stripe_width=8
        )

    elif name == 'airport':
        # Large flat: steel blue grid
        return _make_grid_texture(
            64, 64,
            base_rgb=(150, 160, 175),
            line_rgb=(120, 130, 145),
            grid_step=12
        )

    elif name == 'food_shop':
        # Warm storefront with wide windows
        return _make_window_texture(
            32, 32,
            wall_rgb=(170, 120, 70),
            window_rgb=(240, 230, 180),
            rows=1, cols=2
        )

    elif name == 'warehouse':
        # Corrugated metal look
        return _make_stripe_texture(
            48, 48,
            color_a=(110, 105, 100),
            color_b=(90, 88, 85),
            stripe_width=3
        )

    else:
        # Fallback: pink checkerboard (easy to spot missing textures)
        return _make_grid_texture(
            32, 32,
            base_rgb=(255, 0, 255),
            line_rgb=(0, 0, 0),
            grid_step=16
        )
