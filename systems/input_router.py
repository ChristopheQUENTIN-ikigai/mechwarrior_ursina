"""
systems/input_router.py
=======================
Input dispatcher.

Ursina's built-in `input(key)` global is convenient but couples handlers
to module load order. The router here lets any system register a handler
keyed by an action name (e.g. 'fire_gatling'), and the router checks all
configured keybinds for that action.

Usage:
    router = InputRouter(CFG['keybinds'])
    router.on('fire_gatling',  player.weapons['gatling'].fire)
    router.on('zoom_in',       cam_rig.zoom_in)
    router.on('quit',          application.quit)

    # In Ursina's input(key):
    def input(key):
        router.dispatch(key)
"""


class InputRouter:
    def __init__(self, keybinds_cfg):
        """keybinds_cfg: CFG['keybinds'] — dict of action -> str | list[str]."""
        self._keybinds = keybinds_cfg
        # action -> list[callable]
        self._handlers = {}
        # invert keybinds for fast lookup: key -> set[action]
        self._key_to_actions = {}
        for action, val in keybinds_cfg.items():
            if action.startswith('_'):
                continue
            keys = [val] if isinstance(val, str) else val
            for k in keys:
                self._key_to_actions.setdefault(k, set()).add(action)

    def on(self, action, handler):
        """Register `handler()` to fire when `action` is triggered."""
        self._handlers.setdefault(action, []).append(handler)
        return handler

    def off(self, action, handler):
        try:
            self._handlers.get(action, []).remove(handler)
        except ValueError:
            pass

    def dispatch(self, key):
        """Called from Ursina's input(key)."""
        for action in self._key_to_actions.get(key, ()):
            for h in self._handlers.get(action, ()):
                try:
                    h()
                except Exception as e:
                    print(f'[INPUT] handler {h} for {action} raised: {e}')
