"""
core/mod_loader.py
==================
Scan mods/ folder, read each mod's mod.json, import its entrypoint
module so its registry decorators run.

Usage from main:
    from core.mod_loader import load_mods
    load_mods(['example_mod'])         # explicit list
    load_mods('all')                   # everything in mods/

mod.json schema:
{
    "id": "example_mod",
    "name": "Example Mod",
    "version": "1.0.0",
    "author": "...",
    "description": "...",
    "entrypoint": "mods.example_mod.plugin"  # importable module path
}
"""

import os
import json
import importlib


def discover_mods(mods_dir='mods'):
    """Return list of mod ids found in mods_dir (any folder containing mod.json)."""
    found = []
    if not os.path.isdir(mods_dir):
        return found
    for name in sorted(os.listdir(mods_dir)):
        path = os.path.join(mods_dir, name)
        manifest = os.path.join(path, 'mod.json')
        if os.path.isdir(path) and os.path.isfile(manifest):
            found.append(name)
    return found


def load_mod(mod_id, mods_dir='mods'):
    """Import a single mod by id."""
    manifest_path = os.path.join(mods_dir, mod_id, 'mod.json')
    if not os.path.isfile(manifest_path):
        print(f'[MOD] {mod_id}: no mod.json found at {manifest_path}')
        return False
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f'[MOD] {mod_id}: malformed mod.json — {e}')
        return False

    entry = manifest.get('entrypoint')
    if not entry:
        print(f'[MOD] {mod_id}: no entrypoint in mod.json')
        return False

    try:
        importlib.import_module(entry)
    except Exception as e:
        print(f'[MOD] {mod_id}: import failed — {e}')
        import traceback; traceback.print_exc()
        return False

    print(f'[MOD] loaded {manifest.get("name", mod_id)} '
          f'v{manifest.get("version", "?")} by {manifest.get("author", "?")}')
    return True


def load_mods(which='all', mods_dir='mods'):
    """Load mods. `which` is 'all' or a list of mod ids."""
    if which == 'all':
        ids = discover_mods(mods_dir)
    else:
        ids = list(which)
    loaded = []
    for mid in ids:
        if load_mod(mid, mods_dir=mods_dir):
            loaded.append(mid)
    print(f'[MOD] {len(loaded)}/{len(ids)} loaded: {loaded}')
    return loaded
