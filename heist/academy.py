"""Hyperplane Heist: the Academy: interactive lessons on how a perceptron works, and a quiz.

Every formula on these pages is computed live from the sliders, so what you
read is always what the plot shows.
"""
import math
import random

import pygame

from .core import (Perceptron, boundary_endpoints, clamp, count_errors, ease_out, lerp, project_onto_line,
                   signed_distance)
from .gfx import (AMBER, BLACK, C_B, C_ETA, C_W, C_X, C_Y, C_Z, CYAN, GOLD, GREEN, INK, PANEL_EDGE, PINK, RED,
                  TEXT, TEXT_DIM, TEXT_FAINT, VIOLET, WHITE, Viewport, dashed_line, draw_arc, draw_bot, draw_drone,
                  draw_grid, draw_laser, draw_nyx, draw_star, draw_weight_arrow, draw_zones, mix, panel, scale_color,
                  thick_line)
from .save import LESSON_IDS
from .scene import Scene
from .ui import Button, Slider, SliderGroup, back_button

TEXT_X, TEXT_W = 56, 540
VIEW_RECT = pygame.Rect(660, 128, 440, 440)
CONFIRM = (pygame.K_RETURN, pygame.K_KP_ENTER)

# A small separable training set: bots above the line x2 = x1 + 1, drones below it.
TRAIN_POINTS = ((2.0, 6.0, 1), (6.0, 2.0, 0), (3.0, 8.0, 1), (8.0, 3.5, 0), (1.5, 8.5, 1), (7.0, 1.0, 0),
                (4.0, 7.2, 1), (5.5, 4.0, 0))
TRUE_LINE = (-1.0, 1.0, -1.0)
NOISY_POINTS = TRAIN_POINTS + ((7.5, 2.5, 1),)
TRAIN_START = (0.4, -0.3, -0.2)


def f2(v):
    return "{:.2f}".format(round(v, 2) + 0.0)


def f1(v):
    return "{:g}".format(round(v, 1) + 0.0)


def z_segments(w1, w2, b, x1, x2):
    z = w1 * x1 + w2 * x2 + b
    return [("z = ", C_Z), ("(" + f2(w1) + ")", C_W), ("·" + f1(x1), C_X), (" + ", TEXT), ("(" + f2(w2) + ")", C_W),
            ("·" + f1(x2), C_X), (" + ", TEXT), ("(" + f2(b) + ")", C_B), (" = ", TEXT), (f2(z), C_Z)]


def draw_points(surf, vp, points, time, scale=0.7, highlight=None):
    for i, (x1, x2, label) in enumerate(points):
        x, y = vp.to_screen(x1, x2)
        if highlight == i:
            pygame.draw.circle(surf, GOLD, (x, y), 22, 2)
        if label == 1:
            draw_bot(surf, x, y, time + i, 0.0, scale)
        else:
            draw_drone(surf, x, y, time + i, 0.0, scale)


class Trainer:
    """Runs the perceptron learning rule one sample at a time, in a fixed order."""

    def __init__(self, points, lr=0.1, start=(0.0, 0.0, 0.0)):
        self.points = list(points)
        self.lr = lr
        self.start = start
        self.reset()

    def reset(self, start=None):
        if start is not None:
            self.start = start
        self.brain = Perceptron()
        self.brain.set_params(*self.start)
        self.index = 0
        self.epoch = 1
        self.epoch_mistakes = 0
        self.updates = 0
        self.converged = False
        self.last = None
        self.current = None
        self.history = []

    def step(self):
        if self.converged:
            return None
        x1, x2, label = self.points[self.index]
        old = self.brain.params
        predicted = self.brain.predict(x1, x2)
        changed = self.brain.train(x1, x2, label, self.lr)
        self.last = {"point": (x1, x2), "label": label, "pred": predicted, "old": old, "new": self.brain.params,
                     "changed": changed}
        self.current = self.index
        if changed:
            self.updates += 1
            self.epoch_mistakes += 1
            self.history.append(old)
            del self.history[:-10]
        self.index += 1
        if self.index >= len(self.points):
            if self.epoch_mistakes == 0:
                self.converged = True
            else:
                self.epoch += 1
            self.index = 0
            self.epoch_mistakes = 0
        return self.last

    def run(self, max_steps=100000):
        steps = 0
        while not self.converged and steps < max_steps:
            self.step()
            steps += 1
        return self.converged


def mistake_bound(points, line):
    """Novikoff's bound (R / gamma)^2 for a zero start, using augmented inputs (x1, x2, 1)."""
    w1, w2, b = line
    norm = math.sqrt(w1 * w1 + w2 * w2 + b * b)
    radius = max(math.sqrt(x1 * x1 + x2 * x2 + 1.0) for x1, x2, _ in points)
    gamma = min((1 if label == 1 else -1) * (w1 * x1 + w2 * x2 + b) / norm for x1, x2, label in points)
    return radius, gamma, (radius / gamma) ** 2


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
class Page:
    title = ""

    def __init__(self, lesson):
        self.lesson = lesson
        self.app = lesson.app
        self.gfx = lesson.gfx
        self.audio = lesson.audio
        self.time = 0.0
        self.sliders = None
        self.zones = []             # (rect, callback): clickable spots registered while drawing

    def zone(self, rect, callback):
        self.zones.append((pygame.Rect(rect), callback))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, callback in self.zones:
                if rect.collidepoint(event.pos):
                    callback()
                    return True
        return self.sliders.handle_event(event) if self.sliders else False

    def key_buttons(self, surf, x, y, items):
        """Key hints that are also buttons: items = [(key, label, callback)]."""
        for key, label, callback in items:
            start = x
            x = self.gfx.key_hint(surf, x, y, [key], label)
            rect = pygame.Rect(start - 5, y - 2, x - 16 - start + 10, 24)
            pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=6)
            self.zone(rect, callback)
        return x

    def update(self, dt):
        self.time += dt
        if self.sliders:
            self.sliders.update(dt)

    def draw(self, surf):
        pass

    # helpers
    def para(self, surf, text, y, color=TEXT, font=None, x=TEXT_X, width=TEXT_W):
        return self.gfx.paragraph(surf, font or self.gfx.body, text, x, y, width, color, gap=5) + 8

    def formula(self, surf, segments, y, font=None, x=TEXT_X):
        font = font or self.gfx.mid
        self.gfx.rich(surf, font, segments, (x, y))
        return y + font.get_height() + 10

    def label(self, surf, text, y, color=CYAN, x=TEXT_X):
        self.gfx.text(surf, self.gfx.label, text, (x, y), color)
        return y + 20

    def weight_sliders(self, y, w=(0.4, -0.5), b=2.0, w_range=1.0, b_range=6.0, on_change=None, width=TEXT_W - 20):
        sliders = [Slider("w1", "w₁  weight on x₁", -w_range, w_range, w[0], 0.01, C_W),
                   Slider("w2", "w₂  weight on x₂", -w_range, w_range, w[1], 0.01, C_W),
                   Slider("b", "b  bias", -b_range, b_range, b, 0.05, C_B)]
        self.sliders = SliderGroup(sliders, TEXT_X, y, width, 54, on_change, self.app)
        return self.sliders

    def params(self):
        v = self.sliders.values()
        return v["w1"], v["w2"], v["b"]


class NeuronPage(Page):
    title = "One neuron, three numbers"

    def __init__(self, lesson):
        super().__init__(lesson)
        sliders = [Slider("x1", "x₁  input", 0, 10, 3.0, 0.1, C_X, lambda v: f1(v)),
                   Slider("x2", "x₂  input", 0, 10, 6.0, 0.1, C_X, lambda v: f1(v)),
                   Slider("w1", "w₁  weight", -1, 1, 0.4, 0.01, C_W),
                   Slider("w2", "w₂  weight", -1, 1, -0.5, 0.01, C_W),
                   Slider("b", "b  bias", -5, 5, 2.0, 0.05, C_B)]
        self.sliders = SliderGroup(sliders, TEXT_X, 262, TEXT_W - 20, 54, None, self.app)

    def draw(self, surf):
        gfx = self.gfx
        v = self.sliders.values()
        x1, x2, w1, w2, b = v["x1"], v["x2"], v["w1"], v["w2"], v["b"]
        z = w1 * x1 + w2 * x2 + b
        out = 1 if z > 0 else 0
        y = self.para(surf, "A perceptron is the simplest artificial neuron. It multiplies each input by a weight, "
                            "adds a bias, and fires 1 if the total is above zero. Otherwise it outputs 0.", 112)
        y = self.formula(surf, z_segments(w1, w2, b, x1, x2), y + 4, gfx.body)
        self.formula(surf, [("ŷ = ", C_Y), (str(out), GREEN if out else RED),
                            ("   because z > 0" if out else "   because z is not > 0", TEXT_DIM)], y - 4, gfx.body)
        self.sliders.draw(surf, gfx, self.time)
        # the diagram
        nodes = {"x1": (690, 230), "x2": (690, 430), "one": (800, 560), "sum": (900, 330), "step": (1010, 330),
                 "out": (1110, 330)}
        edges = (("x1", w1, x1, "w₁"), ("x2", w2, x2, "w₂"), ("one", b, 1.0, "b"))
        for name, weight, value, symbol in edges:
            a, e = nodes[name], nodes["sum"]
            color = C_B if name == "one" else (C_W if weight >= 0 else AMBER)
            width = 2 + int(min(8, abs(weight) * (1.2 if name == "one" else 7)))
            thick_line(surf, scale_color(color, 0.55), a, e, width)
            contribution = abs(weight * value)
            speed = 0.6 + min(2.0, contribution * 0.4)
            for k in range(3):
                t = (self.time * speed + k / 3.0) % 1.0
                px, py = lerp(a[0], e[0], t), lerp(a[1], e[1], t)
                pygame.draw.circle(surf, mix(color, WHITE, 0.4), (px, py), 2 + min(6, contribution * 1.5))
            mx, my = lerp(a[0], e[0], 0.42), lerp(a[1], e[1], 0.42)
            text = "{} = {}".format(symbol, f2(weight))
            plate = pygame.Rect(0, 0, gfx.label.size(text)[0] + 12, 20)
            plate.center = (int(mx), int(my))
            surf.blit(gfx.plate(plate.size, (8, 10, 20, 235), 6), plate)
            gfx.text(surf, gfx.label, text, plate.center, color, "center")
        for name, text, value in (("x1", "x₁", f1(x1)), ("x2", "x₂", f1(x2)), ("one", "1", "")):
            cx, cy = nodes[name]
            pygame.draw.circle(surf, INK, (cx, cy), 30)
            pygame.draw.circle(surf, C_B if name == "one" else TEXT, (cx, cy), 30, 2)
            gfx.text(surf, gfx.mid, text, (cx, cy - (8 if value else 0)), WHITE, "center")
            if value:
                gfx.text(surf, gfx.small, value, (cx, cy + 12), TEXT_DIM, "center")
        cx, cy = nodes["sum"]
        pygame.draw.circle(surf, INK, (cx, cy), 44)
        pygame.draw.circle(surf, C_Z, (cx, cy), 44, 3)
        gfx.text(surf, gfx.title, "Σ", (cx, cy - 8), C_Z, "center")
        gfx.text(surf, gfx.small, "z = " + f2(z), (cx, cy + 22), C_Z, "center")
        thick_line(surf, scale_color(C_Z, 0.6), (cx + 44, cy), (nodes["step"][0] - 34, cy), 3)
        sx, sy = nodes["step"]
        box = pygame.Rect(0, 0, 68, 68)
        box.center = (sx, sy)
        pygame.draw.rect(surf, INK, box, border_radius=8)
        pygame.draw.rect(surf, TEXT_DIM, box, 2, border_radius=8)
        pygame.draw.lines(surf, WHITE, False, [(sx - 24, sy + 14), (sx, sy + 14), (sx, sy - 14), (sx + 24, sy - 14)], 2)
        gfx.text(surf, gfx.tiny, "step", (sx, sy + 44), TEXT_DIM, "center")
        thick_line(surf, scale_color(GREEN if out else RED, 0.7), (sx + 34, sy), (nodes["out"][0] - 32, sy), 3)
        ox, oy = nodes["out"]
        color = GREEN if out else RED
        if out:
            gfx.add_glow(surf, ox, oy, 60, GREEN, 0.6)
        pygame.draw.circle(surf, INK, (ox, oy), 32)
        pygame.draw.circle(surf, color, (ox, oy), 32, 3)
        gfx.text(surf, gfx.title, str(out), (ox, oy - 2), color, "center")
        gfx.text(surf, gfx.small, "ŷ = " + ("SAFE" if out else "ALARM"), (ox, oy + 48), color, "center")
        gfx.text(surf, gfx.small, "↑ ↓ choose a slider, ← → change it, or drag", (TEXT_X, 548), TEXT_FAINT)


class FormulaPage(Page):
    title = "The formula"

    def draw(self, surf):
        gfx = self.gfx
        y = self.label(surf, "THE PERCEPTRON", 116)
        y = self.formula(surf, [("z", C_Z), (" = ", TEXT), ("w₁", C_W), ("·", TEXT), ("x₁", C_X), (" + ", TEXT),
                                ("w₂", C_W), ("·", TEXT), ("x₂", C_X), (" + ", TEXT), ("b", C_B)], y + 6, gfx.title)
        y = self.formula(surf, [("ŷ", C_Y), (" = 1  if  ", TEXT), ("z", C_Z), (" > 0,   otherwise  ", TEXT),
                                ("ŷ", C_Y), (" = 0", TEXT)], y + 4, gfx.mid)
        rows = (("x₁, x₂", C_X, "the inputs: here, a unit's position on the vault floor"),
                ("w₁, w₂", C_W, "the weights: how much each input matters, and in which direction"),
                ("b", C_B, "the bias: how eager the neuron is to fire, even when the inputs are 0"),
                ("z", C_Z, "the weighted sum, a score: big positive = confident 1"),
                ("ŷ", C_Y, "y-hat, the prediction. y without the hat is the true label"))
        y += 14
        for symbol, color, text in rows:
            gfx.text(surf, gfx.mid, symbol, (TEXT_X, y), color)
            gfx.paragraph(surf, gfx.body, text, TEXT_X + 110, y + 2, TEXT_W - 110, TEXT)
            y += 46
        box = pygame.Rect(660, 128, 440, 300)
        panel(surf, box, (14, 18, 34), PANEL_EDGE, 12)
        gfx.text(surf, gfx.label, "IN THE GAME", (box.left + 24, box.top + 20), AMBER)
        lines = ("Every unit stands at (x₁, x₂).", "The laser computes z for it.",
                 "ŷ = 1: the unit is SAFE (bots belong here).", "ŷ = 0: ALARM (drones belong here).",
                 "The laser itself is every spot where z = 0.")
        yy = box.top + 52
        for line in lines:
            gfx.text(surf, gfx.body, line, (box.left + 24, yy), TEXT)
            yy += 30
        draw_bot(surf, box.left + 60, box.bottom - 50, self.time, 0.0, 1.0)
        gfx.text(surf, gfx.small, "label y = 1", (box.left + 90, box.bottom - 58), GREEN)
        draw_drone(surf, box.left + 250, box.bottom - 50, self.time, 0.0, 1.0)
        gfx.text(surf, gfx.small, "label y = 0", (box.left + 280, box.bottom - 58), RED)
        self.para(surf, "Weights and bias are the only things a perceptron can change. Learning means finding "
                        "good values for them.", 452, TEXT_DIM, x=660, width=440)


class BiologyPage(Page):
    title = "Where the idea comes from"

    def draw(self, surf):
        gfx = self.gfx
        y = self.para(surf, "Brain cells pass signals along their branches. Each connection can be stronger or "
                            "weaker, and the cell fires once the incoming signals add up past a threshold.", 112)
        rows = (("dendrites", "receive signals", "inputs x₁, x₂"),
                ("synapse strength", "boost or damp a signal", "weights w₁, w₂"),
                ("cell body", "adds the signals up", "weighted sum z"),
                ("threshold", "fire or stay quiet", "step: z > 0 ?"),
                ("axon", "sends the spike on", "output ŷ"))
        gfx.text(surf, gfx.label, "BRAIN", (TEXT_X, y), VIOLET)
        gfx.text(surf, gfx.label, "PERCEPTRON", (TEXT_X + 330, y), CYAN)
        y += 22
        for brain, what, ours in rows:
            gfx.text(surf, gfx.body, brain, (TEXT_X, y), WHITE)
            gfx.text(surf, gfx.small, what, (TEXT_X, y + 20), TEXT_DIM)
            gfx.text(surf, gfx.body, ours, (TEXT_X + 330, y + 8), CYAN)
            y += 50
        y += 6
        y = self.para(surf, "1943: Warren McCulloch and Walter Pitts describe neurons as simple threshold "
                            "switches, but with weights set by hand.", y, TEXT_DIM)
        self.para(surf, "1958: Frank Rosenblatt's perceptron learns its own weights from examples. That is "
                        "the rule you will meet in lesson 5.", y, TEXT_DIM)
        # a drawn neuron
        cx, cy = 900, 340
        t = self.time
        for k in range(6):
            angle = math.pi * (0.62 + 0.15 * k)
            ex, ey = cx + math.cos(angle) * 150, cy + math.sin(angle) * 150
            thick_line(surf, (90, 70, 150), (cx, cy), (ex, ey), 5)
            for side in (-0.4, 0.4):
                bx, by = lerp(cx, ex, 0.75), lerp(cy, ey, 0.75)
                thick_line(surf, (90, 70, 150), (bx, by), (bx + math.cos(angle + side) * 50,
                                                          by + math.sin(angle + side) * 50), 3)
            pulse = (t * 0.8 + k * 0.17) % 1.0
            px, py = lerp(ex, cx, pulse), lerp(ey, cy, pulse)
            pygame.draw.circle(surf, (200, 180, 255), (px, py), 4)
        thick_line(surf, (90, 70, 150), (cx, cy), (cx + 230, cy + 10), 7)
        fire = (t % 2.0) < 0.25
        pygame.draw.circle(surf, (120, 90, 190), (cx, cy), 40)
        pygame.draw.circle(surf, (210, 190, 255) if fire else (150, 120, 220), (cx, cy), 40, 3)
        gfx.text(surf, gfx.small, "cell body", (cx, cy + 56), TEXT_DIM, "center")
        gfx.text(surf, gfx.small, "dendrites", (cx - 150, cy - 170), TEXT_DIM, "center")
        gfx.text(surf, gfx.small, "axon", (cx + 210, cy + 34), TEXT_DIM, "center")
        if fire:
            gfx.add_glow(surf, cx, cy, 90, VIOLET, 0.5)
        spike = ((t % 2.0) / 0.6)
        if spike < 1.0:
            sx = lerp(cx + 40, cx + 230, spike)
            pygame.draw.circle(surf, WHITE, (sx, cy + 10 * spike / 1.0 * 0.5 + 2), 6)


class HeatmapPage(Page):
    title = "Every spot gets a score"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.probe = list(lesson.state.get("probe", (3.0, 6.0)))
        self.dragging = False
        self.heat = None
        self.heat_key = None
        self.weight_sliders(352, (0.4, -0.5), 2.0)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.vp.contains(*event.pos):
            self.dragging = True
            self.move_probe(event.pos)
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.move_probe(event.pos)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        return super().handle_event(event)

    def move_probe(self, pos):
        x, y = self.vp.to_world(*pos)
        self.probe = [clamp(x, 0.0, 10.0), clamp(y, 0.0, 10.0)]
        self.lesson.state["probe"] = tuple(self.probe)

    def heatmap(self, w1, w2, b):
        key = (round(w1, 3), round(w2, 3), round(b, 3))
        if key != self.heat_key:
            size = 64
            small = pygame.Surface((size, size), 0, 32)
            for i in range(size):
                for j in range(size):
                    x1 = (i + 0.5) / size * 10.0
                    x2 = 10.0 - (j + 0.5) / size * 10.0
                    z = w1 * x1 + w2 * x2 + b
                    k = math.tanh(abs(z) / 2.5)
                    base = GREEN if z > 0 else RED
                    small.set_at((i, j), mix((14, 20, 35), scale_color(base, 0.55), k))
            self.heat = pygame.transform.smoothscale(small, self.vp.rect.size)
            self.heat_key = key
        return self.heat

    def draw(self, surf):
        gfx = self.gfx
        w1, w2, b = self.params()
        draw_grid(surf, self.vp, gfx)
        surf.blit(self.heatmap(w1, w2, b), self.vp.rect.topleft)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, CYAN, 0.9, self.time)
        draw_weight_arrow(surf, self.vp, gfx, w1, w2, b)
        px, py = self.vp.to_screen(*self.probe)
        z = w1 * self.probe[0] + w2 * self.probe[1] + b
        pygame.draw.circle(surf, WHITE, (px, py), 9, 2)
        pygame.draw.line(surf, WHITE, (px - 14, py), (px + 14, py))
        pygame.draw.line(surf, WHITE, (px, py - 14), (px, py + 14))
        gfx.text(surf, gfx.label, "z = " + f2(z), (px + 14, py - 22), C_Z)
        y = self.para(surf, "Pick any spot on the floor and the perceptron gives it a score z. Green spots score "
                            "above zero (SAFE), red ones below (ALARM). The brighter the colour, the bigger the "
                            "score. The laser is exactly where z = 0.", 112)
        y = self.formula(surf, z_segments(w1, w2, b, self.probe[0], self.probe[1]), y, gfx.body)
        self.formula(surf, [("Drag the white cross on the floor.", TEXT_DIM)], y - 4, gfx.small)
        self.sliders.draw(surf, gfx, self.time)
        self.para(surf, "Think of z as a tilted ramp over the floor. The weights set which way it slopes, the bias "
                        "lifts it. The laser is where the ramp meets sea level.", 532, TEXT_DIM, gfx.small)


class StepPage(Page):
    title = "From score to decision"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.sliders = SliderGroup([Slider("z", "z  the score", -6, 6, 1.5, 0.05, C_Z)], TEXT_X, 382, TEXT_W - 20,
                                   54, None, self.app)

    def draw(self, surf):
        gfx = self.gfx
        z = self.sliders.values()["z"]
        out = 1 if z > 0 else 0
        y = self.para(surf, "The perceptron only cares about the SIGN of z. A score of 0.01 and a score of 100 "
                            "both give ŷ = 1. That hard jump is called the step function (or Heaviside function).",
                      112)
        y = self.formula(surf, [("step(z) = 1 if ", TEXT), ("z", C_Z), (" > 0, else 0", TEXT)], y + 4)
        y = self.para(surf, "Exactly zero counts as 0 in this game: the boundary itself belongs to the ALARM side.",
                      y, TEXT_DIM)
        self.sliders.draw(surf, gfx, self.time)
        self.formula(surf, [("z = ", C_Z), (f2(z), C_Z), ("   →   ŷ = ", TEXT), (str(out), GREEN if out else RED)],
                     450)
        rect = pygame.Rect(660, 160, 440, 320)
        panel(surf, rect, (14, 18, 34), PANEL_EDGE, 10)
        left, right = rect.left + 30, rect.right - 30
        top, bottom = rect.top + 60, rect.bottom - 70
        zero_x = (left + right) / 2

        def sx(value):
            return lerp(left, right, (value + 6.0) / 12.0)
        pygame.draw.line(surf, TEXT_DIM, (left, bottom), (right, bottom), 1)
        pygame.draw.line(surf, TEXT_DIM, (zero_x, top - 20), (zero_x, bottom + 10), 1)
        pygame.draw.line(surf, CYAN, (left, bottom), (zero_x, bottom), 4)
        pygame.draw.line(surf, CYAN, (zero_x, top), (right, top), 4)
        pygame.draw.circle(surf, INK, (zero_x, top), 6)
        pygame.draw.circle(surf, CYAN, (zero_x, top), 6, 2)
        pygame.draw.circle(surf, CYAN, (zero_x, bottom), 6)
        gfx.text(surf, gfx.small, "1", (left - 14, top), TEXT_DIM, "center")
        gfx.text(surf, gfx.small, "0", (left - 14, bottom), TEXT_DIM, "center")
        for value in (-6, -3, 0, 3, 6):
            gfx.text(surf, gfx.tiny, str(value), (sx(value), bottom + 12), TEXT_DIM, "midtop")
        gfx.text(surf, gfx.small, "z", (right, bottom + 30), C_Z, "center")
        mx = sx(z)
        my = top if out else bottom
        gfx.add_glow(surf, mx, my, 34, GREEN if out else RED, 0.7)
        pygame.draw.circle(surf, GREEN if out else RED, (mx, my), 9)
        gfx.text(surf, gfx.mid, "ŷ = {}".format(out), (rect.centerx, rect.top + 24), GREEN if out else RED, "center")


class SlopePage(Page):
    title = "Slope and intercept"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.weight_sliders(372, (0.4, 0.5), -4.0)

    def draw(self, surf):
        gfx = self.gfx
        w1, w2, b = self.params()
        draw_grid(surf, self.vp, gfx)
        draw_zones(surf, self.vp, w1, w2, b, 34)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, CYAN, 1.0, self.time)
        draw_weight_arrow(surf, self.vp, gfx, w1, w2, b)
        y = self.para(surf, "The laser is every point where z = 0. Solve w₁x₁ + w₂x₂ + b = 0 for x₂ and you get "
                            "the equation of a straight line:", 112)
        y = self.formula(surf, [("x₂", C_X), (" = -(", TEXT), ("w₁", C_W), (" / ", TEXT), ("w₂", C_W),
                                (")·", TEXT), ("x₁", C_X), ("  -  ", TEXT), ("b", C_B), (" / ", TEXT), ("w₂", C_W)], y)
        if abs(w2) > 1e-9:
            slope, cross = -w1 / w2, -b / w2
            y = self.formula(surf, [("slope = -w₁/w₂ = ", TEXT), (f2(slope), WHITE)], y - 2, gfx.body)
            self.formula(surf, [("crosses the x₂ axis at -b/w₂ = ", TEXT), (f2(cross), WHITE)], y - 6, gfx.body)
        else:
            if abs(w1) > 1e-9:
                y = self.formula(surf, [("w₂ = 0: a vertical line at x₁ = -b/w₁ = ", TEXT), (f2(-b / w1), WHITE)],
                                 y - 2, gfx.body)
            else:
                self.formula(surf, [("w₁ = w₂ = 0: no line at all. z = b everywhere.", AMBER)], y - 2, gfx.body)
        self.sliders.draw(surf, gfx, self.time)
        self.para(surf, "Try it: make w₂ tiny and the line stands up. Change only b and the line slides "
                        "without turning.", 540, TEXT_DIM, gfx.small)


class NormalPage(Page):
    title = "The weight vector and distance"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.point = [7.0, 7.5]
        self.dragging = False
        self.weight_sliders(386, (0.3, 0.4), -3.0)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.vp.contains(*event.pos):
            self.dragging = True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if self.dragging and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            x, y = self.vp.to_world(*event.pos)
            self.point = [clamp(x, 0, 10), clamp(y, 0, 10)]
            return True
        return super().handle_event(event)

    def draw(self, surf):
        gfx = self.gfx
        w1, w2, b = self.params()
        draw_grid(surf, self.vp, gfx)
        draw_zones(surf, self.vp, w1, w2, b, 30)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, CYAN, 1.0, self.time)
        draw_weight_arrow(surf, self.vp, gfx, w1, w2, b, length=70)
        norm = math.hypot(w1, w2)
        px, py = self.point
        p = self.vp.to_screen(px, py)
        foot = project_onto_line(w1, w2, b, px, py)
        if foot is not None:
            f = self.vp.to_screen(*foot)
            dashed_line(surf, GOLD, p, f, 2, 6, 5, self.time * 20)
            pygame.draw.circle(surf, GOLD, (int(f[0]), int(f[1])), 4)
        pygame.draw.circle(surf, WHITE, (int(p[0]), int(p[1])), 8)
        pygame.draw.circle(surf, GOLD, (int(p[0]), int(p[1])), 8, 2)
        y = self.para(surf, "The weight vector w = (w₁, w₂) always sits at a right angle to the laser and points "
                            "into the SAFE side. Its length is |w| = √(w₁² + w₂²).", 112)
        y = self.formula(surf, [("|w| = √(", TEXT), (f2(w1), C_W), ("² + ", TEXT), (f2(w2), C_W), ("²) = ", TEXT),
                                (f2(norm), WHITE)], y, gfx.body)
        y = self.para(surf, "Dividing the score by |w| gives the true distance from a point to the laser. Drag the "
                            "gold point:", y - 2)
        if norm > 1e-9:
            z = w1 * px + w2 * py + b
            self.formula(surf, [("distance = |z| / |w| = ", TEXT), (f2(abs(z)), C_Z), (" / ", TEXT), (f2(norm), WHITE),
                                (" = ", TEXT), (f2(abs(z) / norm), GOLD)], y, gfx.body)
        self.sliders.draw(surf, gfx, self.time)
        self.para(surf, "This distance is the margin you collect points for in the game: the bigger the gap to the "
                        "closest unit, the safer the boundary.", 556, TEXT_DIM, gfx.small)


class ScalePage(Page):
    title = "Scale doesn't matter, sign does"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.params_now = [0.3, 0.4, -3.5]
        self.flash = 0.0
        self.note = "Click a row, or press 1, 2, 3 or 4."

    def apply(self, index):
        factors = ((2.0, "×2: every number doubled. Same line, same sides."),
                   (0.5, "×½: every number halved. Still the same line."),
                   (-1.0, "×(-1): same line, but SAFE and ALARM swapped sides!"))
        if index == 3:
            self.params_now = [0.3, 0.4, -3.5]
            self.note = "Back to the start."
            self.audio.play("ui_back")
            return
        k, self.note = factors[index]
        self.params_now = [v * k for v in self.params_now]
        self.flash = 0.6
        self.audio.play("flip" if k < 0 else "tick")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self.apply(event.key - pygame.K_1)
            return True
        return super().handle_event(event)

    def update(self, dt):
        super().update(dt)
        self.flash = max(0.0, self.flash - dt)

    def draw(self, surf):
        gfx = self.gfx
        w1, w2, b = self.params_now
        draw_grid(surf, self.vp, gfx)
        draw_zones(surf, self.vp, w1, w2, b, 34)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, mix(CYAN, WHITE, self.flash), 1.0, self.time)
        draw_weight_arrow(surf, self.vp, gfx, w1, w2, b)
        y = self.para(surf, "Multiply w₁, w₂ and b by the same positive number k and z becomes k·z. The sign of "
                            "z doesn't change, so the line and every prediction stay exactly the same.", 112)
        y = self.para(surf, "Multiply by a negative number and every sign flips: the line stays put, but SAFE and "
                            "ALARM swap. That is the F (flip) key in the game.", y)
        y = self.formula(surf, [("w₁ = ", C_W), (f2(w1), WHITE), ("   w₂ = ", C_W), (f2(w2), WHITE), ("   b = ", C_B),
                                (f2(b), WHITE)], y + 6, gfx.mid)
        for index, (key, text) in enumerate((("1", "multiply everything by 2"), ("2", "multiply everything by ½"),
                                             ("3", "multiply everything by -1"), ("4", "reset"))):
            x = gfx.keycap(surf, TEXT_X, y, key)
            right = gfx.text(surf, gfx.body, text, (x + 6, y + 1), TEXT).right
            rect = pygame.Rect(TEXT_X - 6, y - 3, right - TEXT_X + 14, 26)
            pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=6)
            self.zone(rect, lambda index=index: self.apply(index))
            y += 30
        self.para(surf, self.note, y + 10, GOLD)


class GatesPage(Page):
    title = "Logic gates"
    GATES = (("AND", (0, 0, 0, 1)), ("OR", (0, 1, 1, 1)), ("NAND", (1, 1, 1, 0)), ("XOR", (0, 1, 1, 0)))
    INPUTS = ((0, 0), (0, 1), (1, 0), (1, 1))

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT, (-0.5, 1.5, -0.5, 1.5))
        self.gate = 0
        self.solved = set(lesson.state.get("gates", set()))
        self.tried_xor = 0.0
        sliders = [Slider("w1", "w₁", -2, 2, 0.5, 0.05, C_W), Slider("w2", "w₂", -2, 2, 0.5, 0.05, C_W),
                   Slider("b", "b", -3, 3, 0.0, 0.05, C_B)]
        self.sliders = SliderGroup(sliders, TEXT_X, 448, TEXT_W - 20, 50, None, self.app)

    def select(self, index):
        self.gate = index
        self.audio.play("ui_move")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self.select(event.key - pygame.K_1)
            return True
        return super().handle_event(event)

    def update(self, dt):
        super().update(dt)
        name, targets = self.GATES[self.gate]
        w1, w2, b = self.params()
        outputs = [1 if w1 * x1 + w2 * x2 + b > 0 else 0 for x1, x2 in self.INPUTS]
        if name == "XOR":
            self.tried_xor += dt
        elif outputs == list(targets) and name not in self.solved:
            self.solved.add(name)
            self.lesson.state["gates"] = set(self.solved)
            self.audio.play("star")

    def draw(self, surf):
        gfx = self.gfx
        name, targets = self.GATES[self.gate]
        w1, w2, b = self.params()
        points = [(x1, x2, t) for (x1, x2), t in zip(self.INPUTS, targets)]
        draw_grid(surf, self.vp, gfx, step=0.5, major_every=2, axes=True)
        draw_zones(surf, self.vp, w1, w2, b, 34)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, CYAN, 1.0, self.time)
        draw_points(surf, self.vp, points, self.time, 1.0)
        x = TEXT_X
        for i, (gate, _) in enumerate(self.GATES):
            focused = i == self.gate
            rect = pygame.Rect(x, 112, 110, 34)
            panel(surf, rect, (20, 28, 48) if focused else (12, 16, 30), GOLD if focused else PANEL_EDGE, 8,
                  2 if focused else 1)
            gfx.text(surf, gfx.label, "{}  {}".format(i + 1, gate), rect.center, WHITE if focused else TEXT_DIM,
                     "center")
            if gate in self.solved:
                draw_star(surf, rect.right - 12, rect.top + 10, 6, GOLD)
            self.zone(rect, lambda i=i: self.select(i))
            x += 122
        y = self.para(surf, "A perceptron can be a logic gate. The four corners are the inputs 0 and 1; a bot means "
                            "the gate should output 1. Find w₁, w₂ and b that put every bot on the SAFE side.", 160)
        gfx.text(surf, gfx.label, "x₁   x₂   want   ŷ", (TEXT_X, y), TEXT_DIM)
        y += 20
        all_ok = True
        for (x1, x2), target in zip(self.INPUTS, targets):
            out = 1 if w1 * x1 + w2 * x2 + b > 0 else 0
            ok = out == target
            all_ok = all_ok and ok
            gfx.text(surf, gfx.body, "{}    {}    {}      {}".format(x1, x2, target, out), (TEXT_X + 4, y),
                     TEXT if ok else AMBER)
            gfx.text(surf, gfx.body, "✓" if ok else "✗", (TEXT_X + 210, y), GREEN if ok else RED)
            y += 22
        if name == "XOR":
            text = ("No luck? That's the point: the two 1s sit on opposite corners, and any straight line that puts "
                    "both on one side also catches a 0. A single perceptron cannot compute XOR.")
            if self.tried_xor > 4.0:
                self.para(surf, text, y + 4, VIOLET, gfx.small)
            else:
                self.para(surf, "Try to build XOR (exclusive or)...", y + 4, TEXT_DIM, gfx.small)
        elif all_ok:
            self.para(surf, "{} built:  w₁ = {}, w₂ = {}, b = {}".format(name, f2(w1), f2(w2), f2(b)), y + 4, GREEN)
        self.sliders.draw(surf, gfx, self.time)
        gfx.text(surf, gfx.small, "click a gate above, or press 1-4", (TEXT_X, 610), TEXT_FAINT)


class RulePage(Page):
    title = "The learning rule"

    def draw(self, surf):
        gfx = self.gfx
        y = self.para(surf, "Show the perceptron one labelled example. If it answers correctly, nothing happens. "
                            "If it's wrong, every weight moves a little:", 112)
        y = self.formula(surf, [("error = ", TEXT), ("y", C_Y), (" - ", TEXT), ("ŷ", C_Y),
                                ("      (+1, 0 or -1)", TEXT_DIM)], y)
        y = self.formula(surf, [("w₁ ← ", C_W), ("w₁", C_W), (" + ", TEXT), ("η", C_ETA), ("·error·", TEXT),
                                ("x₁", C_X)], y)
        y = self.formula(surf, [("w₂ ← ", C_W), ("w₂", C_W), (" + ", TEXT), ("η", C_ETA), ("·error·", TEXT),
                                ("x₂", C_X)], y)
        y = self.formula(surf, [("b  ← ", C_B), ("b", C_B), ("  + ", TEXT), ("η", C_ETA), ("·error", TEXT)], y)
        y = self.para(surf, "η (eta) is the learning rate: the size of each step. Missed a 1? The error is +1, so "
                            "the input is added and the laser swings toward that point. Fired wrongly on a 0? "
                            "The input is subtracted and the laser swings away.", y + 4)
        box = pygame.Rect(660, 128, 440, 470)
        panel(surf, box, (14, 18, 34), PANEL_EDGE, 12)
        gfx.text(surf, gfx.label, "WORKED EXAMPLE   η = 0.1", (box.left + 22, box.top + 18), AMBER)
        lines = (
            [("w = (0.20, -0.50),  b = 0.10", TEXT)],
            [("bot at x = (3, 2),  label ", TEXT), ("y = 1", C_Y)],
            [("z = 0.2·3 - 0.5·2 + 0.1 = ", TEXT), ("-0.30", C_Z)],
            [("ŷ = 0   →   error = 1 - 0 = ", TEXT), ("+1", GREEN)],
            [("w₁ ← 0.20 + 0.1·1·3 = ", TEXT), ("0.50", C_W)],
            [("w₂ ← -0.50 + 0.1·1·2 = ", TEXT), ("-0.30", C_W)],
            [("b  ← 0.10 + 0.1·1 = ", TEXT), ("0.20", C_B)],
            [("new z = 0.5·3 - 0.3·2 + 0.2 = ", TEXT), ("1.10", C_Z)],
            [("ŷ = 1   ✓  fixed in one step", GREEN)],
        )
        yy = box.top + 52
        for k, segments in enumerate(lines):
            if self.time > 0.35 * k:
                gfx.rich(surf, gfx.body, segments, (box.left + 22, yy))
            yy += 34
        self.para(surf, "One step doesn't always fix the point, but it always moves the score the right way.",
                  box.bottom - 70, TEXT_DIM, gfx.small, box.left + 22, box.width - 44)


class TrainerPage(Page):
    title = "Watch it learn"
    points = TRAIN_POINTS
    start = TRAIN_START

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.trainer = Trainer(self.points, 0.1, self.start)
        self.playing = False
        self.acc = 0.0
        self.sliders = SliderGroup([Slider("lr", "η  learning rate", 0.01, 1.0, 0.1, 0.01, C_ETA,
                                           lambda v: "{:.2f}".format(v))], TEXT_X, 448, TEXT_W - 20, 54,
                                   self.set_rate, self.app)
        self.shown = self.trainer.brain.params

    def set_rate(self, name, value):
        self.trainer.lr = value

    def toggle_play(self):
        self.playing = not self.playing
        self.audio.play("ui_select")

    def reset(self):
        self.trainer.reset()
        if self.sliders is not None:
            self.trainer.lr = self.sliders.values()["lr"]
        self.shown = self.trainer.brain.params
        self.playing = False
        self.audio.play("ui_back")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.step()
                return True
            if event.key == pygame.K_p:
                self.toggle_play()
                return True
            if event.key == pygame.K_r:
                self.reset()
                return True
        return super().handle_event(event)

    def draw_controls(self, surf, y, play_label="play"):
        self.key_buttons(surf, TEXT_X, y, (("SPACE", "step", self.step),
                                           ("P", "pause" if self.playing else play_label, self.toggle_play),
                                           ("R", "reset", self.reset)))

    def step(self):
        info = self.trainer.step()
        if info is None:
            self.audio.play("ui_back")
        elif info["changed"]:
            self.audio.play("snap")
        else:
            self.audio.play("tick")

    def update(self, dt):
        super().update(dt)
        if self.playing:
            self.acc += dt
            while self.acc >= 0.32:
                self.acc -= 0.32
                self.step()
                if self.trainer.converged:
                    self.playing = False
                    self.audio.play("win")
                    break
        target = self.trainer.brain.params
        self.shown = tuple(lerp(a, b, min(1.0, dt * 10.0)) for a, b in zip(self.shown, target))

    def draw_status(self, surf, y):
        gfx = self.gfx
        tr = self.trainer
        state = "CONVERGED: no mistakes in a full epoch" if tr.converged else "epoch {}, sample {} of {}".format(
            tr.epoch, tr.index + 1, len(tr.points))
        gfx.text(surf, gfx.label, state, (TEXT_X, y), GREEN if tr.converged else CYAN)
        y += 22
        gfx.text(surf, gfx.small, "updates so far: {}".format(tr.updates), (TEXT_X, y), TEXT_DIM)
        y += 26
        info = tr.last
        if info is None:
            gfx.text(surf, gfx.body, "SPACE (or the step button) runs one step; P plays.", (TEXT_X, y), TEXT)
            return
        x1, x2 = info["point"]
        old, new = info["old"], info["new"]
        name = "bot" if info["label"] == 1 else "drone"
        if not info["changed"]:
            gfx.rich(surf, gfx.body, [("{} at ({}, {}): ŷ = {}, correct. ".format(name, f1(x1), f1(x2), info["pred"]),
                                       TEXT), ("No change.", GREEN)], (TEXT_X, y))
            return
        error = info["label"] - info["pred"]
        gfx.rich(surf, gfx.body, [("{} at ({}, {}): ŷ = {}, wrong. error = ".format(name, f1(x1), f1(x2),
                                                                                  info["pred"]), TEXT),
                                  ("{:+d}".format(error), AMBER)], (TEXT_X, y))
        y += 24
        lr = "{:g}".format(tr.lr)
        for symbol, i, xv in (("w₁", 0, x1), ("w₂", 1, x2), ("b ", 2, None)):
            extra = "·" + f1(xv) if xv is not None else ""
            gfx.rich(surf, gfx.body, [(symbol + " ← ", C_B if i == 2 else C_W),
                                      ("{} + {}·({:+d}){} = ".format(f2(old[i]), lr, error, extra), TEXT),
                                      (f2(new[i]), WHITE)], (TEXT_X, y))
            y += 22

    def draw(self, surf):
        gfx = self.gfx
        tr = self.trainer
        draw_grid(surf, self.vp, gfx)
        w1, w2, b = self.shown
        draw_zones(surf, self.vp, w1, w2, b, 30)
        for k, old in enumerate(tr.history):
            ends = boundary_endpoints(*old)
            if ends:
                fade = 0.15 + 0.5 * (k + 1) / max(1, len(tr.history))
                pygame.draw.aaline(surf, scale_color(CYAN, fade * 0.6), self.vp.to_screen(*ends[0]),
                                   self.vp.to_screen(*ends[1]))
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, GREEN if tr.converged else CYAN, 1.0, self.time)
        draw_weight_arrow(surf, self.vp, gfx, w1, w2, b)
        draw_points(surf, self.vp, tr.points, self.time, 0.75, tr.current)
        y = self.para(surf, "The perceptron visits the examples in order, one per step. Each mistake nudges the "
                            "laser using the rule. It stops once it gets through a whole round (an epoch) without a "
                            "single mistake.", 112)
        self.draw_status(surf, y)
        self.sliders.draw(surf, gfx, self.time)
        self.draw_controls(surf, 540)
        gfx.text(surf, gfx.small, "faded lines: where the laser used to be", (TEXT_X, 574), TEXT_FAINT)


class VectorPage(Page):
    title = "Why it works: vectors"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT, (-2.5, 2.5, -2.5, 2.5))
        self.sliders = SliderGroup([Slider("lr", "η  learning rate", 0.0, 1.0, 0.5, 0.01, C_ETA,
                                           lambda v: "{:.2f}".format(v))], TEXT_X, 474, TEXT_W - 20, 54, None,
                                   self.app)

    def arrow(self, surf, a, e, color, width=3, label=None):
        thick_line(surf, color, a, e, width)
        dx, dy = e[0] - a[0], e[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        pygame.draw.polygon(surf, color, (e, (e[0] - ux * 12 - uy * 6, e[1] - uy * 12 + ux * 6),
                                          (e[0] - ux * 12 + uy * 6, e[1] - uy * 12 - ux * 6)))
        if label:
            self.gfx.text(surf, self.gfx.label, label, (e[0] + ux * 16, e[1] + uy * 16), color, "center")

    def draw(self, surf):
        gfx = self.gfx
        lr = self.sliders.values()["lr"]
        w = (1.0, -0.6)
        x = (0.6, 1.8)
        new = (w[0] + lr * x[0], w[1] + lr * x[1])
        draw_grid(surf, self.vp, gfx, step=0.5, major_every=2, axes=True, labels=False)
        for params, color in (((w[0], w[1], 0.0), scale_color(CYAN, 0.5)), ((new[0], new[1], 0.0), GREEN)):
            ends = boundary_endpoints(*params, self.vp.bounds)
            if ends:
                dashed_line(surf, color, self.vp.to_screen(*ends[0]), self.vp.to_screen(*ends[1]), 2, 9, 6)
        origin = self.vp.to_screen(0, 0)
        self.arrow(surf, origin, self.vp.to_screen(*w), CYAN, 3, "w")
        self.arrow(surf, origin, self.vp.to_screen(*x), WHITE, 3, "x")
        self.arrow(surf, self.vp.to_screen(*w), self.vp.to_screen(*new), C_ETA, 3, "η·x")
        self.arrow(surf, origin, self.vp.to_screen(*new), GREEN, 3, "new w")
        draw_bot(surf, *self.vp.to_screen(*x), self.time, 0.0, 0.7)
        z_old = w[0] * x[0] + w[1] * x[1]
        z_new = new[0] * x[0] + new[1] * x[1]
        angle_old = math.degrees(math.acos(z_old / (math.hypot(*w) * math.hypot(*x))))
        angle_new = math.degrees(math.acos(clamp(z_new / (math.hypot(*new) * math.hypot(*x)), -1, 1)))
        y = self.para(surf, "Here the bias is 0, so the boundary (dashed) passes through the origin, at right angles "
                            "to w. The bot x is on the wrong side: w·x < 0.", 112)
        y = self.para(surf, "The rule adds η·x to w. Adding x drags w toward x, the angle between them shrinks, and "
                            "w·x grows. Keep adding and x ends up on the SAFE side.", y)
        y = self.formula(surf, [("before:  w·x = ", TEXT), (f2(z_old), RED if z_old <= 0 else GREEN),
                                ("   angle {:.0f}°".format(angle_old), TEXT_DIM)], y + 4, gfx.body)
        self.formula(surf, [("after:   w·x = ", TEXT), (f2(z_new), GREEN if z_new > 0 else RED),
                            ("   angle {:.0f}°".format(angle_new), TEXT_DIM)], y - 4, gfx.body)
        self.sliders.draw(surf, gfx, self.time)
        self.para(surf, "Why the bias? Treat b as one more weight on an input that is always 1. Then the same "
                        "picture holds in three dimensions.", 552, TEXT_DIM, gfx.small)


class TheoremPage(TrainerPage):
    title = "The convergence theorem"
    start = (0.0, 0.0, 0.0)

    def __init__(self, lesson):
        super().__init__(lesson)
        self.radius, self.gamma, self.bound = mistake_bound(TRAIN_POINTS, TRUE_LINE)
        self.sliders = None

    def draw(self, surf):
        gfx = self.gfx
        tr = self.trainer
        draw_grid(surf, self.vp, gfx)
        w1, w2, b = self.shown
        draw_zones(surf, self.vp, w1, w2, b, 30)
        if any(abs(v) > 1e-9 for v in (w1, w2)):
            draw_laser(surf, gfx.fx, self.vp, w1, w2, b, GREEN if tr.converged else CYAN, 1.0, self.time)
        draw_points(surf, self.vp, tr.points, self.time, 0.75, tr.current)
        y = self.para(surf, "Frank Rosenblatt's perceptron comes with a guarantee, proved by Albert Novikoff in "
                            "1962: if some straight line separates the data, the learning rule makes only a "
                            "finite number of mistakes. After that, it classifies every example correctly.", 112)
        y = self.formula(surf, [("mistakes ≤ (R / γ)²", GOLD)], y + 2)
        y = self.para(surf, "R: the length of the biggest input, with the constant 1 for the bias added "
                            "as a third entry. γ (gamma): the margin of a separating line, measured in that same "
                            "3-D space. Starting from w = 0, b = 0:", y, TEXT_DIM, gfx.small)
        y = self.formula(surf, [("R = {:.2f},  γ = {:.2f}  →  at most {} mistakes".format(
            self.radius, self.gamma, int(self.bound)), WHITE)], y, gfx.body)
        color = GREEN if tr.converged else CYAN
        self.formula(surf, [("mistakes so far: ", TEXT), (str(tr.updates), color),
                            ("   CONVERGED" if tr.converged else "", color)], y - 4, gfx.body)
        self.draw_controls(surf, 506)
        self.para(surf, "A guarantee, not a prediction: the real count is usually far below the bound. A wider gap "
                        "between the classes (bigger γ) means a smaller bound.", 548, TEXT_DIM, gfx.small)


class NoisyPage(TrainerPage):
    title = "When it never stops"
    points = NOISY_POINTS

    def __init__(self, lesson):
        super().__init__(lesson)
        self.sliders = None
        self.epoch_log = []
        self.best = None

    def step(self):
        before = self.trainer.epoch
        super().step()
        tr = self.trainer
        errors = count_errors(*tr.brain.params, tr.points)
        if self.best is None or errors < self.best[0]:
            self.best = (errors, tr.brain.params)
        if tr.epoch != before:
            self.epoch_log.append(errors)

    def update(self, dt):
        if self.playing:
            self.acc += dt * 3.0
        super().update(dt)

    def draw(self, surf):
        gfx = self.gfx
        tr = self.trainer
        draw_grid(surf, self.vp, gfx)
        w1, w2, b = self.shown
        draw_zones(surf, self.vp, w1, w2, b, 30)
        draw_laser(surf, gfx.fx, self.vp, w1, w2, b, AMBER, 1.0, self.time)
        if self.best is not None:
            ends = boundary_endpoints(*self.best[1])
            if ends:
                dashed_line(surf, GOLD, self.vp.to_screen(*ends[0]), self.vp.to_screen(*ends[1]), 2, 8, 6)
        draw_points(surf, self.vp, tr.points, self.time, 0.75, tr.current)
        x, y = self.vp.to_screen(7.5, 2.5)
        gfx.text(surf, gfx.tiny, "faulty sensor", (x, y + 22), AMBER, "midtop")
        y = self.para(surf, "Add one mislabelled bot and no straight line can be perfect. There is always a point "
                            "on the wrong side, so the rule keeps finding mistakes and the laser never settles.", 112)
        y = self.para(surf, "A common fix is the pocket algorithm (Gallant, 1990): keep training, but keep the best "
                            "weights seen so far in your pocket. The gold dashed line is that pocket.", y)
        gfx.text(surf, gfx.label, "epoch {}   updates {}".format(tr.epoch, tr.updates), (TEXT_X, y + 4), AMBER)
        if self.best is not None:
            gfx.text(surf, gfx.small, "pocket: {} error{}".format(self.best[0], "" if self.best[0] == 1 else "s"),
                     (TEXT_X + 260, y + 5), GOLD)
        self.draw_controls(surf, y + 36, "play fast")
        self.para(surf, "Other fixes: models that measure how wrong they are, like logistic regression, or more "
                        "layers (lesson 8).", 548, TEXT_DIM, gfx.small)

    def reset(self):
        self.epoch_log = []
        self.best = None
        super().reset()


class RatePage(Page):
    title = "The learning rate"
    RATES = (0.01, 0.1, 1.0)

    def __init__(self, lesson):
        super().__init__(lesson)
        self.vp = Viewport(VIEW_RECT)
        self.zero = []
        self.random = []
        for lr in self.RATES:
            for start, table in (((0.0, 0.0, 0.0), self.zero), (TRAIN_START, self.random)):
                tr = Trainer(TRAIN_POINTS, lr, start)
                tr.run()
                table.append((lr, tr.updates, tr.brain.params))
        self.show = 1

    def select(self, index):
        self.show = index
        self.audio.play("ui_move")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.select(event.key - pygame.K_1)
            return True
        return super().handle_event(event)

    def draw(self, surf):
        gfx = self.gfx
        draw_grid(surf, self.vp, gfx)
        lr, updates, params = self.zero[self.show]
        draw_zones(surf, self.vp, *params, 30)
        draw_laser(surf, gfx.fx, self.vp, *params, CYAN, 1.0, self.time)
        draw_points(surf, self.vp, TRAIN_POINTS, self.time, 0.75)
        y = self.para(surf, "η sets how big each correction is. Here is a fun fact: if the weights and bias start "
                            "at zero, η doesn't change what the perceptron learns at all.", 112)
        y = self.para(surf, "Every update adds η·x, so every weight ends up η times bigger, and the sign of z, which "
                            "is all predict() looks at, never changes. Same mistakes, same line, bigger numbers:", y)
        gfx.text(surf, gfx.label, "η        start at 0             random start", (TEXT_X, y), TEXT_DIM)
        y += 22
        for i, lr in enumerate(self.RATES):
            zero = self.zero[i]
            rnd = self.random[i]
            color = GOLD if i == self.show else TEXT
            gfx.text(surf, gfx.body, "{:<6}   {:>2} mistakes   w₁ {:+.2f}".format("{:g}".format(lr), zero[1],
                                                                                    zero[2][0]),
                     (TEXT_X, y), color)
            gfx.text(surf, gfx.body, "{:>3} mistakes".format(rnd[1]), (TEXT_X + 380, y), color)
            rect = pygame.Rect(TEXT_X - 8, y - 3, 530, 24)
            if i == self.show:
                pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=6)
            self.zone(rect, lambda i=i: self.select(i))
            y += 24
        y = self.para(surf, "With a random start, η matters: a small η keeps the start's influence for longer, a "
                        "big η drowns it out quickly.", y + 8, TEXT_DIM)
        gfx.text(surf, gfx.small, "click a row (or press 1-3) to see the line learned from zero", (TEXT_X, y + 4),
                 TEXT_FAINT)


class FeatureScalePage(Page):
    title = "Big inputs, big jumps"

    def __init__(self, lesson):
        super().__init__(lesson)
        self.sliders = SliderGroup([Slider("s", "input size: the drone sits at s·(0.8, 0.7)", 0.5, 12.0, 10.0, 0.1,
                                           C_X, lambda v: f1(v))], TEXT_X, 430, TEXT_W - 20, 54, None, self.app)

    def draw(self, surf):
        gfx = self.gfx
        s = self.sliders.values()["s"]
        x1, x2 = 0.8 * s, 0.7 * s
        lr = 0.1
        dw1, dw2, db = -lr * x1, -lr * x2, -lr
        y = self.para(surf, "In the game, a wrong drone at (8, 7) makes the counter-attack change w₁ by 0.8 and w₂ "
                            "by 0.7, but b by only 0.1. Weights carry the input's size; the bias doesn't. That's why "
                            "the laser can leap right off the floor.", 112)
        y = self.formula(surf, [("Δw = η·error·x", C_W), ("     Δb = η·error", C_B)], y + 2, gfx.mid)
        y = self.formula(surf, [("drone at (", TEXT), (f1(x1), C_X), (", ", TEXT), (f1(x2), C_X),
                                ("), η = 0.1, error = -1", TEXT)], y, gfx.body)
        self.para(surf, "The usual fix is to rescale inputs to similar, small ranges (for example 0 to 1) before "
                        "training, so weights and bias move at comparable speeds.", 500, TEXT_DIM)
        self.sliders.draw(surf, gfx, self.time)
        box = pygame.Rect(660, 150, 440, 400)
        panel(surf, box, (14, 18, 34), PANEL_EDGE, 12)
        gfx.text(surf, gfx.label, "SIZE OF ONE UPDATE", (box.left + 24, box.top + 20), AMBER)
        base = box.top + 300
        for i, (name, value, color) in enumerate((("Δw₁", dw1, C_W), ("Δw₂", dw2, C_W), ("Δb", db, C_B))):
            x = box.left + 70 + i * 120
            height = min(240, abs(value) * 240)
            pygame.draw.rect(surf, color, (x, base - height, 60, height), border_radius=4)
            gfx.text(surf, gfx.mid, "{:+.2f}".format(value), (x + 30, base - height - 26), color, "center")
            gfx.text(surf, gfx.body, name, (x + 30, base + 20), TEXT, "center")
        pygame.draw.line(surf, TEXT_DIM, (box.left + 40, base), (box.right - 40, base))


class XorNetPage(Page):
    title = "Two layers beat XOR"
    HIDDEN = (("OR", (1.0, 1.0, -0.5)), ("NAND", (-1.0, -1.0, 1.5)))
    OUTPUT = (1.0, 1.0, -1.5)

    INPUT_POS = ((680, 196), (680, 356))
    HIDDEN_POS = ((830, 176), (830, 376))
    OUT_POS = (990, 276)

    def __init__(self, lesson):
        super().__init__(lesson)
        self.inputs = [1, 0]
        self.vp = Viewport(pygame.Rect(916, 448, 180, 180), (-0.5, 1.5, -0.5, 1.5))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_2):
            i = event.key - pygame.K_1
            self.inputs[i] = 1 - self.inputs[i]
            self.audio.play("tick")
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, (cx, cy) in enumerate(self.INPUT_POS):
                if math.hypot(event.pos[0] - cx, event.pos[1] - cy) < 34:
                    self.inputs[i] = 1 - self.inputs[i]
                    self.audio.play("tick")
                    return True
        return False

    @staticmethod
    def fire(params, a, b):
        return 1 if params[0] * a + params[1] * b + params[2] > 0 else 0

    def draw(self, surf):
        gfx = self.gfx
        x1, x2 = self.inputs
        hidden = [self.fire(p, x1, x2) for _, p in self.HIDDEN]
        out = self.fire(self.OUTPUT, hidden[0], hidden[1])
        y = self.para(surf, "One perceptron draws one line, and XOR needs two. So stack them: a hidden layer of two "
                            "perceptrons, then a third that combines their answers.", 112)
        rows = (("h₁ = OR(x₁, x₂)", "w = (1, 1), b = -0.5"), ("h₂ = NAND(x₁, x₂)", "w = (-1, -1), b = 1.5"),
                ("ŷ = AND(h₁, h₂)", "w = (1, 1), b = -1.5"))
        for name, params in rows:
            gfx.text(surf, gfx.body, name, (TEXT_X, y), WHITE)
            gfx.text(surf, gfx.small, params, (TEXT_X + 250, y + 2), TEXT_DIM)
            y += 26
        y += 10
        gfx.text(surf, gfx.label, "x₁  x₂   h₁  h₂   ŷ = XOR", (TEXT_X, y), TEXT_DIM)
        y += 22
        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1)):
            h = [self.fire(p, a, b) for _, p in self.HIDDEN]
            o = self.fire(self.OUTPUT, h[0], h[1])
            current = (a, b) == (x1, x2)
            if current:
                pygame.draw.rect(surf, (36, 44, 70), (TEXT_X - 8, y - 3, 300, 24), border_radius=5)
            gfx.text(surf, gfx.body, "{}   {}    {}   {}    {}".format(a, b, h[0], h[1], o), (TEXT_X + 4, y),
                     GOLD if current else TEXT)
            y += 26
        self.para(surf, "Training many layers needed a new idea: backpropagation (1986), which passes the error "
                        "backwards through the network.", y + 10, TEXT_DIM, gfx.small)
        gfx.text(surf, gfx.small, "1 / 2 or click an input to flip it", (TEXT_X, 610), TEXT_FAINT)
        # network diagram
        inputs = self.INPUT_POS
        hidden_pos = self.HIDDEN_POS
        out_pos = self.OUT_POS
        for i, hp in enumerate(hidden_pos):
            for j, ip in enumerate(inputs):
                weight = self.HIDDEN[i][1][j]
                thick_line(surf, scale_color(C_W if weight > 0 else AMBER, 0.6), ip, hp, 3)
            thick_line(surf, scale_color(C_W, 0.6), hp, out_pos, 3)
        for i, (cx, cy) in enumerate(inputs):
            value = self.inputs[i]
            pygame.draw.circle(surf, INK, (cx, cy), 32)
            pygame.draw.circle(surf, GOLD if value else TEXT_DIM, (cx, cy), 32, 3)
            gfx.text(surf, gfx.title, str(value), (cx, cy), WHITE, "center")
            gfx.text(surf, gfx.small, "x{}".format("₁₂"[i]), (cx, cy + 46), TEXT_DIM, "center")
        for i, (cx, cy) in enumerate(hidden_pos):
            value = hidden[i]
            if value:
                gfx.add_glow(surf, cx, cy, 50, CYAN, 0.5)
            pygame.draw.circle(surf, INK, (cx, cy), 36)
            pygame.draw.circle(surf, CYAN if value else TEXT_DIM, (cx, cy), 36, 3)
            gfx.text(surf, gfx.label, self.HIDDEN[i][0], (cx, cy - 10), TEXT, "center")
            gfx.text(surf, gfx.mid, str(value), (cx, cy + 12), WHITE, "center")
        if out:
            gfx.add_glow(surf, out_pos[0], out_pos[1], 60, GREEN, 0.6)
        pygame.draw.circle(surf, INK, out_pos, 40)
        pygame.draw.circle(surf, GREEN if out else RED, out_pos, 40, 3)
        gfx.text(surf, gfx.label, "AND", (out_pos[0], out_pos[1] - 12), TEXT, "center")
        gfx.text(surf, gfx.title, str(out), (out_pos[0], out_pos[1] + 12), GREEN if out else RED, "center")
        gfx.text(surf, gfx.mid, "XOR = {}".format(out), (out_pos[0] + 60, out_pos[1] - 12), GREEN if out else RED)
        # the two lines carve out the XOR region
        draw_grid(surf, self.vp, gfx, step=0.5, major_every=2, labels=False, axis_names=None)
        for _, params in self.HIDDEN:
            ends = boundary_endpoints(*params, self.vp.bounds)
            if ends:
                pygame.draw.line(surf, CYAN, self.vp.to_screen(*ends[0]), self.vp.to_screen(*ends[1]), 2)
        for a, b in ((0, 0), (0, 1), (1, 0), (1, 1)):
            px, py = self.vp.to_screen(a, b)
            if a != b:
                draw_bot(surf, px, py, self.time, 0.0, 0.6)
            else:
                draw_drone(surf, px, py, self.time, 0.0, 0.6)
        gfx.text(surf, gfx.tiny, "two lines: the XOR bots sit between them", (self.vp.rect.right,
                                                                              self.vp.rect.top - 16), TEXT_DIM,
                 "midright")


class TimelinePage(Page):
    title = "A short history"
    EVENTS = (
        ("1943", "McCulloch & Pitts", "Neurons modelled as threshold switches that can compute logic. No learning "
                                      "yet: someone has to set the weights."),
        ("1949", "Donald Hebb", "Proposes that a connection gets stronger when the neurons on both ends are active "
                                "together: an early idea of learning."),
        ("1958", "Frank Rosenblatt", "Publishes the perceptron: a neuron that learns its own weights from labelled "
                                     "examples with a simple error-correcting rule."),
        ("1960", "Mark I Perceptron", "A machine at Cornell Aeronautical Laboratory learns to recognise simple shapes "
                                      "from a 20 × 20 grid of photocells."),
        ("1962", "Albert Novikoff", "Proves the convergence theorem: on separable data the perceptron stops making "
                                    "mistakes after finitely many updates."),
        ("1969", "Minsky & Papert", "Their book Perceptrons maps what single-layer networks cannot do, like XOR. "
                                    "Interest in neural networks cools for years."),
        ("1986", "Backpropagation", "Rumelhart, Hinton and Williams show how to train multi-layer networks, which "
                                    "can learn XOR and much more."),
        ("2012", "Deep learning", "A deep network called AlexNet wins the ImageNet image-recognition contest by a "
                                  "wide margin, and the deep learning boom begins."),
    )

    def __init__(self, lesson):
        super().__init__(lesson)
        self.focus = 2

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.focus = clamp(self.focus + (1 if event.key == pygame.K_RIGHT else -1), 0, len(self.EVENTS) - 1)
            self.audio.play("ui_move")
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.EVENTS)):
                if math.hypot(event.pos[0] - self.node_x(i), event.pos[1] - 300) < 26:
                    self.focus = i
                    self.audio.play("ui_move")
                    return True
        return False

    def node_x(self, i):
        return 110 + i * 140

    def draw(self, surf):
        gfx = self.gfx
        self.para(surf, "From a 1940s thought experiment to the networks of today. Pick a year with ← →.", 112,
                  TEXT_DIM)
        pygame.draw.line(surf, PANEL_EDGE, (80, 300), (1120, 300), 3)
        for i, (year, who, _) in enumerate(self.EVENTS):
            x = self.node_x(i)
            focused = i == self.focus
            if focused:
                gfx.add_glow(surf, x, 300, 46, CYAN, 0.6)
            pygame.draw.circle(surf, INK, (x, 300), 16)
            pygame.draw.circle(surf, CYAN if focused else TEXT_DIM, (x, 300), 16, 3)
            gfx.text(surf, gfx.mid if focused else gfx.body, year, (x, 258), WHITE if focused else TEXT_DIM, "center")
            gfx.text(surf, gfx.tiny, who, (x, 334), CYAN if focused else TEXT_FAINT, "center")
        year, who, text = self.EVENTS[self.focus]
        box = pygame.Rect(150, 390, 900, 170)
        panel(surf, box, (14, 18, 34), CYAN, 12)
        gfx.text(surf, gfx.title, year, (box.left + 30, box.top + 22), GOLD)
        gfx.text(surf, gfx.mid, who, (box.left + 150, box.top + 28), WHITE)
        gfx.paragraph(surf, gfx.lead, text, box.left + 30, box.top + 80, box.width - 60, TEXT)
        self.para(surf, "Today's networks have billions of weights, yet every neuron still computes a weighted sum "
                        "plus a bias, just like the laser in your vault.", 590, TEXT_DIM, gfx.body, 150, 900)


class ModernPage(Page):
    title = "Where to next"

    def draw(self, surf):
        gfx = self.gfx
        y = self.para(surf, "The hard step is a problem for modern training: its slope is zero almost everywhere, so "
                            "gradient descent gets no signal about which way to move. Modern neurons swap it for "
                            "smooth functions:", 112)
        y = self.formula(surf, [("sigmoid:  σ(z) = 1 / (1 + exp(-z))", GREEN)], y)
        y = self.formula(surf, [("ReLU:     max(0, z)", AMBER)], y - 4)
        y = self.para(surf, "A sigmoid neuron trained by gradient descent is logistic regression: a perceptron that "
                            "also says how sure it is.", y)
        self.para(surf, "Support vector machines (Cortes & Vapnik, 1995) choose the separating line with the widest "
                        "possible margin, the same thing the margin bonus in this game rewards. Stack many neurons "
                        "in layers and you have a deep neural network.", y, TEXT_DIM)
        box = pygame.Rect(660, 140, 440, 380)
        panel(surf, box, (14, 18, 34), PANEL_EDGE, 12)
        left, right = box.left + 40, box.right - 30
        top, bottom = box.top + 96, box.bottom - 50
        zero = (left + right) / 2

        def sx(z):
            return lerp(left, right, (z + 6.0) / 12.0)

        def sy(v):
            return lerp(bottom, top, v / 2.0)
        pygame.draw.line(surf, TEXT_DIM, (left, bottom), (right, bottom))
        pygame.draw.line(surf, TEXT_DIM, (zero, top), (zero, bottom))
        step = [(sx(-6), sy(0)), (sx(0), sy(0)), (sx(0), sy(1)), (sx(6), sy(1))]
        pygame.draw.lines(surf, CYAN, False, step, 3)
        sig = [(sx(z / 10.0), sy(1.0 / (1.0 + math.exp(-z / 10.0)))) for z in range(-60, 61)]
        pygame.draw.lines(surf, GREEN, False, sig, 3)
        relu = [(sx(z / 10.0), sy(clamp(max(0.0, z / 10.0) / 3.0, 0.0, 2.0))) for z in range(-60, 61)]
        pygame.draw.lines(surf, AMBER, False, relu, 3)
        for text, color, y0 in (("step (perceptron)", CYAN, 0), ("sigmoid", GREEN, 22), ("ReLU (scaled)", AMBER, 44)):
            gfx.text(surf, gfx.small, text, (box.left + 24, box.top + 16 + y0), color)
        gfx.text(surf, gfx.tiny, "z", (right, bottom + 10), C_Z, "midtop")


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------
LESSONS = (
    ("neuron", "Meet the Perceptron", "inputs, weights, bias, fire!", (NeuronPage, FormulaPage, BiologyPage)),
    ("sum", "The Weighted Sum", "every spot gets a score z", (HeatmapPage, StepPage)),
    ("boundary", "The Decision Boundary", "slope, normal, distance, sign", (SlopePage, NormalPage, ScalePage)),
    ("gates", "Logic Gates", "AND, OR, NAND... and XOR?", (GatesPage,)),
    ("learning", "How It Learns", "the perceptron learning rule", (RulePage, TrainerPage, VectorPage)),
    ("convergence", "Convergence", "when learning stops, and when it can't", (TheoremPage, NoisyPage)),
    ("rate", "Learning Rate & Scale", "step sizes and big numbers", (RatePage, FeatureScalePage)),
    ("beyond", "Beyond One Neuron", "XOR, layers, history", (XorNetPage, TimelinePage, ModernPage)),
)
assert tuple(lesson[0] for lesson in LESSONS) == LESSON_IDS


class LessonScene(Scene):
    music = "academy"

    def __init__(self, app, index, page=0):
        super().__init__(app)
        self.index = index
        self.lesson_id, self.name, self.sub, self.page_types = LESSONS[index]
        self.state = {}
        self.page_index = page
        self.page = self.page_types[page](self)
        self.slide = 0.0
        self.hub = Button((525, 670, 150, 36), "ACADEMY", VIOLET)

    def go(self, step):
        target = self.page_index + step
        if target < 0:
            self.audio.play("ui_back")
            return
        if target >= len(self.page_types):
            new = self.profile.complete_lesson(self.lesson_id)
            self.audio.play("levelup" if new else "ui_select")
            self.app.go_academy(self.index)
            return
        self.page_index = target
        self.page = self.page_types[target](self)
        self.slide = 1.0 if step > 0 else -1.0
        self.audio.play("ui_select" if step > 0 else "ui_back")

    def nav_rects(self):
        return pygame.Rect(56, 670, 150, 36), pygame.Rect(994, 670, 150, 36)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go_academy(self.index)
                return True
            if event.key in CONFIRM:
                self.go(1)
                return True
            if event.key == pygame.K_BACKSPACE:
                self.go(-1)
                return True
        if self.hub.handle_event(event):
            self.app.go_academy(self.index)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            back, forward = self.nav_rects()
            if back.collidepoint(event.pos):
                self.go(-1)
                return True
            if forward.collidepoint(event.pos):
                self.go(1)
                return True
        return self.page.handle_event(event)

    def update(self, dt):
        super().update(dt)
        self.page.update(dt)
        self.slide *= math.exp(-14.0 * dt)

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        gfx.text(surf, gfx.label, "LESSON {} · {}".format(self.index + 1, self.name.upper()), (56, 22), CYAN)
        gfx.text(surf, gfx.title, self.page.title, (56, 42), WHITE)
        for k in range(len(self.page_types)):
            x = 1144 - (len(self.page_types) - 1 - k) * 22
            pygame.draw.circle(surf, CYAN if k == self.page_index else PANEL_EDGE, (x, 40), 6 if k == self.page_index
                               else 5)
        gfx.text(surf, gfx.tiny, "page {} of {}".format(self.page_index + 1, len(self.page_types)), (1150, 56),
                 TEXT_FAINT, "topright")
        pygame.draw.line(surf, PANEL_EDGE, (56, 92), (1144, 92))
        self.page.zones = []
        if abs(self.slide) > 0.01:
            layer = pygame.Surface((1200, 720), pygame.SRCALPHA, 32)
            layer.blit(gfx.backdrop, (0, 0))
            self.page.draw(layer)
            surf.blit(layer, (int(self.slide * 60), 96), pygame.Rect(0, 96, 1200, 562))
        else:
            self.page.draw(surf)
        back, forward = self.nav_rects()
        last = self.page_index == len(self.page_types) - 1
        for rect, text, enabled in ((back, "◀  BACK", self.page_index > 0),
                                    (forward, "FINISH  ✓" if last else "NEXT  ▶", True)):
            panel(surf, rect, (16, 22, 40), (GREEN if last and rect is forward else CYAN) if enabled else PANEL_EDGE,
                  8)
            gfx.text(surf, gfx.label, text, rect.center, WHITE if enabled else TEXT_FAINT, "center")
        self.hub.draw(surf, gfx)
        gfx.text(surf, gfx.tiny, "keys: ENTER next   BACKSPACE back   ESC Academy", (600, 656), TEXT_FAINT, "center")


class AcademyScene(Scene):
    music = "academy"

    def __init__(self, app, focus=0):
        super().__init__(app)
        self.focus = focus
        self.cards = []
        for i in range(len(LESSONS) + 1):
            col, row = i % 3, i // 3
            self.cards.append(pygame.Rect(60 + col * 366, 150 + row * 150, 346, 132))
        self.back = back_button()

    def open(self, i):
        self.audio.play("ui_select")
        if i == len(LESSONS):
            self.app.go_quiz()
        else:
            self.app.replace(LessonScene(self.app, i))

    def handle_event(self, event):
        if self.back.handle_event(event):
            self.app.go_menu("academy")
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go_menu("academy")
                return True
            moves = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1, pygame.K_UP: -3, pygame.K_DOWN: 3}
            if event.key in moves:
                self.focus = clamp(self.focus + moves[event.key], 0, len(self.cards) - 1)
                self.audio.play("ui_move")
                return True
            if event.key in CONFIRM + (pygame.K_SPACE,):
                self.open(self.focus)
                return True
        if event.type == pygame.MOUSEMOTION:
            for i, rect in enumerate(self.cards):
                if rect.collidepoint(event.pos) and i != self.focus:
                    self.focus = i
                    self.audio.play("ui_move")
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.cards):
                if rect.collidepoint(event.pos):
                    self.open(i)
                    return True
        return False

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        done = self.profile.lessons
        gfx.draw_banner(surf, "PERCEPTRON ACADEMY", (600, 56), WHITE, VIOLET, gfx.big)
        gfx.text(surf, gfx.body, "{} of {} lessons finished  ·  quiz best {}/10".format(
            len(done), len(LESSONS), self.profile.data["quiz_best"]), (600, 104), TEXT_DIM, "center")
        for i, rect in enumerate(self.cards):
            focused = i == self.focus
            quiz = i == len(LESSONS)
            accent = GOLD if quiz else VIOLET
            panel(surf, rect, (18, 22, 40) if focused else (12, 16, 30), accent if focused else PANEL_EDGE, 12,
                  2 if focused else 1)
            if focused:
                gfx.add_glow(surf, rect.left + 40, rect.top + 40, 50, accent, 0.4)
            if quiz:
                gfx.text(surf, gfx.label, "FINAL EXAM", (rect.left + 20, rect.top + 16), GOLD)
                gfx.text(surf, gfx.mid, "The Quiz", (rect.left + 20, rect.top + 40), WHITE)
                gfx.text(surf, gfx.small, "10 questions · new numbers every time", (rect.left + 20, rect.top + 74),
                         TEXT_DIM)
                best = self.profile.data["quiz_best"]
                for k in range(3):
                    draw_star(surf, rect.right - 70 + k * 22, rect.bottom - 22, 8,
                              GOLD if best >= (5, 8, 10)[k] else TEXT_FAINT, best >= (5, 8, 10)[k])
                continue
            lesson_id, name, sub, pages = LESSONS[i]
            gfx.text(surf, gfx.label, "LESSON {}".format(i + 1), (rect.left + 20, rect.top + 16), accent)
            gfx.text(surf, gfx.mid, name, (rect.left + 20, rect.top + 40), WHITE)
            gfx.text(surf, gfx.small, sub, (rect.left + 20, rect.top + 74), TEXT_DIM)
            gfx.text(surf, gfx.tiny, "{} page{}".format(len(pages), "" if len(pages) == 1 else "s"),
                     (rect.left + 20, rect.bottom - 26), TEXT_FAINT)
            if lesson_id in done:
                gfx.text(surf, gfx.label, "✓ DONE", (rect.right - 20, rect.bottom - 28), GREEN, "topright")
        draw_nyx(surf, 96, 640, 22, self.time, talking=False, color=VIOLET)
        gfx.text(surf, gfx.small, "Each lesson is hands-on: drag sliders, step the learning rule, break XOR. "
                                  "Finished lessons earn XP and a violet laser.", (134, 632), TEXT_DIM)
        gfx.text(surf, gfx.tiny, "arrows choose  ·  ENTER open  ·  ESC menu", (134, 654), TEXT_FAINT)
        self.back.draw(surf, gfx)


# ---------------------------------------------------------------------------
# The quiz
# ---------------------------------------------------------------------------
BANK = (
    ("When does a perceptron output 1?",
     ("When w₁x₁ + w₂x₂ + b > 0", "When w₁x₁ + w₂x₂ + b < 0", "When x₁ > x₂", "When b > 0"),
     "It fires when the weighted sum z is above zero."),
    ("Which parameter slides the boundary without turning it?",
     ("The bias b", "w₁", "w₂", "The learning rate η"),
     "Changing b moves the line parallel to itself."),
    ("The weight vector w = (w₁, w₂) is ... the boundary.",
     ("perpendicular to", "parallel to", "at 45° to", "unrelated to"),
     "w is the line's normal, and it points into the side where the output is 1."),
    ("You multiply w₁, w₂ and b by -1. What happens?",
     ("Same line, SAFE and ALARM swap", "The line turns 90°", "Nothing at all", "The line jumps to the far corner"),
     "z = 0 on the same points, but every other z changes sign."),
    ("You multiply w₁, w₂ and b by 3. What happens?",
     ("Nothing changes", "The line moves 3 times further", "The line rotates", "Every output flips"),
     "z triples, but its sign doesn't change, so every prediction stays the same."),
    ("The true label is 1 and the perceptron predicted 0. The error y - ŷ is...",
     ("+1", "-1", "0", "2"),
     "1 - 0 = +1, so the weights move toward the input."),
    ("The perceptron wrongly fires (ŷ = 1) on a drone x with label 0. How do the weights change?",
     ("w ← w - η·x", "w ← w + η·x", "w ← -w", "They don't change"),
     "The error is -1, so it subtracts η·x and the line tilts away from that point."),
    ("How much do the weights change on a correctly classified example?",
     ("Not at all", "By η·x", "By -η·x", "By half of η·x"),
     "The rule only updates on mistakes: the error y - ŷ is 0."),
    ("What is the slope of the line w₁x₁ + w₂x₂ + b = 0 (with w₂ ≠ 0)?",
     ("-w₁ / w₂", "w₁ / w₂", "-w₂ / w₁", "-b / w₂"),
     "Solve for x₂: x₂ = -(w₁/w₂)·x₁ - b/w₂."),
    ("Which gate can a single perceptron NOT compute?",
     ("XOR", "AND", "OR", "NAND"),
     "XOR's 1s sit on opposite corners, and no straight line separates them from the 0s."),
    ("Which weights and bias make a perceptron compute AND on 0/1 inputs?",
     ("w = (1, 1), b = -1.5", "w = (1, 1), b = -0.5", "w = (-1, -1), b = 1.5", "w = (1, -1), b = 0"),
     "Only (1, 1) gives 1 + 1 - 1.5 > 0. With b = -0.5 it would be OR; (-1, -1) with b = 1.5 is NAND."),
    ("On linearly separable data, the perceptron convergence theorem promises that...",
     ("it stops making mistakes after finitely many updates", "it finds the widest possible margin",
      "it needs exactly one epoch", "it never makes a mistake"),
     "Novikoff (1962): at most (R/γ)² mistakes, after which every example is classified correctly."),
    ("On data that is NOT linearly separable, the plain perceptron rule...",
     ("keeps updating forever", "converges anyway", "stops after one epoch", "deletes the outliers"),
     "Some point is always wrong, so it never settles. The pocket algorithm keeps the best weights seen."),
    ("Who introduced the perceptron?",
     ("Frank Rosenblatt", "Alan Turing", "Geoffrey Hinton", "Marvin Minsky"),
     "Rosenblatt published it in 1958, and the Mark I Perceptron machine followed."),
    ("What is the distance from a point x to the boundary?",
     ("|w·x + b| / |w|", "w·x + b", "|w| / |w·x + b|", "|b| / |w|"),
     "Divide the score by the length of w. (|b| / |w| is the distance from the origin.)"),
    ("In this game, dragging the whole laser sideways without turning it changes...",
     ("only b", "only w₁", "w₁ and w₂", "the learning rate"),
     "A parallel shift keeps the direction of w and changes the bias."),
    ("If w and b start at zero, doubling the learning rate η...",
     ("makes exactly the same mistakes", "halves the number of mistakes", "doubles the number of mistakes",
      "stops it converging"),
     "Every weight just doubles, and the sign of z, all that predict() uses, is unchanged."),
    ("The mistake bound (R/γ)² gets smaller when...",
     ("the margin γ grows", "the inputs get bigger", "the learning rate shrinks", "you add more points"),
     "A wide gap between the classes makes the problem easier."),
    ("A point lies exactly on the boundary (z = 0). This game's perceptron outputs...",
     ("0", "1", "0.5", "a random choice"),
     "predict() returns 1 only when z > 0, so z = 0 gives 0."),
    ("What does it take to compute XOR with perceptrons?",
     ("Two layers: a hidden layer, then an output", "A bigger learning rate", "More training epochs",
      "A larger bias"),
     "For example OR and NAND in a hidden layer, then AND on their outputs."),
    ("With w₁ = w₂ = 0, what decides the output?",
     ("Only the bias b", "Only x₁", "Nothing: it's always 1", "The learning rate"),
     "z = b for every input, so every point gets the same answer."),
    ("Why do modern networks use sigmoid or ReLU instead of the hard step?",
     ("Their slopes let gradient descent learn", "They are faster to compute", "The step can't output 1",
      "They don't need a bias"),
     "The step's slope is zero almost everywhere, so gradients can't flow through it."),
    ("Large inputs (like 8 and 7) make one learning step...",
     ("move the weights much more than the bias", "move only the bias", "do nothing", "move everything equally"),
     "Δw = η·error·x scales with the input; Δb = η·error does not. Rescaling inputs balances it."),
    ("Which 1969 book showed the limits of single-layer perceptrons?",
     ("Perceptrons, by Minsky & Papert", "The Organization of Behavior, by Hebb",
      "Computing Machinery and Intelligence, by Turing", "Deep Learning, by Goodfellow et al."),
     "Minsky and Papert analysed what single-layer networks cannot compute, XOR among them."),
)


def _four(correct, distractors, fmt):
    """The correct answer first, then the first distinct distractors, always 4 options in all.
    Small offsets of the answer back up the distractors when some coincide (e.g. w₁ = w₂)."""
    options = [fmt(correct)]
    backups = [correct + d for d in (1.0, -1.0, 0.5, -0.5, 2.0, -2.0, 3.0, -3.0)]
    for value in list(distractors) + backups:
        text = fmt(value)
        if text not in options:
            options.append(text)
        if len(options) == 4:
            break
    return options


def generated_question(rng, kind):
    """A numeric question with fresh numbers: (prompt, options, explanation), correct answer first."""
    if kind == "classify":
        w1, w2 = rng.choice((-1, -0.5, 0.5, 1, 2)), rng.choice((-1, -0.5, 0.5, 1, 2))
        b = rng.choice((-4, -3, -2, -1, 1, 2, 3))
        x1, x2 = rng.randint(0, 4), rng.randint(0, 4)
        z = w1 * x1 + w2 * x2 + b
        if abs(z) < 1e-9:
            x1 += 1
            z = w1 * x1 + w2 * x2 + b
        prompt = "w₁ = {:g}, w₂ = {:g}, b = {:g}. What does the perceptron say about x = ({}, {})?".format(
            w1, w2, b, x1, x2)
        options = _four(z, (w1 * x1 + w2 * x2 - b, w2 * x1 + w1 * x2 + b, -z),
                        lambda v: "z = {:g}, so ŷ = {}".format(round(v, 6) + 0.0, 1 if v > 0 else 0))
        return prompt, options, "z = {:g}·{} + {:g}·{} + {:g} = {:g}.".format(w1, x1, w2, x2, b, z)
    if kind == "update":
        w1 = rng.choice((0.2, 0.5, -0.3, 0.8))
        lr = rng.choice((0.1, 0.5))
        x1 = rng.randint(1, 5)
        label = rng.choice((0, 1))
        error = 1 if label == 1 else -1
        new = w1 + lr * error * x1
        prompt = ("w₁ = {:g}, η = {:g}. The perceptron gets a {} at x₁ = {} wrong (label {}). What is the new "
                  "w₁?").format(w1, lr, "bot" if label else "drone", x1, label)
        options = _four(new, (w1 - lr * error * x1, w1 + error * x1, w1, w1 + lr * error),
                        lambda v: "{:.2f}".format(round(v, 6) + 0.0))
        return prompt, options, "w₁ ← {:g} + {:g}·({:+d})·{} = {:.2f}.".format(w1, lr, error, x1, new)
    if kind == "slope":
        w1, w2 = rng.choice((1, 2, 3, -1, -2)), rng.choice((1, 2, 4, -2))
        prompt = "The boundary is {:g}·x₁ {} {:g}·x₂ + 1 = 0. What is its slope?".format(w1, "-" if w2 < 0 else "+",
                                                                                         abs(w2))
        options = _four(-w1 / w2, (w1 / w2, -w2 / w1, w2 / w1, -1 / w2), lambda v: "{:g}".format(round(v, 6) + 0.0))
        return prompt, options, "Slope = -w₁ / w₂ = -({:g}) / {:g} = {:g}.".format(w1, w2, -w1 / w2)
    w1, w2 = rng.choice(((3, 4), (0.6, 0.8), (4, 3), (6, 8)))
    norm = math.hypot(w1, w2)
    b = rng.choice((-5, -10, 5, 10)) * norm / 5
    x1, x2 = rng.randint(0, 3), rng.randint(0, 3)
    z = w1 * x1 + w2 * x2 + b
    distance = abs(z) / norm
    prompt = "w = ({:g}, {:g}), b = {:g}. How far is x = ({}, {}) from the boundary?".format(w1, w2, b, x1, x2)
    options = _four(distance, (abs(z), abs(z) / norm ** 2, abs(b) / norm), lambda v: "{:.2f}".format(abs(v)))
    return prompt, options, "|z| / |w| = {:.2f} / {:g} = {:.2f}.".format(abs(z), norm, distance)


class QuizScene(Scene):
    music = "academy"

    def __init__(self, app, seed=None):
        super().__init__(app)
        rng = random.Random(seed)
        picks = rng.sample(BANK, 6)
        questions = [(q, list(opts), why) for q, opts, why in picks]
        for kind in ("classify", "update", "slope", "distance"):
            prompt, options, why = generated_question(rng, kind)
            questions.append((prompt, options, why))
        rng.shuffle(questions)
        self.questions = []
        for prompt, options, why in questions:
            correct = options[0]
            options = options[:4]
            rng.shuffle(options)
            self.questions.append((prompt, options, options.index(correct), why))
        self.index = 0
        self.choice = 0
        self.answered = None
        self.correct = 0
        self.finished = False
        self.result_new = False
        self.back = back_button()
        self.again = Button((380, 540, 200, 44), "NEW QUIZ", GREEN)
        self.to_hub = Button((620, 540, 200, 44), "ACADEMY", VIOLET)

    def option_rects(self):
        return [pygame.Rect(150, 300 + i * 70, 900, 56) for i in range(4)]

    def answer(self, i):
        if self.answered is not None:
            return
        self.answered = i
        if i == self.questions[self.index][2]:
            self.correct += 1
            self.audio.play_ok(self.correct)
        else:
            self.audio.play("bad")

    def advance(self):
        if self.answered is None:
            return
        self.index += 1
        self.answered = None
        self.choice = 0
        if self.index >= len(self.questions):
            self.finished = True
            self.result_new = self.profile.record_quiz(self.correct, len(self.questions))
            self.audio.play("win" if self.correct >= 8 else "wave_clear")

    def handle_event(self, event):
        if self.back.handle_event(event) or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            self.app.go_academy(len(LESSONS))
            return True
        if self.finished:
            if self.again.handle_event(event) or (event.type == pygame.KEYDOWN and event.key in CONFIRM):
                self.app.go_quiz()
            elif self.to_hub.handle_event(event) or (event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE):
                self.app.go_academy(len(LESSONS))
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.choice = event.key - pygame.K_1
                self.answer(self.choice)
            elif event.key in (pygame.K_UP, pygame.K_DOWN) and self.answered is None:
                self.choice = (self.choice + (1 if event.key == pygame.K_DOWN else -1)) % 4
                self.audio.play("ui_move")
            elif event.key in CONFIRM + (pygame.K_SPACE,):
                if self.answered is None:
                    self.answer(self.choice)
                else:
                    self.advance()
            return True
        if event.type == pygame.MOUSEMOTION and self.answered is None:
            for i, rect in enumerate(self.option_rects()):
                if rect.collidepoint(event.pos):
                    self.choice = i
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.answered is not None:
                self.advance()
                return True
            for i, rect in enumerate(self.option_rects()):
                if rect.collidepoint(event.pos):
                    self.choice = i
                    self.answer(i)
                    return True
        return False

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        if self.finished:
            total = len(self.questions)
            gfx.draw_banner(surf, "{} / {}".format(self.correct, total), (600, 230), WHITE,
                            GOLD if self.correct == total else VIOLET, gfx.huge)
            verdict = ("CERTIFIED HYPERPLANE HACKER" if self.correct == total else
                       "Sharp work" if self.correct >= 8 else "Good start: revisit a lesson and try again")
            gfx.text(surf, gfx.mid, verdict, (600, 320), GOLD if self.correct == total else TEXT, "center")
            gfx.text(surf, gfx.body, "+{} XP".format(10 * self.correct), (600, 360), GOLD, "center")
            if self.result_new:
                gfx.text(surf, gfx.body, "New best score", (600, 390), GREEN, "center")
            for k in range(3):
                earned = self.correct >= (5, 8, 10)[k]
                draw_star(surf, 600 + (k - 1) * 70, 460, 26, GOLD if earned else (60, 66, 84), earned, 3)
            self.again.draw(surf, gfx)
            self.to_hub.draw(surf, gfx)
            gfx.text(surf, gfx.small, "keys: ENTER new quiz   BACKSPACE Academy", (600, 606), TEXT_FAINT, "center")
            self.back.draw(surf, gfx)
            return
        prompt, options, answer, why = self.questions[self.index]
        gfx.text(surf, gfx.label, "QUESTION {} OF {}".format(self.index + 1, len(self.questions)), (150, 70), VIOLET)
        gfx.text(surf, gfx.label, "SCORE {}".format(self.correct), (1050, 70), GOLD, "topright")
        bar = pygame.Rect(150, 92, 900, 4)
        pygame.draw.rect(surf, PANEL_EDGE, bar)
        pygame.draw.rect(surf, VIOLET, (bar.left, bar.top, bar.width * self.index // len(self.questions), 4))
        gfx.paragraph(surf, gfx.title, prompt, 150, 130, 900, WHITE, gap=8)
        for i, rect in enumerate(self.option_rects()):
            focused = i == self.choice
            fill, edge = (14, 18, 34), PANEL_EDGE
            if self.answered is not None:
                if i == answer:
                    fill, edge = (16, 48, 34), GREEN
                elif i == self.answered:
                    fill, edge = (56, 18, 26), RED
            elif focused:
                fill, edge = (24, 30, 54), CYAN
            panel(surf, rect, fill, edge, 10, 2 if focused or self.answered is not None else 1)
            gfx.keycap(surf, rect.left + 18, rect.centery - 10, str(i + 1))
            gfx.text(surf, gfx.lead, options[i], (rect.left + 60, rect.centery), WHITE, "midleft")
        if self.answered is not None:
            ok = self.answered == answer
            gfx.text(surf, gfx.mid, "CORRECT!" if ok else "NOT QUITE", (150, 588), GREEN if ok else RED)
            gfx.paragraph(surf, gfx.body, why, 330, 590, 720, TEXT)
            gfx.text(surf, gfx.small, "ENTER or click to continue", (1050, 680), TEXT_DIM, "topright")
        else:
            gfx.text(surf, gfx.small, "click an answer, or 1-4", (1050, 680), TEXT_FAINT, "topright")
        self.back.draw(surf, gfx)
