#!/usr/bin/env python3
"""
HYPERPLANE HEIST - a perceptron puzzle game
===========================================

You are a master thief inside a vault whose security system is one Perceptron.
Its decision boundary is drawn across the vault floor as a laser:

        w1*x1 + w2*x2 + b = 0

Units standing where  w1*x1 + w2*x2 + b > 0  scan as SAFE (1); everything else
trips the ALARM (0).  Put every Authorized Bot (label 1) on the safe side and
every Intruder Drone (label 0) on the alarm side.  Lock in a wrong boundary
and the Perceptron fights back with one step of its learning rule.

Modes
-----
    CAMPAIGN       12 hand-made vaults, one idea each, 3 stars apiece
    ENDLESS HEIST  procedural waves, boss vaults, perks, combos, shields
    DAILY HEIST    10 waves, the same for everyone on the same day
    ACADEMY        8 interactive lessons on how a perceptron works, and a quiz

Controls
--------
    LEFT / RIGHT     decrease / increase weight w1   (tilts the laser)
    DOWN / UP        decrease / increase weight w2   (tilts the laser)
    S / W            decrease / increase bias b      (slides the laser)
    SPACE            increase bias b  (SHIFT + SPACE decreases it)
    Q / E            turn the laser
    F, right-click   flip: same line, SAFE and ALARM swap
    mouse            drag an end to aim, the beam to slide, the floor to draw
    ENTER            lock in the boundary
    X                declare that no straight line can split the vault
    T                Auto-Trainer (an Endless perk)
    M                sound on / off          ESC   pause / back

Run:       python3 hyperplane_heist.py
Requires:  pygame 2.x   (python3 -m pip install pygame)
           pip has no pygame 2.6.1 build for Python 3.14; tested on Python 3.11.
Progress:  ~/.hyperplane_heist/save.json  (set HYPERPLANE_HEIST_SAVE to move it)
Sound:     set HYPERPLANE_HEIST_AUDIO=0 to play without opening any audio device

The Perceptron class itself lives in heist/core.py.
"""
import sys

try:
    import pygame  # noqa: F401
except ImportError:
    sys.exit("Hyperplane Heist needs pygame 2.\n"
             "Install it with:   python3 -m pip install pygame\n"
             "If pip finds no version for your Python (it has none for 3.14), use an older one such as 3.11.")

from heist.app import main
from heist.core import Perceptron  # noqa: F401  (re-exported for anyone looking for it here)

if __name__ == "__main__":
    main()
