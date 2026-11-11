"""Hyperplane Heist: the vault floor that every game mode plays on.

The Board owns the Perceptron (the laser), the units standing on the floor,
the player's controls and every animation on the floor.  It never decides
whether a heist is won: it reports what happened through `events`, and the
game mode (campaign, endless) applies its own rules.

Events (tuples, read with take_events()):
    ("judge", unit, correct)   the scanner sweep reached a unit
    ("scan_done",)             every unit has been judged
    ("alarm_done",)            the alarm before a counter-attack has finished
    ("snap_done",)             the laser has settled after a training step
    ("units_gone",)            the exit animation has finished
    ("changed", param)         the player moved the laser
    ("flip",)                  the player flipped the laser
"""
import math
import random

import pygame

from .core import (FLOOR_BOUNDS, PARAM_STEP, WORLD_CENTRE, WORLD_HI, WORLD_LO, Perceptron, boundary_endpoints,
                   clamp, ease_out, flip_params, from_pose, lerp, line_through, margin, polygon_centroid,
                   project_onto_line, quantize, rotate_about, signed, signed_distance, spring, to_pose)
from .gfx import (AMBER, ARROW_GREEN, BLACK, CYAN, FLOOR_EDGE, FLOOR_FILL, GREEN, GRID_MAJOR, GRID_MINOR, INK,
                  PANEL_EDGE, PANEL_FILL, RED, ROW_FILL, ROW_FLASH, TEXT, TEXT_DIM, TEXT_FAINT, VIOLET, WHITE,
                  Particles, Popups, Viewport, beam, draw_arc, draw_bot, draw_drone, draw_grid, draw_imposter,
                  draw_lock, draw_margin_corridor, draw_pulses, draw_verdict, draw_weight_arrow, draw_zones,
                  dashed_line, laser_segment, lightning, make_scan_strip, mix, scale_color, skin_color, thick_line)

FLOOR = pygame.Rect(52, 76, 600, 600)       # where the vault floor is drawn
PANEL = pygame.Rect(684, 76, 480, 600)      # the HUD

LEARNING_RATE = 0.1         # learning rate of the counter-attack training step
SCAN_TIME = 0.8             # seconds: scanner sweep after a lock-in
ALARM_TIME = 0.9            # seconds: alarm and target lock before the training step
SNAP_TIME = 0.65            # seconds: laser snapping to the retrained boundary
POWER_ON_TIME = 0.6         # seconds: laser powering up
TRAIL_LIFE = 0.22           # seconds: afterimages left behind by the snapping laser
ENTER_TIME = 0.7            # seconds: a unit flying in
EXIT_TIME = 0.7             # seconds: a unit leaving
AMBIENT_SCAN_EVERY = 6.0
AMBIENT_SCAN_TIME = 2.6

WEIGHT_RATE = 0.45          # weight units per second while a key is held
BIAS_RATE = 1.5             # bias units per second while a key is held
TURN_RATE = math.radians(32)
HOLD_DELAY = 0.2            # seconds before a held key starts sweeping
HOLD_RAMP = 3.0             # a long hold accelerates up to (1 + HOLD_RAMP) times the rate
WEIGHT_LIMIT = 30.0
BIAS_LIMIT = 200.0

KEY_PARAMS = {
    pygame.K_LEFT: ("w1", -1), pygame.K_RIGHT: ("w1", +1),
    pygame.K_DOWN: ("w2", -1), pygame.K_UP: ("w2", +1),
    pygame.K_s: ("b", -1), pygame.K_w: ("b", +1),
    pygame.K_SPACE: ("b", +1),          # SHIFT + SPACE reverses it
}
KEY_TURN = {pygame.K_q: +1, pygame.K_e: -1}     # Q turns counter-clockwise
CONTROL_KEYS = set(KEY_PARAMS) | set(KEY_TURN) | {pygame.K_f}
FOCUS_LOST = getattr(pygame, "WINDOWFOCUSLOST", None)
ARROWS = ("left", "right", "up", "down")


class Unit:
    """A bot (label 1) or a drone (label 0) on the vault floor."""

    def __init__(self, x, y, label, motion=None, disguised=False, reveal_at=None, tag=None):
        self.bx, self.by = float(x), float(y)       # base position (world units)
        self.x, self.y = float(x), float(y)         # where it is now
        self.label = label
        self.motion = motion
        self.disguised = disguised                  # a drone showing itself as a bot
        self.reveal_at = reveal_at                  # board clock time when the disguise drops
        self.tag = tag                              # text under the unit instead of its coordinates
        self.seed = random.random() * 10.0
        self.enter_t = 0.0
        self.enter_from = (x, y)
        self.exit_t = None                          # None while it stays on the floor
        self.exit_kind = None
        self.verdict = None                         # True / False once the scanner has judged it
        self.verdict_t = 0.0
        self.jx = self.jy = None                    # where it was when judged
        self.judged_dist = None
        self.reveal_flash = 0.0

    @property
    def shown_label(self):
        return 1 if self.disguised else self.label

    @property
    def moving(self):
        return self.motion is not None and self.motion.kind != "still"


class Board:
    def __init__(self, app, units=(), params=None, locks=(), theme=CYAN):
        self.app = app
        self.gfx = app.gfx
        self.audio = app.audio
        self.vp = Viewport(FLOOR, FLOOR_BOUNDS)
        self.brain = Perceptron()
        if params is not None:
            self.brain.set_params(*params)
        self.locks = set(locks)
        self.theme = theme
        self.static = self.build_static()
        self.scan_soft = make_scan_strip(CYAN, 34, FLOOR.height)
        self.scan_hard = make_scan_strip(mix(CYAN, WHITE, 0.5), 120, FLOOR.height)
        self.units = []
        self.time = 0.0
        self.clock = 0.0                # drives unit motion; restarts with each set of units
        self.motion_speed = 1.0
        self.phase = "control"          # control | scan | alarm | snap | frozen
        self.phase_t = 0.0
        self.events = []
        self.controls_enabled = True
        self.held = set()
        self.hold_time = {}
        self.carry = {}
        self.gesture = False            # a smooth change (drag, turn) is under way
        self.drag = None
        self.hover = None
        self.cursor = None
        self.particles = Particles()
        self.popups = Popups()
        self.fx_rng = random.Random()
        self.flash = {"w1": 0.0, "w2": 0.0, "b": 0.0}
        self.lock_flash = {"w1": 0.0, "w2": 0.0, "b": 0.0}
        self.delta = {}
        self.delta_time = 0.0
        self.last_update = None
        self.snap_from = self.snap_to = None
        self.snap_color = AMBER
        self.trails = []
        self.target = None
        self.target_assist = False
        self.power_on = 0.0
        self.ghost = None
        self.ghost_time = 0.0
        self.dismissing = False
        self.skin = "cyan"
        self.laser_override = None      # (colour, power) set by a mode, e.g. green on a win
        self.banner = None              # (text, colour) in the corner of the floor
        self.show_z = False
        self.show_paths = False
        self.show_tags = True
        self.show_margin = True
        self.ambient_scan = True
        self.offfloor_hint = True
        self.label_avoid = []           # screen rects the zone labels must keep clear of
        self.set_units(units, animate=False)

    # ------------------------------------------------------------------ setup
    def build_static(self):
        surf = self.gfx.backdrop.copy()
        draw_grid(surf, self.vp, self.gfx, fill=mix(FLOOR_FILL, self.theme, 0.05),
                  minor=mix(GRID_MINOR, self.theme, 0.07), major=mix(GRID_MAJOR, self.theme, 0.12), edge=False)
        pygame.draw.rect(surf, mix(FLOOR_EDGE, self.theme, 0.35), FLOOR.inflate(6, 6), 2, border_radius=4)
        pygame.draw.rect(surf, PANEL_FILL, PANEL, border_radius=10)
        pygame.draw.rect(surf, PANEL_EDGE, PANEL, 1, border_radius=10)
        return surf

    def set_theme(self, theme):
        if theme != self.theme:
            self.theme = theme
            self.static = self.build_static()

    def set_units(self, units, animate=True, stagger=0.06):
        self.units = list(units)
        self.clock = 0.0
        self.dismissing = False
        for i, u in enumerate(self.units):
            u.x, u.y = u.motion.position(u.bx, u.by, 0.0) if u.motion else (u.bx, u.by)
            if animate:
                dx, dy = u.x - WORLD_CENTRE[0], u.y - WORLD_CENTRE[1]
                length = math.hypot(dx, dy)
                if length < 1e-6:
                    angle = random.uniform(0, math.tau)
                    dx, dy, length = math.cos(angle), math.sin(angle), 1.0
                u.enter_from = (WORLD_CENTRE[0] + dx / length * 8.5, WORLD_CENTRE[1] + dy / length * 8.5)
                u.enter_t = -stagger * i
            else:
                u.enter_t = ENTER_TIME

    def dismiss_units(self):
        """Play every unit's exit animation, then report ("units_gone",)."""
        if not self.units:
            self.events.append(("units_gone",))
            return
        self.dismissing = True
        for u in self.units:
            u.exit_t = 0.0
            if u.verdict is None:
                u.exit_kind = "dissolve"
            elif not u.verdict:
                u.exit_kind = "glitch"
            else:
                u.exit_kind = "teleport" if u.label == 1 else "caught"
            x, y = self.unit_screen(u)
            if u.exit_kind == "caught":
                self.particles.spark(x, y, RED, count=14, speed=160, life=0.5)
            elif u.exit_kind == "teleport":
                self.particles.spark(x, y, GREEN, count=8, speed=90, life=0.6, gravity=-160)
        self.audio.play("teleport")

    def take_events(self):
        events, self.events = self.events, []
        return events

    # ------------------------------------------------------------- parameters
    @property
    def params(self):
        return self.brain.params

    def set_params(self, w1, w2, b, quant=True):
        w1 = clamp(w1, -WEIGHT_LIMIT, WEIGHT_LIMIT)
        w2 = clamp(w2, -WEIGHT_LIMIT, WEIGHT_LIMIT)
        b = clamp(b, -BIAS_LIMIT, BIAS_LIMIT)
        if quant:
            w1, w2, b = quantize(w1), quantize(w2), quantize(b)
        self.brain.set_params(w1, w2, b)

    def quantize_params(self):
        self.set_params(*self.brain.params, quant=True)

    def end_gesture(self):
        if self.gesture:
            self.gesture = False
            self.quantize_params()

    def can_control(self):
        return self.phase == "control" and self.controls_enabled

    def deny(self, param):
        self.lock_flash[param] = 0.6
        self.audio.play("ui_back")

    def nudge(self, param, steps):
        """Move one parameter by a whole number of 0.01 steps."""
        if param in self.locks:
            self.deny(param)
            return
        brain = self.brain
        old = brain.bias if param == "b" else brain.weights[0 if param == "w1" else 1]
        limit = BIAS_LIMIT if param == "b" else WEIGHT_LIMIT
        new = round(old + steps * PARAM_STEP, 6)
        if abs(new) > limit and abs(new) > abs(old):
            return
        if param == "b":
            brain.bias = new
        else:
            brain.weights[0 if param == "w1" else 1] = new
        self.flash[param] = max(self.flash[param], 0.18)
        self.events.append(("changed", param))
        self.audio.play("tick")

    def turn(self, angle):
        """Rotate the laser.  With the bias locked it turns around the origin."""
        if "w1" in self.locks or "w2" in self.locks:
            self.deny("w1" if "w1" in self.locks else "w2")
            return
        w1, w2, b = self.brain.params
        if math.hypot(w1, w2) < 1e-9:
            return
        if "b" in self.locks:
            c, s = math.cos(angle), math.sin(angle)
            new = (c * w1 - s * w2, s * w1 + c * w2, b)
        else:
            pivot = project_onto_line(w1, w2, b, WORLD_CENTRE[0], WORLD_CENTRE[1])
            new = rotate_about(w1, w2, b, angle, pivot)
        self.set_params(*new, quant=False)
        self.gesture = True
        self.flash["w1"] = self.flash["w2"] = max(self.flash["w1"], 0.18)
        self.events.append(("changed", "turn"))

    def flip(self):
        w1, w2, b = self.brain.params
        if "w1" in self.locks or "w2" in self.locks or ("b" in self.locks and abs(b) > 1e-9):
            self.deny("b" if "b" in self.locks else "w1")
            return
        self.set_params(*flip_params(w1, w2, b), quant=not self.gesture)
        for key in self.flash:
            self.flash[key] = 0.4
        self.particles.burst_along(self.segment_now(), mix(CYAN, VIOLET, 0.5), 24, 120, 0.5)
        self.events.append(("flip",))
        self.audio.play("flip")

    def binding(self, key):
        param, direction = KEY_PARAMS[key]
        if key == pygame.K_SPACE and (pygame.K_LSHIFT in self.held or pygame.K_RSHIFT in self.held):
            direction = -direction
        return param, direction

    # ------------------------------------------------------------------ input
    def handle_event(self, event):
        """Returns True if the board used the event."""
        if event.type == pygame.KEYDOWN:
            self.held.add(event.key)
            if event.key not in CONTROL_KEYS:
                return False
            if not self.can_control():
                return True
            if event.key in KEY_PARAMS:
                param, direction = self.binding(event.key)
                self.nudge(param, direction)        # a tap is always exactly one step
            elif event.key in KEY_TURN:
                self.turn(math.radians(1.0) * KEY_TURN[event.key])
            elif event.key == pygame.K_f:
                self.flip()
            self.hold_time[event.key] = 0.0
            self.carry[event.key] = 0.0
            return True
        if event.type == pygame.KEYUP:
            self.held.discard(event.key)
            if event.key in KEY_TURN:
                self.end_gesture()
            return event.key in CONTROL_KEYS
        if FOCUS_LOST is not None and event.type == FOCUS_LOST:
            self.held.clear()
            self.drag = None
            self.end_gesture()
            return False
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
            return self.handle_mouse(event)
        return False

    def handle_mouse(self, event):
        if event.type == pygame.MOUSEMOTION:
            if self.drag is not None:
                if self.can_control():
                    self.update_drag(event.pos)
                return True
            self.update_hover(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if not self.can_control() or not self.vp.contains(event.pos[0], event.pos[1], 14):
                return False
            if event.button == 1:
                self.start_drag(event.pos)
                return True
            if event.button == 3:
                self.flip()
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.drag is not None:
                self.drag = None
                self.end_gesture()
                return True
            return False
        if event.type == pygame.MOUSEWHEEL and self.can_control():
            pos = pygame.mouse.get_pos()
            if self.vp.contains(pos[0], pos[1], 14) and event.y:
                self.turn(math.radians(2.0) * (1 if event.y > 0 else -1))
                self.end_gesture()
                return True
        return False

    def hit_test(self, pos):
        segment = self.segment_now()
        if segment is None:
            return None
        for i, (x, y) in enumerate(segment):
            if math.hypot(pos[0] - x, pos[1] - y) <= 16:
                return ("end", i)
        (ax, ay), (ex, ey) = segment
        dx, dy = ex - ax, ey - ay
        length2 = dx * dx + dy * dy
        if length2 > 1e-6:
            t = clamp(((pos[0] - ax) * dx + (pos[1] - ay) * dy) / length2, 0.0, 1.0)
            if math.hypot(pos[0] - (ax + dx * t), pos[1] - (ay + dy * t)) <= 11:
                return ("beam",)
        return None

    def set_cursor(self, name):
        if name == self.cursor:
            return
        self.cursor = name
        try:
            cursor = {"hand": pygame.SYSTEM_CURSOR_HAND, "cross": pygame.SYSTEM_CURSOR_CROSSHAIR,
                      "move": pygame.SYSTEM_CURSOR_SIZEALL}.get(name, pygame.SYSTEM_CURSOR_ARROW)
            pygame.mouse.set_cursor(cursor)
        except (pygame.error, AttributeError, TypeError):
            pass

    def update_hover(self, pos):
        if not self.can_control() or not self.vp.contains(pos[0], pos[1], 14):
            self.hover = None
            self.set_cursor(None)
            return
        self.hover = self.hit_test(pos)
        if self.hover and self.hover[0] == "end":
            self.set_cursor("hand")
        elif self.hover:
            self.set_cursor("move")
        else:
            self.set_cursor("cross")

    def mouse_world(self, pos):
        x = clamp(pos[0], FLOOR.left, FLOOR.right)
        y = clamp(pos[1], FLOOR.top, FLOOR.bottom)
        return self.vp.to_world(x, y)

    def start_drag(self, pos):
        w1, w2, b = self.brain.params
        norm = math.hypot(w1, w2)
        weights_locked = "w1" in self.locks or "w2" in self.locks
        hit = self.hit_test(pos)
        world = self.mouse_world(pos)
        if hit and hit[0] == "end" and not weights_locked:
            ends = boundary_endpoints(w1, w2, b)
            fixed = ends[1 - hit[1]] if ends else WORLD_CENTRE
            self.drag = ("end", fixed, norm if norm > 0.05 else 0.5, (w1, w2))
        elif weights_locked or (hit and hit[0] == "beam"):
            if "b" in self.locks:
                self.deny("b")
                return
            if norm < 1e-9:
                return
            self.drag = ("beam", world, b, (w1, w2))
        else:
            ref = (w1, w2) if norm > 1e-9 else (0.0, 0.5)
            self.drag = ("draw", world, norm if norm > 0.05 else 0.5, ref)
        self.gesture = True
        self.audio.play("ui_move")

    def update_drag(self, pos):
        kind = self.drag[0]
        mx, my = self.mouse_world(pos)
        b_locked = "b" in self.locks
        if kind in ("end", "draw"):
            anchor, norm, ref = self.drag[1], self.drag[2], self.drag[3]
            if b_locked:
                if abs(self.brain.bias) > 1e-9:
                    return
                anchor = (0.0, 0.0)
            if math.hypot(mx - anchor[0], my - anchor[1]) < 0.35:
                return
            new = line_through(anchor, (mx, my), ref, norm)
            if new is None:
                return
            if b_locked:
                new = (new[0], new[1], 0.0)
            self.set_params(*new, quant=False)
            self.drag = (kind, self.drag[1], norm, (new[0], new[1]))
            self.flash["w1"] = self.flash["w2"] = self.flash["b"] = 0.15
        elif kind == "beam":
            start, b0, (w1, w2) = self.drag[1], self.drag[2], self.drag[3]
            n = math.hypot(w1, w2)
            if n < 1e-9:
                return
            d = (mx - start[0]) * w1 / n + (my - start[1]) * w2 / n
            self.set_params(w1, w2, b0 - d * n, quant=False)
            self.flash["b"] = 0.15
        self.events.append(("changed", kind))

    def update_controls(self, dt):
        """Held keys sweep their parameter, accelerating the longer they are held."""
        for key in KEY_PARAMS:
            if key not in self.held:
                continue
            self.hold_time[key] = self.hold_time.get(key, 0.0) + dt
            sweeping = self.hold_time[key] - HOLD_DELAY
            if sweeping <= 0.0:
                continue
            param, direction = self.binding(key)
            if param in self.locks:
                continue
            rate = BIAS_RATE if param == "b" else WEIGHT_RATE
            rate *= 1.0 + HOLD_RAMP * min(1.0, sweeping / 1.5)
            self.carry[key] = self.carry.get(key, 0.0) + rate * dt / PARAM_STEP
            steps = int(self.carry[key])
            if steps:
                self.carry[key] -= steps
                self.nudge(param, direction * steps)
        for key, direction in KEY_TURN.items():
            if key not in self.held:
                continue
            self.hold_time[key] = self.hold_time.get(key, 0.0) + dt
            sweeping = self.hold_time[key] - HOLD_DELAY
            if sweeping > 0.0:
                self.turn(direction * TURN_RATE * (1.0 + HOLD_RAMP * min(1.0, sweeping / 1.5)) * dt)

    # ------------------------------------------------------------- the phases
    def begin_scan(self):
        """Freeze the laser and sweep the scanner across every unit."""
        self.drag = None
        self.gesture = False
        self.quantize_params()
        self.phase = "scan"
        self.phase_t = 0.0
        self.set_cursor(None)
        for u in self.units:
            u.verdict = None
            u.judged_dist = None
        self.audio.play("scan")

    def judge(self, u):
        if u.disguised:
            u.disguised = False
            u.reveal_flash = 1.0
            self.audio.play("reveal")
        predicted = self.brain.predict(u.x, u.y)
        u.verdict = predicted == u.label
        u.verdict_t = 0.0
        u.jx, u.jy = u.x, u.y
        distance = signed_distance(*self.brain.params, u.x, u.y)
        u.judged_dist = abs(distance) if distance is not None else 0.0
        x, y = self.unit_screen(u)
        if u.verdict:
            self.particles.spark(x, y, GREEN if u.label == 1 else mix(RED, WHITE, 0.3), count=8, speed=110, life=0.45)
        else:
            self.particles.spark(x, y, AMBER, count=14, speed=170, life=0.55)
        self.events.append(("judge", u, u.verdict))

    def begin_alarm(self, unit):
        self.phase = "alarm"
        self.phase_t = 0.0
        self.target = unit
        self.target_assist = False
        self.app.add_shake(1.0)
        self.audio.play("alarm")
        for u in self.units:
            if u.verdict is False:
                x, y = self.unit_screen(u)
                self.particles.spark(x, y, RED, count=10, speed=150, life=0.5)

    def counter_attack(self, unit, x1=None, x2=None, learning_rate=LEARNING_RATE, assist=False, label=None):
        """Exactly ONE perceptron training step on `unit` (at its judged position
        unless x1, x2 are given), then the laser snaps to the new boundary."""
        brain = self.brain
        if x1 is None:
            x1, x2 = (unit.jx, unit.jy) if unit.jx is not None else (unit.x, unit.y)
        label = unit.label if label is None else label
        old = brain.params
        old_segment = self.segment_now()
        predicted = brain.predict(x1, x2)
        changed = brain.train(x1, x2, label, learning_rate)
        new = brain.params
        self.target = unit
        self.target_assist = assist
        self.last_update = {"point": (x1, x2), "label": label, "predicted": predicted, "old": old, "new": new,
                            "assist": assist, "lr": learning_rate}
        if not changed:
            self.phase = "frozen"
            self.events.append(("snap_done",))
            return False
        self.delta = {"w1": new[0] - old[0], "w2": new[1] - old[1], "b": new[2] - old[2]}
        self.delta_time = 4.0
        self.flash = {"w1": 0.7, "w2": 0.7, "b": 0.7}
        self.snap_from, self.snap_to = to_pose(*old), to_pose(*new)
        self.snap_color = CYAN if assist else AMBER
        self.app.add_shake(0.35 if assist else 0.9)
        self.particles.burst_along(old_segment, self.snap_color, 46, 240, 0.7)
        self.phase = "snap"
        self.phase_t = 0.0
        self.audio.play("snap")
        return True

    def show_ghost(self, params, seconds=2.4):
        self.ghost = params
        self.ghost_time = seconds

    def set_phase(self, phase):
        self.phase = phase
        self.phase_t = 0.0
        if phase == "control":
            for u in self.units:             # old verdicts would mislead while the player adjusts
                u.verdict = None

    # ----------------------------------------------------------------- update
    def update(self, dt):
        self.time += dt
        self.phase_t += dt
        self.power_on += dt
        self.delta_time = max(0.0, self.delta_time - dt)
        for name in self.flash:
            self.flash[name] = max(0.0, self.flash[name] - dt)
            self.lock_flash[name] = max(0.0, self.lock_flash[name] - dt)
        self.ghost_time = max(0.0, self.ghost_time - dt)
        self.trails = [(a, e, life - dt) for a, e, life in self.trails if life > dt]
        self.particles.update(dt)
        self.popups.update(dt)
        self.update_units(dt)

        phase = self.phase
        if phase == "control":
            if self.controls_enabled:
                self.update_controls(dt)
                segment = self.segment_now()
                if segment and self.power_on >= POWER_ON_TIME:
                    color = skin_color(self.skin, self.time)
                    for end in segment:
                        if self.fx_rng.random() < 9 * dt:
                            self.particles.spark(end[0], end[1], color, speed=70, life=0.45, size=2)
        elif phase == "scan":
            progress = self.phase_t / SCAN_TIME
            sweep = lerp(WORLD_LO - 0.6, WORLD_HI + 0.6, min(1.0, progress))
            for u in self.units:
                if u.verdict is None and u.exit_t is None and u.x <= sweep:
                    self.judge(u)
            if progress >= 1.0:
                for u in self.units:
                    if u.verdict is None and u.exit_t is None:
                        self.judge(u)
                self.phase = "frozen"
                self.events.append(("scan_done",))
        elif phase == "alarm":
            if self.phase_t >= ALARM_TIME:
                self.phase = "frozen"
                self.events.append(("alarm_done",))
        elif phase == "snap":
            segment = self.segment_now()
            if segment:
                self.trails.append((segment[0], segment[1], TRAIL_LIFE))
            if self.phase_t >= SNAP_TIME:
                self.phase = "frozen"
                self.events.append(("snap_done",))

    def update_units(self, dt):
        self.clock += dt * self.motion_speed
        for u in self.units:
            if u.motion is not None:
                u.x, u.y = u.motion.position(u.bx, u.by, self.clock)
            u.enter_t += dt
            u.verdict_t += dt
            u.reveal_flash = max(0.0, u.reveal_flash - dt * 1.5)
            if u.exit_t is not None:
                u.exit_t += dt
            if u.disguised and u.reveal_at is not None and self.clock >= u.reveal_at:
                u.disguised = False
                u.reveal_flash = 1.0
                x, y = self.unit_screen(u)
                self.particles.spark(x, y, RED, count=18, speed=180, life=0.6)
                self.popups.add("IMPOSTER!", x, y - 30, RED, "label", 1.2)
                self.audio.play("reveal")
        if self.dismissing and all(u.exit_t is not None and u.exit_t >= EXIT_TIME for u in self.units):
            self.units = []
            self.dismissing = False
            self.events.append(("units_gone",))

    # ---------------------------------------------------------------- queries
    def active_units(self):
        return [u for u in self.units if u.exit_t is None]

    def points(self, shown=False):
        return [(u.x, u.y, u.shown_label if shown else u.label) for u in self.active_units()]

    def errors_now(self, shown=True):
        w1, w2, b = self.brain.params
        return sum(1 for x, y, label in self.points(shown) if (1 if w1 * x + w2 * y + b > 0 else 0) != label)

    def margin_now(self, shown=True):
        return margin(*self.brain.params, self.points(shown))

    def judged_margin(self):
        values = [u.judged_dist for u in self.units if u.verdict and u.judged_dist is not None]
        return min(values) if values else None

    def unit_screen(self, u):
        return self.vp.to_screen(u.x, u.y)

    def display_params(self):
        """The boundary to DRAW: the live perceptron, except during the snap
        animation that carries it from the old boundary to the retrained one."""
        if self.phase == "snap" and self.snap_from and self.snap_to:
            s = spring(self.phase_t / SNAP_TIME)
            theta0, offset0 = self.snap_from
            theta1, offset1 = self.snap_to
            turn = (theta1 - theta0 + math.pi) % math.tau - math.pi
            offset0, offset1 = clamp(offset0, -9.0, 9.0), clamp(offset1, -9.0, 9.0)
            return from_pose(theta0 + turn * s, lerp(offset0, offset1, s))
        return self.brain.params

    def segment_now(self):
        return laser_segment(self.vp, *self.display_params())

    def scan_x(self):
        if self.phase == "scan":
            return FLOOR.left + lerp(-0.06, 1.06, min(1.0, self.phase_t / SCAN_TIME)) * FLOOR.width
        if self.phase == "control" and self.ambient_scan:
            phase = self.time % AMBIENT_SCAN_EVERY
            if phase < AMBIENT_SCAN_TIME:
                return FLOOR.left + phase / AMBIENT_SCAN_TIME * (FLOOR.width + 120)
        return None

    def laser_look(self):
        t = self.phase_t
        base = skin_color(self.skin, self.time)
        flashes = self.app.profile.settings.get("flashes", True)
        if self.laser_override is not None:
            return self.laser_override
        if self.phase == "scan":
            return mix(base, WHITE, 0.5), 1.15
        if self.phase == "alarm":
            if not flashes:
                return RED, 1.0
            return mix(RED, AMBER, 0.5 + 0.5 * math.sin(t * 19.0)), 1.1
        if self.phase == "snap":
            k = clamp(t / SNAP_TIME, 0.0, 1.0)
            return mix(RED if not self.target_assist else CYAN, base, k * k), 1.3 - 0.3 * k
        return base, 0.92 + 0.08 * math.sin(self.time * 7.0)

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        surf.blit(self.static, (0, 0))
        w1, w2, b = self.display_params()
        zones = draw_zones(surf, self.vp, w1, w2, b, alpha=30)
        self.draw_zone_labels(surf, zones, w1, w2, b)
        if self.show_margin and self.phase in ("control", "frozen") and self.units:
            slack, errors = self.margin_now(shown=True)
            if errors == 0 and slack:
                draw_margin_corridor(surf, self.vp, w1, w2, b, slack, scale_color(ARROW_GREEN, 0.55), self.time)
        if self.ghost is not None and self.ghost_time > 0:
            ends = boundary_endpoints(*self.ghost)
            if ends:
                k = min(1.0, self.ghost_time / 0.5)
                dashed_line(surf, mix(BLACK, WHITE, 0.85 * k), self.vp.to_screen(*ends[0]),
                            self.vp.to_screen(*ends[1]), 3, 12.0, 8.0, self.time * 40)
        if self.show_paths:
            self.draw_paths(surf)
        if self.power_on >= POWER_ON_TIME:
            draw_weight_arrow(surf, self.vp, self.gfx, w1, w2, b)
        self.draw_scan_bar(surf)
        self.draw_units(surf, w1, w2, b)
        self.draw_laser(surf, w1, w2, b)
        self.draw_markers(surf)
        if self.banner:
            text, color = self.banner
            rect = pygame.Rect(FLOOR.left + 12, FLOOR.top + 12, self.gfx.body.size(text)[0] + 28, 30)
            surf.blit(self.gfx.plate(rect.size), rect)
            pygame.draw.rect(surf, color, rect, 1, border_radius=8)
            self.gfx.text(surf, self.gfx.body, text, rect.center, color, "center")
        self.particles.draw(surf)
        self.popups.draw(surf, self.gfx)

    def draw_zone_labels(self, surf, zones, w1, w2, b):
        units = [self.unit_screen(u) for u in self.units]
        norm = math.hypot(w1, w2)
        for positive, points in zones:
            centre, area = polygon_centroid(points)
            if centre is None or area < 16000:
                continue
            candidates = [centre]
            for k in (0.35, 0.6):
                candidates.extend((lerp(centre[0], vx, k), lerp(centre[1], vy, k)) for vx, vy in points)
            for x, y in candidates:
                if not (FLOOR.left + 62 <= x <= FLOOR.right - 62 and FLOOR.top + 50 <= y <= FLOOR.bottom - 26):
                    continue
                if norm > 1e-9:
                    wx, wy = self.vp.to_world(x, y)
                    if abs(w1 * wx + w2 * wy + b) / norm * self.vp.ppu < 44:
                        continue
                if units and min(math.hypot(x - ux, y - uy) for ux, uy in units) < 66:
                    continue
                if any(rect.inflate(110, 40).collidepoint(x, y) for rect in self.label_avoid):
                    continue
                color = GREEN if positive else RED
                self.gfx.text(surf, self.gfx.label, "SAFE ZONE" if positive else "ALARM ZONE", (x, y - 8), color,
                              "center", 150)
                self.gfx.text(surf, self.gfx.tiny, "output 1" if positive else "output 0", (x, y + 8), color,
                              "center", 120)
                break

    def draw_paths(self, surf):
        for u in self.units:
            if u.motion is None or u.motion.kind != "patrol" or u.exit_t is not None:
                continue
            a = self.vp.to_screen(u.bx, u.by)
            e = self.vp.to_screen(*u.motion.to)
            color = scale_color(GREEN if u.label == 1 else RED, 0.55)
            dashed_line(surf, color, a, e, 2, 6.0, 7.0, self.time * 10)
            for p in (a, e):
                pygame.draw.circle(surf, color, (int(p[0]), int(p[1])), 4, 1)

    def draw_scan_bar(self, surf):
        x = self.scan_x()
        if x is None:
            return
        strip = self.scan_hard if self.phase == "scan" else self.scan_soft
        surf.set_clip(FLOOR)
        surf.blit(strip, (int(x) - strip.get_width(), FLOOR.top))
        surf.set_clip(None)

    def draw_units(self, surf, w1, w2, b):
        gfx = self.gfx
        sweep = self.scan_x()
        live = self.phase == "control" and self.controls_enabled
        for u in self.units:
            progress = clamp(u.enter_t / ENTER_TIME, 0.0, 1.0)
            if u.enter_t <= 0.0:
                continue
            tx, ty = self.unit_screen(u)
            if progress < 1.0:
                fx, fy = self.vp.to_screen(*u.enter_from)
                e = ease_out(progress)
                x, y = lerp(fx, tx, e), lerp(fy, ty, e)
                tail = ease_out(max(0.0, progress - 0.18))
                streak = mix(BLACK, GREEN if u.shown_label == 1 else RED, 0.7)
                thick_line(surf, streak, (lerp(fx, tx, tail), lerp(fy, ty, tail)), (x, y), 4)
            else:
                x, y = tx, ty
            y += math.sin(self.time * 2.2 + u.seed) * 1.6
            scale = 1.0
            if u.exit_t is not None:
                k = clamp(u.exit_t / EXIT_TIME, 0.0, 1.0)
                scale = max(0.0, 1.0 - k * k)
                if u.exit_kind == "teleport":
                    column = scale_color(GREEN, 0.6 * (1.0 - k))
                    pygame.draw.rect(surf, column, (x - 10 * (1 - k) - 2, FLOOR.top, 20 * (1 - k) + 4, y - FLOOR.top))
                    y -= 40 * k * k
                elif u.exit_kind == "caught":
                    ring = int(26 * (1.0 - k) + 6)
                    pygame.draw.circle(surf, mix(RED, WHITE, 0.4), (int(x), int(y)), ring, 2)
                    if self.fx_rng.random() < 0.5:
                        lightning(surf, (x - ring, y), (x + ring, y), (255, 210, 220), self.fx_rng, 5, 6.0, 1)
                elif u.exit_kind == "glitch":
                    x += self.fx_rng.uniform(-5, 5) * (1 - k)
            if scale <= 0.05:
                continue
            color = GREEN if u.shown_label == 1 else RED
            gfx.add_glow(surf, x, y, 34, color, 0.5 * scale)
            ping = 0.0
            if sweep is not None and 0.0 <= sweep - x <= 120.0:
                ping = 1.0 - (sweep - x) / 120.0
            ping = max(ping, u.reveal_flash)
            t = self.time + u.seed
            if u.disguised:
                nervous = 0.0
                if u.reveal_at is not None:
                    nervous = clamp(1.0 - (u.reveal_at - self.clock) / 1.6, 0.0, 1.0)
                draw_imposter(surf, x, y, t, self.fx_rng, ping, scale, nervous)
            elif u.label == 1:
                draw_bot(surf, x, y, t, ping, scale)
            else:
                draw_drone(surf, x, y, t, ping, scale)
            if u.exit_t is not None:
                continue
            if self.show_tags and progress >= 1.0:
                if u.tag is not None:
                    gfx.text(surf, gfx.small, u.tag, (x, y + 25), TEXT_DIM, "midtop")
                elif not u.moving:
                    gfx.text(surf, gfx.tiny, "({:g}, {:g})".format(round(u.bx, 1), round(u.by, 1)), (x, y + 25),
                             TEXT_FAINT, "midtop")
            if self.show_z and progress >= 1.0:
                z = w1 * u.x + w2 * u.y + b
                label = "z={:+.2f}".format(z)
                width, height = gfx.tiny.size(label)
                plate = pygame.Rect(0, 0, width + 8, height + 2)
                plate.midbottom = (int(x), int(y) - 32)
                surf.blit(gfx.plate(plate.size, (8, 10, 20, 210), 4), plate)
                gfx.text(surf, gfx.tiny, label, plate.center, VIOLET, "center")
            if live and progress >= 1.0 and (1 if w1 * u.x + w2 * u.y + b > 0 else 0) != u.shown_label:
                pulse = 0.5 + 0.5 * math.sin(self.time * 9.0)
                pygame.draw.circle(surf, mix(AMBER, WHITE, pulse * 0.4), (x, y), 25 + 2 * pulse, 2)
            if u.verdict is not None:
                pop = clamp(u.verdict_t / 0.18, 0.0, 1.0)
                draw_verdict(surf, int(x + 20), int(y - 20), u.verdict, 0.4 + 0.6 * pop)

    def draw_laser(self, surf, w1, w2, b):
        color, power = self.laser_look()
        fx = self.gfx.fx
        fx.set_clip(FLOOR)
        fx.fill(BLACK, FLOOR)
        for a, e, life in self.trails:
            beam(fx, a, e, color, 0.45 * life / TRAIL_LIFE, core=False, extend=40)
        segment = laser_segment(self.vp, w1, w2, b)
        grown = True
        if segment:
            a, e = segment
            grow = ease_out(self.power_on / POWER_ON_TIME)
            if grow < 1.0:
                grown = False
                mid = ((a[0] + e[0]) / 2.0, (a[1] + e[1]) / 2.0)
                a = (lerp(mid[0], a[0], grow), lerp(mid[1], a[1], grow))
                e = (lerp(mid[0], e[0], grow), lerp(mid[1], e[1], grow))
            beam(fx, a, e, color, power, extend=40 if grown else 0)
            draw_pulses(fx, a, e, color, self.time)
        fx.set_clip(None)
        surf.blit(fx, FLOOR.topleft, FLOOR, special_flags=pygame.BLEND_RGB_ADD)
        if segment is None:
            if self.offfloor_hint and self.units:
                self.draw_off_floor_hint(surf, w1, w2, b)
            return
        if grown:
            hovering = self.hover[1] if self.hover and self.hover[0] == "end" else None
            dragging = self.drag is not None and self.drag[0] == "end"
            for i, (x, y) in enumerate(segment):
                big = hovering == i or dragging
                r = 11 if big else 8
                if big:
                    pygame.draw.circle(surf, scale_color(color, 0.5), (x, y), r + 6, 2)
                pygame.draw.circle(surf, INK, (x, y), r)
                pygame.draw.circle(surf, color, (x, y), r, 2)
                pygame.draw.circle(surf, WHITE, (x, y), 3)

    def draw_off_floor_hint(self, surf, w1, w2, b):
        gfx = self.gfx
        text_x, text_y = FLOOR.centerx, FLOOR.centery + 46
        pose = to_pose(w1, w2, b)
        if pose is None:
            everything = "SAFE" if b > 0 else "ALARM"
            gfx.text(surf, gfx.label, "NO LASER: w1 = w2 = 0", (text_x, text_y), AMBER, "center")
            gfx.text(surf, gfx.tiny, "only the bias decides now, so every unit scans as " + everything,
                     (text_x, text_y + 17), TEXT_DIM, "center")
            return
        if "b" in self.locks:
            advice = "turn it back with Q / E or the arrows"
        else:
            advice = "slide it back with W / S, or drag on the floor"
        gfx.text(surf, gfx.label, "LASER IS OFF THE FLOOR", (text_x, text_y), AMBER, "center")
        gfx.text(surf, gfx.tiny, advice, (text_x, text_y + 17), TEXT_DIM, "center")
        theta, offset = pose
        side = 1.0 if offset >= 0 else -1.0
        dx, dy = math.cos(theta) * side, -math.sin(theta) * side
        reach = (FLOOR.width / 2.0 - 30.0) / max(abs(dx), abs(dy))
        x, y = FLOOR.centerx + dx * reach, FLOOR.centery + dy * reach
        push = 6.0 * (0.5 + 0.5 * math.sin(self.time * 6.0))
        tip = (x + dx * (8 + push), y + dy * (8 + push))
        thick_line(surf, AMBER, (x - dx * (30 - push), y - dy * (30 - push)), (tip[0] - dx * 8, tip[1] - dy * 8), 4)
        pygame.draw.polygon(surf, AMBER, (tip,
                                          (tip[0] - dx * 14 - dy * 8, tip[1] - dy * 14 + dx * 8),
                                          (tip[0] - dx * 14 + dy * 8, tip[1] - dy * 14 - dx * 8)))

    def draw_markers(self, surf):
        """The reticle on the unit the perceptron is about to train on."""
        if self.target is None:
            return
        if not (self.phase == "alarm" or (self.phase == "snap" and self.phase_t < SNAP_TIME * 0.6)):
            return
        u = self.target
        px, py = (u.jx, u.jy) if (u.jx is not None and not self.target_assist) else (u.x, u.y)
        x, y = self.vp.to_screen(px, py)
        color = CYAN if self.target_assist else AMBER
        lock = 1.0 if self.phase == "snap" else self.phase_t / ALARM_TIME
        radius = lerp(80.0, 32.0, ease_out(lock * 1.5))
        spin = self.time * 3.0
        for k in range(4):
            angle = spin + k * math.pi / 2
            draw_arc(surf, color, (x, y), radius, angle - 0.5, angle + 0.5, 3)
            ca, sa = math.cos(angle), math.sin(angle)
            pygame.draw.line(surf, color, (x + ca * (radius + 5), y + sa * (radius + 5)),
                             (x + ca * (radius + 16), y + sa * (radius + 16)), 2)
        caption = "{} ON {} ({:.1f}, {:.1f})".format("AUTO-TRAIN" if self.target_assist else "RETRAINING",
                                                    "BOT" if u.label == 1 else "DRONE", px, py)
        width = self.gfx.small.size(caption)[0] + 22
        rect = pygame.Rect(0, 0, width, 24)
        rect.centerx = int(clamp(x, FLOOR.left + width / 2 + 6, FLOOR.right - width / 2 - 6))
        rect.centery = int(y + 62 if y < FLOOR.bottom - 150 else y - 62)
        surf.blit(self.gfx.plate(rect.size), rect)
        pygame.draw.rect(surf, color, rect, 1, border_radius=8)
        self.gfx.text(surf, self.gfx.small, caption, rect.center, color, "center")

    # ------------------------------------------------------------------ panel
    def equation_segments(self):
        w1, w2 = self.brain.weights
        b = self.brain.bias

        def sign(v):
            return " - " if round(v, 2) < 0 else " + "
        return [("{:.2f}".format(round(w1, 2) + 0.0), CYAN), ("·x₁", TEXT), (sign(w2), TEXT),
                ("{:.2f}".format(abs(round(w2, 2))), CYAN), ("·x₂", TEXT), (sign(b), TEXT),
                ("{:.2f}".format(abs(round(b, 2))), AMBER), (" = 0", TEXT)]

    def draw_params(self, surf, top, compact=False):
        """Equation and the w1 / w2 / b rows.  Returns the y below them."""
        gfx = self.gfx
        left, right = PANEL.left + 22, PANEL.right - 22
        y = top
        gfx.text(surf, gfx.label, "DECISION BOUNDARY", (left, y), CYAN)
        gfx.text(surf, gfx.tiny, "SAFE where the left side is > 0", (right, y + 1), TEXT_FAINT, "topright")
        y += 18
        gfx.rich(surf, gfx.mid, self.equation_segments(), (left, y))
        y += 32
        live = self.can_control()
        rows = (
            ("w1", "w₁", self.brain.weights[0], "weight on x₁", 2.0, (("left", pygame.K_LEFT), ("right", pygame.K_RIGHT))),
            ("w2", "w₂", self.brain.weights[1], "weight on x₂", 2.0, (("down", pygame.K_DOWN), ("up", pygame.K_UP))),
            ("b", "b", self.brain.bias, "bias: slides it", 8.0, (("S", pygame.K_s), ("W", pygame.K_w),
                                                                ("SPACE", pygame.K_SPACE))),
        )
        row_h = 50 if compact else 56
        for name, symbol, value, hint, gauge, keys in rows:
            box = pygame.Rect(left - 10, y, right - left + 20, row_h - 6)
            locked = name in self.locks
            fill = mix(ROW_FILL, ROW_FLASH, self.flash[name] * 4.0)
            if self.lock_flash[name] > 0:
                fill = mix(ROW_FILL, (90, 30, 40), self.lock_flash[name] * 1.5)
            pygame.draw.rect(surf, fill, box, border_radius=6)
            gfx.text(surf, gfx.mid, symbol, (left, y + 4), TEXT_FAINT if locked else (AMBER if name == "b" else CYAN))
            if locked:
                draw_lock(surf, left + 52, y + 9, 12, TEXT_DIM)
                gfx.text(surf, gfx.small, "locked in this vault", (left + 66, y + 8), TEXT_FAINT)
            else:
                gfx.text(surf, gfx.small, hint, (left + 44, y + 8), TEXT_DIM)
                key_x = left + 44
                for label, key in keys:
                    active = live and key in self.held
                    if label in ARROWS:
                        key_x = gfx.keycap(surf, key_x, y + 26, arrow=label, active=active)
                    else:
                        key_x = gfx.keycap(surf, key_x, y + 26, label=label, active=active)
            gfx.text(surf, gfx.value, signed(value), (right, y + 2), TEXT_FAINT if locked else TEXT, "topright")
            if self.delta_time > 0.0 and name in self.delta:
                gfx.text(surf, gfx.small, "{:+.2f}".format(self.delta[name]), (right, y + row_h - 22), AMBER,
                         "topright", 255 * min(1.0, self.delta_time))
            track = pygame.Rect(left, y + row_h - 8, right - left, 3)
            pygame.draw.rect(surf, (30, 41, 66), track)
            reach = math.tanh(value / gauge) * track.width / 2.0
            if abs(reach) >= 1.0:
                pygame.draw.rect(surf, CYAN if reach > 0 else AMBER,
                                 (min(track.centerx, track.centerx + reach), track.top, abs(reach), track.height))
            pygame.draw.line(surf, TEXT_DIM, (track.centerx, track.top - 3), (track.centerx, track.bottom + 2))
            y += row_h
        return y

    def update_lines(self):
        """The last training step, with the numbers plugged into the learning rule."""
        update = self.last_update
        if update is None:
            return None
        x1, x2 = update["point"]
        old, new = update["old"], update["new"]
        step = "{:g}·({:+d})".format(update["lr"], update["label"] - update["predicted"])
        head = "{} on {} ({:.1f}, {:.1f}): target {}, predicted {}".format(
            "Auto-train" if update["assist"] else "Retrained", "BOT" if update["label"] == 1 else "DRONE",
            x1, x2, update["label"], update["predicted"])
        return ((head, CYAN if update["assist"] else AMBER),
                ("w₁ = {} + {}·{:.1f} = {}".format(signed(old[0]), step, x1, signed(new[0])), TEXT),
                ("w₂ = {} + {}·{:.1f} = {}".format(signed(old[1]), step, x2, signed(new[1])), TEXT),
                ("b  = {} + {} = {}".format(signed(old[2]), step, signed(new[2])), TEXT))
