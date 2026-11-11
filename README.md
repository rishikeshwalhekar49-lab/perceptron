# Hyperplane Heist

A heist game about a single perceptron. The vault's whole security system is one artificial neuron, and its decision boundary is a laser across the floor:

```
w₁·x₁ + w₂·x₂ + b = 0
```

Put every Authorized Bot on the laser's SAFE side and every Intruder Drone on its ALARM side, then lock it in. Get it wrong and the perceptron fights back with one step of its learning rule, and the laser snaps somewhere new.

![A 35-second tour of the game](hyperplane_heist_demo.gif)

## Play

You need Python 3 and pygame 2. It is tested with Python 3.11 and pygame 2.6.1. pip has no pygame build for Python 3.14 yet, so use 3.13 or older.

```bash
python3 -m pip install -r requirements.txt
python3 hyperplane_heist.py
```

## Modes

- **Campaign:** 12 hand-made vaults, each teaching one idea (bias, rotation, flipping sides, margin, patrols, a spinning floor, an AND gate, noisy data), with up to 3 stars each. The last vault is XOR: you win it by proving that no line can.
- **Endless Heist:** generated waves with a timer, combos and shields. Expect moving vaults, imposter drones, a boss every 5th wave and a perk after each boss.
- **Daily Heist:** the same 10 waves for everyone on the same day.
- **Academy:** 8 hands-on lessons on how a perceptron works, with every formula computed live from sliders, and a quiz with fresh numbers each time.

There are ranks, 22 achievements, 6 laser colours to unlock and a local top-10 leaderboard. Sound and music are generated in code, so there are no asset files.

## Controls

| Key | Action |
| --- | --- |
| ← → | change w₁ (tilts the laser) |
| ↓ ↑ | change w₂ (tilts the laser) |
| W / S, SPACE | change the bias b (slides the laser); SHIFT + SPACE lowers b |
| Q / E, mouse wheel | turn the laser |
| F, right-click | flip: same line, SAFE and ALARM swap |
| Mouse drag | drag an end to aim, the beam to slide, or the floor to draw a new laser |
| ENTER | lock in |
| X | declare that no straight line can split the vault |
| T | Auto-Trainer (an Endless perk) |
| M | sound on / off |
| ESC | pause / back |

## Notes

- Progress is saved to `~/.hyperplane_heist/save.json`. Set `HYPERPLANE_HEIST_SAVE` to move it.
- Set `HYPERPLANE_HEIST_AUDIO=0` to play without opening any audio device.
- `python3 selftest.py` runs a headless self-test (no window) that never touches your save file.
- The perceptron itself is the `Perceptron` class in `heist/core.py`.
