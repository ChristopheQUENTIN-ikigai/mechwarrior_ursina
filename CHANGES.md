# mech2_v2 — Audit & Fixes

Summary of the audit pass and every change made. Three reported problems
(see-through ground, no weapons, weak enemies) plus several latent bugs found
along the way. The environment used for this work was headless (no GPU), so
rendering changes are correct-by-inspection and all *logic* is covered by a
headless test harness in `tests/` (56 logic + 11 map tests, all passing).

## Reported problems

### 1. Transparent / see-through ground  — FIXED
**Cause:** no map builder ever created a floor. `systems/terrain_stream.py`
existed but was never instantiated, so the only thing behind the buildings was
the `Sky()`. The player's "am I grounded?" downward raycast hit nothing, so the
mech floated and enemies sank.
**Fix:** new shared builder `maps/_ground.py::build_ground()` lays down one
flat textured slab whose top sits at `y=0` (matching how buildings are placed
at `y = height/2`). Called first by every map (`megacity`, `arena_flat`,
`canyon`). One entity + one box collider — cheap, and gives raycasts a real
surface. Per-map texture/tint live in `config.json → "ground"`.

### 2. No weapons  — FIXED / EXTENDED
`config.json` already defined rail gun (hitscan), rocket pod (salvo) and
heat-seeker (homing). Added the two that were missing, both on the existing
`hitscan` path:
- **laser** — light, fast, *continuous* (hold to fire, ~20 pulses/s, cooldown-gated), low heat. Key **4**.
- **gauss** — heavy charged hitscan, big damage, long cooldown. Key **5**.

Full loadout now: gatling(LMB), railgun(RMB), rocketpod(1), heatseeker(2),
sniper(3), laser(4), gauss(5).

### 3. Weak / inactive enemies  — FIXED
**Cause:** `EnemyMech._find_player()` re-scanned every entity in the scene each
frame for every enemy (O(entities × enemies)); enemies fired straight down their
own facing with no aiming and no line-of-sight check (so they "shot" through
walls and rarely hit).
**Fix:**
- Player lookup is cached module-side and only re-scans when the reference is
  gone — O(1) per enemy per frame.
- Enemies now aim projectiles at the player's center of mass from their muzzle.
- New `_has_line_of_sight()` raycast: an enemy only fires when nothing solid is
  between it and the player.
- Enemies are clamped to the ground plane on spawn and each frame (no more
  floating/sinking).

## Latent bugs found & fixed

- **KeyError crash on partial loadouts.** `PlayerMech.input()` hard-referenced
  `self.weapons['rocketpod'/'heatseeker'/'sniper']`; pressing those keys on a
  loadout that didn't include them (e.g. arena_duel) crashed. Firing was also
  wired in *two* places (the Entity input + InputRouter), risking double-fire.
  → Removed the per-key dispatch from the entity; all firing goes through one
  path. Weapons now bind by convention `fire_<key>`, so new/mod weapons are
  picked up automatically (`core/game.py::_wire_input`).
- **Damage bypassed the event system.** Projectile/hitscan hits did
  `target.hp -= dmg; destroy(target)` directly, so `enemy.killed` /
  `player.killed` / `player.damaged` never fired, and the player *entity* got
  destroyed on death (scenarios should handle the loss, not the entity).
  → All damage now routes through a `take_damage()` hook (`_damage_entity()` in
  `systems/weapons.py`); events fire correctly and the player entity survives so
  the scenario can run its lose condition.
- **Projectiles could detonate on their own shooter.** Added an `owner` ignore
  set (shooter + body parts) to every projectile/hitscan so a mech can't kill
  itself with its own muzzle.

## Optimization

- **Draw calls (the big one).** The city was ~184 entities / ~146 colliders —
  one draw call + collider per building cube. `maps/megacity.py` now collects
  building *specs* and batches them per-texture with Ursina's `Entity.combine()`
  into a handful of merged meshes. Controlled by `config.json → city.batch`
  (default **true**); the original one-entity-per-building path is kept intact as
  an automatic fallback if `combine()` ever fails, and can be forced with
  `"batch": false`. Trade-off: a batched (merged) building can't be individually
  tinted when shot, so the cosmetic hit-flash is skipped on batched buildings
  (gameplay damage is unaffected — buildings aren't damageable targets anyway).
- **Startup CPU.** `systems/tex_gen.py` generated textures with pure-Python
  per-pixel loops (the window-facade builder looped every window for every
  pixel). Rewrote the four pattern builders to be numpy-vectorized
  (~20× faster on a 64×64 facade in measurement); the per-pixel versions remain
  as a fallback when numpy isn't installed. Visual patterns are unchanged.

## Notes / deliberate choices

- `systems/terrain_stream.py` is left unused on purpose — the world geometry is
  flat (buildings sit on `y=0`), so a flat slab is the correct floor; rolling
  procedural terrain would make buildings clip. The streamer can be revived
  later if the design moves to heightmap terrain.
- City batching is untestable headlessly (no real `combine()`), so it ships
  on-by-default *with* the safe fallback. If the merged city ever looks wrong on
  your GPU, set `city.batch = false` in `config.json`.

## Tests

Headless harness (no GPU / Panda3D needed) under `tests/`:
- `tests/mock_ursina.py` — minimal stand-in for the `ursina` package.
- `tests/run_tests.py` — 56 logic checks: weapon resolution & firing,
  cooldown/heat/overheat gating, charged-gauss damage, homing acquisition &
  steering, damage→event flow, enemy FSM + line-of-sight gating, ground
  clamping, scenario win/lose conditions, numpy texture arrays.
- `tests/map_smoke.py` — 11 checks: ground slab placement, batched vs unbatched
  city build.

Run:
```
cd tests
python3 run_tests.py
python3 map_smoke.py
```
