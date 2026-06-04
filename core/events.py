"""
core/events.py
==============
Tiny synchronous pub/sub bus.

Modules subscribe to event names; anyone can publish. No threading, no queues —
events fire inline during whatever frame published them. This is deliberate:
makes flow easy to reason about, no race conditions.

Conventional event names (dot-namespaced):
    player.spawned        payload: {'player': PlayerMech}
    player.killed         payload: {'player': PlayerMech, 'by': source}
    player.heat_changed   payload: {'player': PlayerMech, 'heat': float}
    enemy.spawned         payload: {'enemy': EnemyMech, 'spawner': Scenario}
    enemy.killed          payload: {'enemy': EnemyMech, 'by': source}
    weapon.fired          payload: {'weapon': Weapon, 'origin': Vec3}
    weapon.hit            payload: {'weapon': Weapon, 'target': Entity, 'damage': float}
    scenario.started      payload: {'scenario': Scenario}
    scenario.completed    payload: {'scenario': Scenario, 'won': bool}
    wave.started          payload: {'wave': int, 'count': int}
    wave.cleared          payload: {'wave': int}
    map.loaded            payload: {'map': Map}

Mod authors should keep their own event names under a prefix, e.g.
    mods.plasma.charged   payload: {...}

Usage:
    from core.events import bus
    bus.subscribe('enemy.killed', my_handler)
    bus.publish('enemy.killed', enemy=ent, by=weapon)
"""

from collections import defaultdict
import traceback


class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)
        self._wildcard = []   # subscribers to all events ('*')
        self._log = False

    # ---------------- subscription ----------------
    def subscribe(self, event_name, handler):
        """Register `handler(**payload)` to be called when event fires.
        Use '*' to subscribe to every event (handler also receives _event=name).
        """
        if event_name == '*':
            self._wildcard.append(handler)
        else:
            self._subs[event_name].append(handler)
        return handler  # so it can be used as a decorator

    def unsubscribe(self, event_name, handler):
        try:
            if event_name == '*':
                self._wildcard.remove(handler)
            else:
                self._subs[event_name].remove(handler)
        except ValueError:
            pass

    # ---------------- publication ----------------
    def publish(self, event_name, **payload):
        """Fire `event_name` synchronously. Handler exceptions are caught
        and logged so one bad subscriber can't crash the game.
        """
        if self._log:
            print(f'[EVT] {event_name} {payload!r}')
        for h in list(self._subs.get(event_name, [])):
            try:
                h(**payload)
            except Exception as e:
                print(f'[EVT][ERROR] handler {h} for {event_name}: {e}')
                traceback.print_exc()
        for h in list(self._wildcard):
            try:
                h(_event=event_name, **payload)
            except Exception as e:
                print(f'[EVT][ERROR] wildcard {h} for {event_name}: {e}')
                traceback.print_exc()

    # ---------------- debug ----------------
    def enable_logging(self, on=True):
        self._log = on

    def reset(self):
        """Drop all subscribers — useful between scenarios."""
        self._subs.clear()
        self._wildcard.clear()


# Module-level singleton — import as `from core.events import bus`
bus = EventBus()
