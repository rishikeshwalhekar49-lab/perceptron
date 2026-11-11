"""Hyperplane Heist: the twelve campaign vaults.

Each vault teaches one idea.  Units are (x1, x2, label, motion, tag): label 1 is
an Authorized Bot, 0 an Intruder Drone.  selftest.py checks that every vault
can be cracked (or, for the XOR vault, that it cannot) and that the three-star
margin goal is reachable.
"""
import math
import random

from .core import WORLD_CENTRE, Motion, separable_layout


class Level:
    def __init__(self, key, name, units, concept, intro, tip, start=None, locks=(), allowed_errors=0,
                 impossible=False, max_alarms=3, margin_goal=1.0, lesson=None, win_text=None, show_paths=False):
        self.key = key
        self.name = name
        self.units = units
        self.concept = concept
        self.intro = intro
        self.tip = tip
        self.start = start
        self.locks = tuple(locks)
        self.allowed_errors = allowed_errors
        self.impossible = impossible
        self.max_alarms = max_alarms
        self.margin_goal = margin_goal
        self.lesson = lesson
        self.win_text = win_text
        self.show_paths = show_paths

    def points(self, t=0.0):
        """(x1, x2, label) for every unit at time t."""
        out = []
        for x, y, label, motion, _ in self.units:
            if motion is not None:
                x, y = motion.position(x, y, t)
            out.append((x, y, label))
        return out


def _u(x, y, label, motion=None, tag=None):
    return (x, y, label, motion, tag)


def _bots(*xy):
    return [_u(x, y, 1) for x, y in xy]


def _drones(*xy):
    return [_u(x, y, 0) for x, y in xy]


def _crowd():
    points, _ = separable_layout(random.Random(7), 10, 10, gap=1.3, spread=1.3, min_gap=0.95)
    return [_u(round(x, 1), round(y, 1), label) for x, y, label in points]


def _patrol(x, y, to, label, period, phase):
    return _u(x, y, label, Motion("patrol", to=to, period=period, phase=phase))


_SPIN = Motion("spin", centre=WORLD_CENTRE, omega=math.tau / 40.0)

LEVELS = [
    Level("first_night", "First Night",
          _bots((2, 2), (3, 1), (2, 3), (1, 2), (3.5, 2.5)) + _drones((8, 7), (9, 9), (7, 8), (9, 7.5), (7.5, 9)),
          concept="Line up the laser and lock it in.",
          intro="Welcome to the crew. That laser is the vault's brain: a single perceptron. Every green bot must "
                "stand on its SAFE side, every red drone on its ALARM side. Line it up, then press ENTER to lock "
                "it in.",
          tip="Arrows tilt the laser (w₁, w₂), W / S slide it (b). Or grab its glowing ends with the mouse.",
          max_alarms=5, margin_goal=1.5, lesson="neuron"),
    Level("slide", "Slide",
          _bots((1, 2.5), (2.2, 1.2), (3.2, 2), (1.5, 4.4), (4.6, 1), (2.6, 3.4))
          + _drones((5.5, 3.5), (3.5, 5.5), (6.8, 5), (4.5, 7), (8.2, 3), (6, 7.8)),
          concept="The bias slides the line.",
          intro="This vault's weights are welded in place: only the bias moves. Slide the laser with W / S, or "
                "drag anywhere on the floor, until the two groups are split.",
          tip="Changing b slides the line without turning it.",
          start=(-0.40, -0.40, 1.60), locks=("w1", "w2"), margin_goal=0.9, lesson="boundary"),
    Level("spin", "Spin",
          _bots((1.5, 5), (2.5, 7), (3, 5.5), (4, 8.5), (1, 8)) + _drones((5, 1.5), (7, 2.5), (8, 5), (6, 4), (9, 3.5)),
          concept="The weights turn the line.",
          intro="Here the bias is stuck at zero, so the laser always runs through the corner (0, 0). Turn it with "
                "the weights: the arrows, Q / E, or drag its far end.",
          tip="With b = 0 the boundary passes through the origin. The weights only set its direction.",
          start=(0.45, -0.15, 0.0), locks=("b",), margin_goal=1.0, lesson="boundary"),
    Level("flip", "Wrong Side",
          [_u(x, y, 1) for x, y in ((8, 7), (9, 9), (7, 8), (9, 7.5), (7.5, 9))]
          + [_u(x, y, 0) for x, y in ((2, 2), (3, 1), (2, 3), (1, 2), (3.5, 2.5))],
          concept="Flip every sign to swap the sides.",
          intro="Something's off. The laser sits in the perfect spot, yet every unit is on the wrong side. "
                "Multiply w₁, w₂ and b by -1: same line, sides swapped. Press F or right-click to flip it.",
          tip="Flipping every sign keeps the line and swaps SAFE and ALARM.",
          start=(-0.40, -0.40, 4.20), margin_goal=2.0, lesson="boundary"),
    Level("squeeze", "Tight Squeeze",
          _bots((3, 4.34), (6, 5.84), (1.5, 5.5), (4.5, 6.8), (8, 7.9), (2.5, 7.8))
          + _drones((4.5, 4.41), (8, 6.16), (2, 2.2), (6.5, 3.8), (8.8, 4.2), (3.8, 1.2)),
          concept="Margin: centre the line in the gap.",
          intro="Tight squeeze: barely half a tile between the groups. Tap keys for 0.01 steps, or drag slowly. "
                "For three stars, centre the laser in the gap.",
          tip="Margin = distance from the laser to the closest unit. A centred line has the most margin.",
          start=(0.30, 0.30, -3.00), margin_goal=0.22, lesson="boundary"),
    Level("vertical", "Vertical Limit",
          _bots((2, 1.5), (3.6, 3), (1.5, 5), (4.2, 6.5), (3, 8.5), (4.3, 9))
          + _drones((6, 1.2), (6.4, 4), (8, 2.5), (6.8, 7.5), (8.5, 8.8), (6.6, 9.2)),
          concept="Slope = -w₁ / w₂.",
          intro="The crews are split left and right, so you need a nearly vertical laser. The slope of the line "
                "is -w₁ / w₂: make w₂ tiny.",
          tip="As w₂ shrinks toward 0, the laser stands upright.",
          start=(0.10, 0.40, -2.20), margin_goal=0.8, lesson="boundary"),
    Level("crowd", "Crowd Control", _crowd(),
          concept="Many points, still one line.",
          intro="Twenty units, one laser. Look for the widest empty lane between the two crowds.",
          tip="However many points there are, a perceptron only ever draws one straight line.",
          margin_goal=0.5, lesson="sum"),
    Level("patrol", "Patrol",
          [_patrol(0.9, 7.0, (2.6, 5.4), 1, 5.0, 0.0), _patrol(1.2, 1.6, (3.6, 1.0), 1, 6.0, 1.3),
           _patrol(2.4, 3.4, (4.2, 3.0), 1, 7.0, 2.6), _patrol(5.8, 1.0, (6.6, 1.6), 1, 5.5, 4.0),
           _patrol(9.0, 4.0, (8.0, 5.6), 0, 6.5, 0.7), _patrol(4.6, 8.8, (6.8, 8.4), 0, 5.2, 2.0),
           _patrol(8.8, 8.6, (9.2, 6.6), 0, 7.5, 3.3), _patrol(5.6, 6.6, (6.8, 5.6), 0, 6.0, 5.1)],
          concept="Separate whole routes, not just positions.",
          intro="Guards on patrol. Each unit walks its dotted route back and forth. Find a laser that keeps every "
                "whole route on the right side; then it doesn't matter when you lock in.",
          tip="A good boundary works for every position a unit can take, not just where it stands now.",
          margin_goal=1.0, lesson="boundary", show_paths=True),
    Level("carousel", "Carousel",
          [_u(x, y, 1, _SPIN) for x, y in ((1.6, 5.0), (2.4, 6.3), (2.6, 3.8), (3.4, 5.2), (1.9, 7.2))]
          + [_u(x, y, 0, _SPIN) for x, y in ((8.4, 5.0), (7.6, 3.7), (7.4, 6.2), (6.6, 4.8), (8.1, 2.8))],
          concept="Timing: the units keep moving.",
          intro="The vault floor is spinning, but your laser isn't. Line it up with the gap and lock in at the "
                "right moment, before the crowds swing across.",
          tip="Units keep moving while the scanner sweeps, so leave yourself some margin.",
          margin_goal=1.0, lesson="boundary"),
    Level("and_gate", "Logic Gate",
          [_u(2.5, 2.5, 0, tag="(0, 0)"), _u(2.5, 7.5, 0, tag="(0, 1)"), _u(7.5, 2.5, 0, tag="(1, 0)"),
           _u(7.5, 7.5, 1, tag="(1, 1)")],
          concept="One perceptron = one logic gate.",
          intro="Read the floor as a truth table: left or right is input A (0 or 1), down or up is input B. Only "
                "(1, 1) is authorized. You're building an AND gate.",
          tip="w₁ = w₂ = 1, b = -1.5 is the classic AND gate on 0 / 1 inputs.",
          margin_goal=1.5, lesson="gates",
          win_text="That's an AND gate: output 1 only when both inputs are 1. One perceptron can do AND, OR, "
                   "NAND and NOT."),
    Level("noisy", "Noisy Sensors",
          _bots((1.5, 2.0), (2.8, 1.2), (2.2, 3.4), (3.8, 2.6), (1.2, 4.6), (4.6, 1.2), (3.4, 4.4), (8.0, 7.9))
          + _drones((6.5, 8.0), (8.2, 6.6), (7.0, 6.0), (8.9, 8.9), (5.8, 7.0), (9.0, 5.0), (6.8, 9.2)),
          concept="Noisy data: aim for the fewest errors.",
          intro="One of the bots reports from the wrong side of the room: a faulty sensor. No laser can be "
                "perfect here, so the vault forgives one error. Don't chase the outlier.",
          tip="When no line separates everything, the learning rule never settles. Aim for the fewest errors.",
          allowed_errors=1, margin_goal=1.2, lesson="convergence"),
    Level("xor", "The Impossible Vault",
          _bots((2.0, 7.2), (3.0, 8.0), (7.0, 2.0), (8.0, 3.0)) + _drones((2.0, 3.0), (3.0, 2.0), (7.0, 8.0), (8.0, 7.0)),
          concept="Some vaults no line can crack.",
          intro="Last job. Two bot squads in opposite corners, two drone squads in the others. Crack it with the "
                "laser... or, if you're sure no straight line can do it, press X to prove the vault is impossible.",
          tip="XOR: the classic problem a single perceptron cannot solve.",
          impossible=True, margin_goal=0.0, lesson="beyond",
          win_text="Proven: no straight line separates XOR. Minsky & Papert made this limit of a single perceptron "
                   "famous in 1969. Two layers fix it: see the Academy."),
]

LEVEL_KEYS = [level.key for level in LEVELS]
