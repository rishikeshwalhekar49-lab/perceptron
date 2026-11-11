"""Hyperplane Heist: menus, sliders, dialogue and the animated backdrop shared by every screen."""
import math
import random

import pygame

from .core import clamp, inv_lerp, lerp
from .gfx import (AMBER, BLACK, CYAN, GREEN, INK, PANEL_EDGE, PANEL_FILL, RED, SCREEN_H, SCREEN_W, TEXT, TEXT_DIM,
                  TEXT_FAINT, WHITE, beam, draw_lock, draw_nyx, mix, scale_color)

CONTROLS_HELP = (
    ("← →", "change w₁: tilts the laser"),
    ("↓ ↑", "change w₂: tilts the laser"),
    ("W / S, SPACE", "change the bias b: slides it (SHIFT+SPACE lowers b)"),
    ("Q / E", "turn the laser"),
    ("F, right-click", "flip: same line, SAFE and ALARM swap"),
    ("Mouse", "drag an end to aim, drag the beam to slide, drag the floor to draw"),
    ("Wheel", "turn the laser"),
    ("ENTER", "lock in / scan now"),
    ("X", "declare: no straight line can split this vault"),
    ("T", "Auto-Trainer: one learning step (Endless perk)"),
    ("M", "sound on / off"),
    ("ESC", "pause"),
)


class Attract:
    """Units drifting behind a wandering hyperplane that reclassifies them as it sweeps past."""

    def __init__(self, count=30, seed=None):
        rnd = random.Random(seed)
        self.units = [[rnd.uniform(40, SCREEN_W - 40), rnd.uniform(40, SCREEN_H - 40), rnd.uniform(-26, 26),
                       rnd.uniform(-26, 26), False, 0.0] for _ in range(count)]
        self.time = rnd.uniform(0, 30)

    def plane(self):
        t = self.time
        angle = 0.9 + t * 0.22
        return (SCREEN_W / 2 + 190 * math.sin(t * 0.37), SCREEN_H / 2 + 70 * math.sin(t * 0.29 + 1.0),
                math.cos(angle), math.sin(angle))

    def update(self, dt):
        self.time += dt
        px, py, nx, ny = self.plane()
        for unit in self.units:
            unit[0] += unit[2] * dt
            unit[1] += unit[3] * dt
            if unit[0] < 12 or unit[0] > SCREEN_W - 12:
                unit[2] = -unit[2]
                unit[0] = clamp(unit[0], 12, SCREEN_W - 12)
            if unit[1] < 12 or unit[1] > SCREEN_H - 12:
                unit[3] = -unit[3]
                unit[1] = clamp(unit[1], 12, SCREEN_H - 12)
            safe = (unit[0] - px) * nx + (unit[1] - py) * ny > 0
            if safe != unit[4]:
                unit[4] = safe
                unit[5] = 1.0
            unit[5] = max(0.0, unit[5] - 2.5 * dt)

    def draw(self, surf, gfx, color=CYAN, power=0.55):
        surf.blit(gfx.backdrop, (0, 0))
        px, py, nx, ny = self.plane()
        gfx.fx.fill(BLACK)
        beam(gfx.fx, (px - ny * 1100, py + nx * 1100), (px + ny * 1100, py - nx * 1100), color, power)
        surf.blit(gfx.fx, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        for x, y, _, _, safe, flash in self.units:
            if safe:
                pygame.draw.circle(surf, mix(scale_color(GREEN, 0.55), WHITE, flash), (int(x), int(y)), 7)
            else:
                pygame.draw.polygon(surf, mix(scale_color(RED, 0.55), WHITE, flash),
                                    ((x, y - 9), (x + 8, y + 6), (x - 8, y + 6)))


class MenuItem:
    def __init__(self, label, action, sub="", enabled=True, color=CYAN, locked_text=""):
        self.label = label
        self.action = action
        self.sub = sub
        self.enabled = enabled
        self.color = color
        self.locked_text = locked_text
        self.rect = pygame.Rect(0, 0, 0, 0)


class Menu:
    """A column (or row) of buttons, driven by arrow keys, ENTER and the mouse.

    handle_event() returns the chosen item's action, or None."""

    def __init__(self, app, items, x, y, width, height=52, gap=10, horizontal=False):
        self.app = app
        self.items = items
        self.horizontal = horizontal
        self.focus = 0
        self.flash = 0.0
        for i, item in enumerate(items):
            if horizontal:
                item.rect = pygame.Rect(x + i * (width + gap), y, width, height)
            else:
                item.rect = pygame.Rect(x, y + i * (height + gap), width, height)

    @property
    def current(self):
        return self.items[self.focus]

    def move(self, step):
        self.focus = (self.focus + step) % len(self.items)
        self.app.audio.play("ui_move")

    def activate(self):
        item = self.current
        if not item.enabled:
            self.app.audio.play("ui_back")
            return None
        self.flash = 0.25
        self.app.audio.play("ui_select")
        return item.action

    def handle_event(self, event):
        back, forward = (pygame.K_LEFT, pygame.K_RIGHT) if self.horizontal else (pygame.K_UP, pygame.K_DOWN)
        if event.type == pygame.KEYDOWN:
            if event.key == back:
                self.move(-1)
            elif event.key == forward:
                self.move(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.activate()
        elif event.type == pygame.MOUSEMOTION:
            for i, item in enumerate(self.items):
                if item.rect.collidepoint(event.pos) and i != self.focus:
                    self.focus = i
                    self.app.audio.play("ui_move")
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, item in enumerate(self.items):
                if item.rect.collidepoint(event.pos):
                    self.focus = i
                    return self.activate()
        return None

    def update(self, dt):
        self.flash = max(0.0, self.flash - dt)

    def draw(self, surf, gfx, time):
        for i, item in enumerate(self.items):
            focused = i == self.focus
            rect = item.rect
            accent = item.color if item.enabled else TEXT_FAINT
            if focused:
                pulse = 0.5 + 0.5 * math.sin(time * 5.0)
                fill = mix(PANEL_FILL, accent, 0.16 + 0.05 * pulse + (0.25 if self.flash > 0 else 0))
                pygame.draw.rect(surf, fill, rect, border_radius=9)
                pygame.draw.rect(surf, accent, rect, 2, border_radius=9)
                bar = pygame.Rect(rect.left + 6, rect.top + 10, 4, rect.height - 20)
                pygame.draw.rect(surf, accent, bar, border_radius=2)
            else:
                pygame.draw.rect(surf, PANEL_FILL, rect, border_radius=9)
                pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=9)
            ink = TEXT if item.enabled else TEXT_FAINT
            if focused and item.enabled:
                ink = WHITE
            left = rect.left + 22
            if not item.enabled:
                draw_lock(surf, left + 6, rect.centery - 6, 12, TEXT_FAINT)
                left += 22
            if item.sub and rect.height >= 46:
                gfx.text(surf, gfx.mid, item.label, (left, rect.top + 8), ink)
                sub = item.sub if item.enabled else (item.locked_text or item.sub)
                gfx.text(surf, gfx.small, sub, (left, rect.top + 33), TEXT_DIM if item.enabled else TEXT_FAINT)
            else:
                gfx.text(surf, gfx.mid, item.label, (left, rect.centery), ink, "midleft")


class Slider:
    def __init__(self, name, label, lo, hi, value, step=0.01, color=CYAN, fmt=None):
        self.name = name
        self.label = label
        self.lo = lo
        self.hi = hi
        self.step = step
        self.color = color
        self.fmt = fmt or (lambda v: "{:+.2f}".format(round(v, 2) + 0.0))
        self.value = 0.0
        self.set(value)
        self.rect = pygame.Rect(0, 0, 0, 0)         # the track; set by SliderGroup
        self.enabled = True

    def set(self, value):
        value = clamp(value, self.lo, self.hi)
        if self.step:
            value = round(round(value / self.step) * self.step, 6) + 0.0
        self.value = value

    def value_at(self, px):
        return lerp(self.lo, self.hi, clamp(inv_lerp(self.rect.left, self.rect.right, px), 0.0, 1.0))

    def knob_x(self):
        return lerp(self.rect.left, self.rect.right, inv_lerp(self.lo, self.hi, self.value))

    def draw(self, surf, gfx, focused, time):
        color = self.color if self.enabled else TEXT_FAINT
        label_color = WHITE if focused else TEXT
        gfx.text(surf, gfx.label, self.label, (self.rect.left, self.rect.top - 20), label_color)
        gfx.text(surf, gfx.mid, self.fmt(self.value), (self.rect.right, self.rect.top - 24),
                 color if self.enabled else TEXT_FAINT, "topright")
        pygame.draw.rect(surf, (30, 41, 66), self.rect, border_radius=3)
        zero = None
        if self.lo < 0 < self.hi:
            zero = lerp(self.rect.left, self.rect.right, inv_lerp(self.lo, self.hi, 0.0))
            pygame.draw.line(surf, TEXT_DIM, (zero, self.rect.top - 3), (zero, self.rect.bottom + 2))
        x = self.knob_x()
        start = zero if zero is not None else self.rect.left
        fill = pygame.Rect(min(start, x), self.rect.top, abs(x - start), self.rect.height)
        pygame.draw.rect(surf, scale_color(color, 0.8), fill, border_radius=3)
        r = 9 if focused else 7
        pygame.draw.circle(surf, INK, (x, self.rect.centery), r + 2)
        pygame.draw.circle(surf, color, (x, self.rect.centery), r)
        if focused:
            pulse = 0.5 + 0.5 * math.sin(time * 6.0)
            pygame.draw.circle(surf, mix(color, WHITE, 0.5), (x, self.rect.centery), r + 4 + 2 * pulse, 1)


class SliderGroup:
    """Sliders with keyboard focus (UP / DOWN or TAB) and LEFT / RIGHT to adjust
    (hold to sweep).  The mouse can drag any track."""

    def __init__(self, sliders, x, y, width, row_h=52, on_change=None, app=None):
        self.sliders = sliders
        self.focus = 0
        self.on_change = on_change
        self.app = app
        self.drag = None
        self.held = {pygame.K_LEFT: 0.0, pygame.K_RIGHT: 0.0}
        self.down = set()
        self.carry = 0.0
        for i, slider in enumerate(sliders):
            slider.rect = pygame.Rect(x, y + i * row_h + 24, width, 6)

    def by_name(self, name):
        for slider in self.sliders:
            if slider.name == name:
                return slider
        return None

    def values(self):
        return {s.name: s.value for s in self.sliders}

    def _changed(self, slider):
        if self.on_change:
            self.on_change(slider.name, slider.value)

    def _nudge(self, slider, steps):
        if not slider.enabled:
            return
        before = slider.value
        slider.set(slider.value + steps * slider.step)
        if slider.value != before:
            self._changed(slider)
            if self.app:
                self.app.audio.play("tick")

    def handle_event(self, event):
        if not self.sliders:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_TAB):
                step = -1 if event.key == pygame.K_UP else 1
                if event.key == pygame.K_TAB and event.mod & pygame.KMOD_SHIFT:
                    step = -1
                self.focus = (self.focus + step) % len(self.sliders)
                if self.app:
                    self.app.audio.play("ui_move")
                return True
            if event.key in self.held:
                self.down.add(event.key)
                self.held[event.key] = 0.0
                self.carry = 0.0
                self._nudge(self.sliders[self.focus], -1 if event.key == pygame.K_LEFT else 1)
                return True
        elif event.type == pygame.KEYUP:
            if event.key in self.held:
                self.down.discard(event.key)
                return True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, slider in enumerate(self.sliders):
                if slider.enabled and slider.rect.inflate(16, 26).collidepoint(event.pos):
                    self.focus = i
                    self.drag = slider
                    slider.set(slider.value_at(event.pos[0]))
                    self._changed(slider)
                    return True
        elif event.type == pygame.MOUSEMOTION and self.drag is not None:
            before = self.drag.value
            self.drag.set(self.drag.value_at(event.pos[0]))
            if self.drag.value != before:
                self._changed(self.drag)
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag is not None:
            self.drag = None
            return True
        return False

    def update(self, dt):
        if not self.sliders:
            return
        slider = self.sliders[self.focus]
        for key in self.held:
            if key not in self.down:
                continue
            self.held[key] += dt
            sweeping = self.held[key] - 0.22
            if sweeping <= 0.0:
                continue
            rate = (slider.hi - slider.lo) * 0.18 * (1.0 + 3.0 * min(1.0, sweeping / 1.5))
            self.carry += rate * dt / slider.step
            steps = int(self.carry)
            if steps:
                self.carry -= steps
                before = slider.value
                slider.set(slider.value + (steps if key == pygame.K_RIGHT else -steps) * slider.step)
                if slider.value != before:
                    self._changed(slider)

    def draw(self, surf, gfx, time):
        for i, slider in enumerate(self.sliders):
            slider.draw(surf, gfx, i == self.focus, time)


class Typewriter:
    """Text that types itself out."""

    def __init__(self, text, cps=60.0):
        self.text = text
        self.cps = cps
        self.t = 0.0
        self._last = 0

    @property
    def count(self):
        return min(len(self.text), int(self.t * self.cps))

    @property
    def done(self):
        return self.count >= len(self.text)

    def update(self, dt, audio=None):
        self.t += dt
        count = self.count
        if audio is not None and count > self._last and count % 3 == 0 and not self.done:
            audio.play("type")
        self._last = count

    def skip(self):
        self.t = len(self.text) / self.cps + 1.0

    def visible(self):
        return self.text[:self.count]


def draw_dialogue(surf, gfx, rect, speaker, typer, time, color=CYAN, hint="ENTER"):
    """Nyx's speech box: portrait on the left, text typing out on the right."""
    surf.blit(gfx.plate(rect.size, (8, 10, 22, 236), 12), rect)
    pygame.draw.rect(surf, scale_color(color, 0.8), rect, 2, border_radius=12)
    portrait = min(rect.height - 30, 74)
    draw_nyx(surf, rect.left + 22 + portrait // 2, rect.top + 18 + portrait // 2, portrait * 0.42, time,
             talking=not typer.done, color=color)
    left = rect.left + portrait + 44
    gfx.text(surf, gfx.label, speaker, (left, rect.top + 14), color)
    width = rect.right - left - 22
    y = rect.top + 34
    for line in gfx.wrap(gfx.body, typer.visible(), width):
        gfx.text(surf, gfx.body, line, (left, y), TEXT)
        y += gfx.body.get_height() + 4
    if typer.done and hint:
        pulse = 0.6 + 0.4 * math.sin(time * 5.0)
        gfx.text(surf, gfx.small, hint + " ▶", (rect.right - 18, rect.bottom - 12), AMBER, "bottomright",
                 255 * pulse)
