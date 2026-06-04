import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

with open(_CONFIG_PATH, 'r') as f:
    CFG = json.load(f)


def keys(action):
    """Return keybind(s) for an action as a list.
    Usage: keys('forward') -> ['w', 'z', 'up arrow']
    """
    val = CFG['keybinds'].get(action, [])
    if isinstance(val, str):
        return [val]
    return val


def any_held(action):
    """Check if any key for this action is currently held."""
    from ursina import held_keys
    return any(held_keys[k] for k in keys(action))


def key_match(key, action):
    """Check if a pressed key matches an action binding."""
    return key in keys(action)
