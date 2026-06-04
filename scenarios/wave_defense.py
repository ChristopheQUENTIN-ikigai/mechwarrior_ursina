"""
scenarios/wave_defense.py
=========================
Custom logic for the wave_defense scenario. Reads `waves[]` from its JSON
and spawns each wave on a timer, publishing wave.started / wave.cleared
events for HUD or scoring systems to react to.

This file demonstrates the "JSON declares parameters, Python hooks logic"
pattern: the wave list is fully data-driven, but the timing/spawning state
machine lives in code.
"""

import math
import random
from ursina import Vec3

from core.scenario import Scenario
from core.registry import registry
from core.events import bus


@registry.scenario('wave_defense')
class WaveDefense(Scenario):

    def __init__(self, params):
        super().__init__(params)
        self.waves = params.get('waves', [])
        self.wave_idx = -1
        self.next_wave_at = None      # game-time timestamp for next spawn
        self.alive_this_wave = []
        self._t = 0.0

    # --------------------------------------------------------
    def on_start(self):
        # Don't spawn enemy_groups (they should be empty for wave_defense).
        # Schedule first wave instead.
        if self.waves:
            self.next_wave_at = self.waves[0].get('delay_after_prev', 2.0)
            print(f'[WAVE] First wave in {self.next_wave_at}s')
        else:
            print('[WAVE] No waves declared')

    def on_update(self, dt):
        if self._completed:
            return
        self._t += dt

        # Reap dead enemies from current wave
        self.alive_this_wave = [e for e in self.alive_this_wave
                                if e.enabled and e.hp > 0]

        # If wave cleared, schedule the next
        if (self.wave_idx >= 0
                and not self.alive_this_wave
                and self.next_wave_at is None
                and self.wave_idx + 1 < len(self.waves)):
            bus.publish('wave.cleared', wave=self.wave_idx)
            print(f'[WAVE] Wave {self.wave_idx} cleared')
            nxt = self.waves[self.wave_idx + 1]
            self.next_wave_at = self._t + nxt.get('delay_after_prev', 5.0)
            print(f'[WAVE] Next wave in {nxt.get("delay_after_prev")}s')

        # Spawn the next wave when timer hits
        if self.next_wave_at is not None and self._t >= self.next_wave_at:
            self.wave_idx += 1
            self.next_wave_at = None
            self._spawn_wave(self.waves[self.wave_idx])

        # Lose condition
        if self.params.get('lose_condition'):
            if self._eval_condition(self.params['lose_condition']):
                self._complete(won=False)
                return

        # Win condition: survive all waves AND clear last wave
        if (self.wave_idx + 1 >= len(self.waves)
                and not self.alive_this_wave
                and self.wave_idx >= 0):
            self._complete(won=True)

    # --------------------------------------------------------
    def _spawn_wave(self, wave_cfg):
        kind = wave_cfg.get('type', 'patrol_mech')
        count = wave_cfg.get('count', 3)
        spread = wave_cfg.get('spread', 30)
        cls = registry.get_enemy(kind)
        # Spawn in a ring around player so they come from all sides
        player = self.game.player
        cx, _, cz = (player.position.x, 0, player.position.z) if player else (0, 0, 0)
        for i in range(count):
            ang = (i / count) * math.tau + random.uniform(-0.3, 0.3)
            r = spread + random.uniform(-5, 5)
            offset = Vec3(math.cos(ang) * r, 0, math.sin(ang) * r)
            ent = cls(Vec3(cx + offset.x, 2, cz + offset.z))
            self.alive_this_wave.append(ent)
            self._spawned_enemies.append(ent)
        bus.publish('wave.started', wave=self.wave_idx, count=count)
        print(f'[WAVE] Wave {self.wave_idx} spawned: {count} x {kind}')
