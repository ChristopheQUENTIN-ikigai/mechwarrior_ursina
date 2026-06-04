"""
main.py
=======
Entrypoint. Parses CLI args, builds Game, runs it.

Usage:
    python main.py
    python main.py --scenario arena_duel
    python main.py --scenario wave_defense
    python main.py --scenario canyon_ambush
    python main.py --scenario mod_demo --mods example_mod
    python main.py --list

Available scenarios are determined by *.json files in scenarios/.
Available mods are folders under mods/ containing mod.json.
"""

import argparse
import os
import sys


def parse_args():
    p = argparse.ArgumentParser(prog='mech2', description='Mech Tactical Arena')
    p.add_argument('--scenario', '-s', default='megacity_skirmish',
                   help='Scenario id (default: megacity_skirmish)')
    p.add_argument('--mods', '-m', nargs='*', default=[],
                   help='Mods to load by id (folder name under mods/). '
                        'Use "all" to autoload every mod.')
    p.add_argument('--list', '-l', action='store_true',
                   help='List available scenarios and mods, then exit.')
    p.add_argument('--verbose-events', '-v', action='store_true',
                   help='Print every event bus message (debug).')
    return p.parse_args()


def list_content():
    print('Scenarios:')
    sd = 'scenarios'
    if os.path.isdir(sd):
        for f in sorted(os.listdir(sd)):
            if f.endswith('.json'):
                print(f'  {f[:-5]}')
    print('Mods:')
    md = 'mods'
    if os.path.isdir(md):
        for d in sorted(os.listdir(md)):
            if os.path.isfile(os.path.join(md, d, 'mod.json')):
                print(f'  {d}')


def main():
    args = parse_args()
    if args.list:
        list_content()
        return 0

    # Resolve --mods all
    mods = args.mods
    if mods == ['all']:
        mods = 'all'

    from core.game import Game
    game = Game(scenario=args.scenario, mods=mods,
                verbose_events=args.verbose_events)

    # Ursina expects module-level update() and input(key). They forward
    # to the Game instance.
    import builtins
    import sys as _sys

    # Build Ursina-visible callbacks in main module namespace
    main_module = _sys.modules[__name__]
    setattr(main_module, 'update', game.update)
    setattr(main_module, 'input',  game.dispatch_input)

    game.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
