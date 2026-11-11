"""Hyperplane Heist: the game modes: campaign vaults, endless runs and the daily heist."""
import math
import random

import pygame

from .board import ENTER_TIME, FLOOR, LEARNING_RATE, PANEL, SNAP_TIME, Board, Unit
from .core import (WORLD_CENTRE, Motion, approach, bounce, clamp, clock_text, ease_out, ease_out_back, lerp,
                   min_linear_errors, random_start, ring_layout, sandwich_layout, score_text, separable_layout,
                   xor_layout)
from .gfx import (AMBER, BLACK, CYAN, GOLD, GREEN, PANEL_EDGE, PINK, RED, TEXT, TEXT_DIM, TEXT_FAINT, VIOLET,
                  WHITE, draw_arc, draw_nyx, draw_shield, draw_star, draw_vault_door, make_shutter, mix, panel,
                  scale_color, thick_line)
from .levels import LEVELS
from .save import daily_key, daily_number, daily_seed, today
from .scene import Scene
from .ui import CONTROLS_HELP, Attract, Menu, MenuItem, Typewriter, draw_dialogue

CONFIRM = (pygame.K_RETURN, pygame.K_KP_ENTER)

SECTORS = (("CITY BANK", CYAN), ("NEON CASINO", PINK), ("MUSEUM OF LIGHT", AMBER), ("DATA FORTRESS", GREEN),
           ("ORBITAL VAULT", VIOLET), ("QUANTUM ARCHIVE", (255, 130, 90)))
ROMAN = ("", " II", " III", " IV", " V", " VI", " VII", " VIII", " IX", " X")

PERKS = (
    ("shield", "SPARE SHIELD", "+1 shield right now (5 at most)."),
    ("chrono", "CHRONO CHIP", "+3 seconds on every wave timer."),
    ("trainer", "AUTO-TRAINER", "+3 charges. Press T to run one learning step on a unit you have wrong."),
    ("lens", "INSIGHT LENS", "Shows every unit's score z = w·x + b."),
    ("miner", "MARGIN MINER", "Doubles your margin bonus. Stacks."),
    ("stabilizer", "STABILIZER", "Moving vaults move 35% slower."),
    ("lucky", "LUCKY COIN", "+25% on every point you score."),
    ("insurance", "COMBO INSURANCE", "Your next mistake keeps the combo alive."),
)
PERK_INFO = {p[0]: p for p in PERKS}

COACH = (
    "Tilt the laser: ← → ↑ ↓ change w₁ and w₂. Or drag one of its glowing ends with the mouse.",
    "Now slide it: W / S change the bias b. Or drag the beam itself.",
    "Green bots on the SAFE side, red drones on the ALARM side? Press ENTER to lock it in.",
)
AFTER_ALARM = "The perceptron retrained on a unit you got wrong and moved your laser. Adapt, then lock in again."


def get_shutter(gfx):
    surf = getattr(gfx, "shutter", None)
    if surf is None:
        surf = make_shutter()
        gfx.shutter = surf
    return surf


def sector_info(wave):
    index = (wave - 1) // 5
    name, color = SECTORS[index % len(SECTORS)]
    return index, name + ROMAN[min(index // len(SECTORS), len(ROMAN) - 1)], color


def draw_perk_icon(surf, gfx, name, cx, cy, r, time):
    color = {"shield": GREEN, "chrono": CYAN, "trainer": CYAN, "lens": VIOLET, "miner": GREEN, "stabilizer": AMBER,
             "lucky": GOLD, "insurance": PINK}.get(name, CYAN)
    pygame.draw.circle(surf, scale_color(color, 0.18), (cx, cy), r)
    pygame.draw.circle(surf, color, (cx, cy), r, 2)
    k = r / 30.0
    if name == "shield":
        draw_shield(surf, cx, cy, 17 * k, color)
    elif name == "chrono":
        pygame.draw.circle(surf, color, (cx, cy), int(16 * k), 2)
        for angle, length in ((time * 2.0, 12), (time * 0.2, 8)):
            pygame.draw.line(surf, color, (cx, cy), (cx + math.cos(angle) * length * k, cy + math.sin(angle) * length * k), 2)
    elif name == "trainer":
        gfx.text(surf, gfx.mid, "Σ", (cx, cy), color, "center")
        draw_arc(surf, color, (cx, cy), 18 * k, time * 3, time * 3 + 4.5, 2)
    elif name == "lens":
        pygame.draw.circle(surf, color, (cx - 4 * k, cy - 4 * k), int(10 * k), 2)
        pygame.draw.line(surf, color, (cx + 3 * k, cy + 3 * k), (cx + 13 * k, cy + 13 * k), 3)
    elif name == "miner":
        for dx in (-7, 7):
            pygame.draw.line(surf, color, (cx + dx * k - 6 * k, cy + 14 * k), (cx + dx * k + 6 * k, cy - 14 * k), 2)
        pygame.draw.line(surf, WHITE, (cx - 4 * k, cy), (cx + 4 * k, cy), 2)
    elif name == "stabilizer":
        for i, rr in enumerate((16, 10)):
            draw_arc(surf, color, (cx, cy), rr * k, time * (2 - i * 3), time * (2 - i * 3) + 4.6, 2)
        pygame.draw.circle(surf, color, (cx, cy), int(3 * k))
    elif name == "lucky":
        pygame.draw.circle(surf, color, (cx, cy), int(14 * k))
        draw_star(surf, cx, cy, 8 * k, (90, 60, 10))
    elif name == "insurance":
        pygame.draw.circle(surf, color, (cx - 6 * k, cy), int(9 * k), 2)
        pygame.draw.circle(surf, color, (cx + 6 * k, cy), int(9 * k), 2)


class PlayScene(Scene):
    music = "game"

    def leave(self):
        self.board.set_cursor(None)

    def pause(self):
        board = self.board
        board.held.clear()
        board.drag = None
        board.end_gesture()
        board.set_cursor(None)
        self.audio.play("ui_select")
        self.app.push(PauseScene(self.app, self))

    def draw_alarm_flash(self, surf):
        board = self.board
        t = board.phase_t
        if board.phase == "alarm":
            alpha = 62.0 * math.exp(-4.0 * t) + 22.0 * (0.5 + 0.5 * math.sin(t * 12.0))
        elif board.phase == "snap" and not board.target_assist:
            alpha = 60.0 * max(0.0, 1.0 - t / (SNAP_TIME * 0.5))
        else:
            return
        if not self.profile.settings.get("flashes", True):
            alpha *= 0.3
        self.gfx.dim(surf, alpha, (255, 40, 64))

    def draw_keys(self, surf, y, rows):
        for row in rows:
            x = PANEL.left + 22
            for keys, label in row:
                x = self.gfx.key_hint(surf, x, y, keys, label)
            y += 26


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------
class CampaignScene(PlayScene):
    def __init__(self, app, index):
        super().__init__(app)
        self.index = index
        self.level = level = LEVELS[index]
        self.rng = random.Random()
        units = [Unit(x, y, label, motion, tag=tag) for x, y, label, motion, tag in level.units]
        start = level.start or random_start(self.rng, level.points(0.0))
        self.board = Board(app, params=start, locks=level.locks)
        self.board.skin = app.profile.skin
        self.board.show_paths = level.show_paths
        self.board.set_units(units, animate=True)
        self.board.controls_enabled = False
        self.alarms = 0
        self.attempts = 0
        self.heist_time = 0.0
        self.scan_good = 0
        self.target = None
        self.typer = Typewriter(level.intro)
        self.coach = 0 if index == 0 else None
        self.coach_note = None
        self.message = None
        self.result = None
        self.menu = None
        self.set_state("intro")

    def set_state(self, name):
        self.state = name
        self.state_t = 0.0
        self.once = set()

    def enter(self):
        self.audio.play("power_on")

    # ------------------------------------------------------------------ input
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state in ("won", "failed"):
                self.app.go_levels(self.index)
            elif self.state != "proving":
                self.pause()
            return True
        click = event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        confirm = event.type == pygame.KEYDOWN and event.key in CONFIRM + (pygame.K_SPACE,)
        if self.state == "intro":
            if confirm or click:
                if not self.typer.done:
                    self.typer.skip()
                else:
                    self.start_play()
                return True
            return False
        if self.state in ("won", "failed"):
            ready = 2.7 if self.state == "won" else 1.0
            if self.state_t < ready:
                if confirm or click:
                    self.state_t = ready
                    self.once.update({"win", "star0", "star1", "star2"})
                return True
            action = self.menu.handle_event(event) if self.menu else None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                action = "retry"
            if action:
                self.choose(action)
            return True
        if self.board.handle_event(event):
            return True
        if self.state == "play" and event.type == pygame.KEYDOWN:
            if event.key in CONFIRM:
                self.lock_in()
                return True
            if event.key == pygame.K_x:
                self.declare()
                return True
            if event.key == pygame.K_r:
                self.restart()
                return True
        return False

    def choose(self, action):
        if action == "next" and self.index + 1 < len(LEVELS):
            self.app.go_campaign(self.index + 1)
        elif action == "retry":
            self.restart()
        else:
            self.app.go_levels(self.index)

    def restart(self):
        self.app.go_campaign(self.index)

    # ------------------------------------------------------------- game rules
    def start_play(self):
        self.set_state("play")
        self.board.controls_enabled = True
        self.board.set_phase("control")
        self.audio.play("ui_select")

    def lock_in(self):
        self.attempts += 1
        self.scan_good = 0
        self.coach = None
        self.coach_note = None
        self.board.begin_scan()
        self.set_state("scan")
        self.profile.bump("lockins")

    def declare(self):
        """X: claim that no straight line can crack this vault."""
        if self.level.impossible:
            self.set_state("proving")
            self.board.set_phase("frozen")
            self.board.controls_enabled = False
            self.audio.play("proof")
            for u in self.board.units:
                x, y = self.board.unit_screen(u)
                self.board.particles.spark(x, y, VIOLET, count=16, speed=160, life=0.8)
            return
        self.alarms += 1
        self.audio.play("wrong")
        self.app.add_shake(0.5)
        self.message = ["A straight line CAN split this vault. Keep looking!", RED, 2.6]
        if self.alarms >= self.level.max_alarms:
            self.fail()

    def resolve_scan(self):
        board = self.board
        wrong = [u for u in board.units if u.verdict is False]
        if not self.level.impossible and len(wrong) <= self.level.allowed_errors:
            self.win()
            return
        self.alarms += 1
        self.profile.bump("alarms")
        self.target = self.rng.choice(wrong) if wrong else None
        if self.target is None:
            self.set_state("play")
            board.set_phase("control")
            return
        board.begin_alarm(self.target)
        self.set_state("alarm")

    def on_board_event(self, event):
        kind = event[0]
        board = self.board
        if kind == "changed":
            what = event[1]
            if self.coach == 0 and what in ("w1", "w2", "turn", "end", "draw"):
                self.coach = 1
            elif self.coach == 1 and what in ("b", "beam"):
                self.coach = 2
            self.coach_note = None
        elif kind == "judge":
            unit, ok = event[1], event[2]
            if ok:
                self.scan_good += 1
                self.audio.play_ok(self.scan_good)
                if unit.judged_dist is not None and unit.judged_dist < 0.05:
                    self.profile.unlock("close")
            else:
                self.audio.play("bad")
        elif kind == "scan_done":
            self.resolve_scan()
        elif kind == "alarm_done":
            self.set_state("snap")
            if self.target is not None:
                board.counter_attack(self.target)
        elif kind == "snap_done" and self.state == "snap":
            if self.alarms >= self.level.max_alarms:
                self.fail()
            else:
                self.set_state("play")
                board.set_phase("control")
                if self.index == 0 and self.alarms == 1:
                    self.coach_note = AFTER_ALARM

    def win(self, proof=False):
        board = self.board
        level = self.level
        self.set_state("won")
        board.set_phase("frozen")
        board.controls_enabled = False
        board.laser_override = (GREEN, 1.05)
        slack = None if proof else board.judged_margin()
        stars = 1
        if self.alarms <= 1:
            stars = 2
        if self.alarms == 0 and (proof or (slack is not None and slack >= level.margin_goal - 1e-9)):
            stars = 3
        p = self.profile
        gained, first = p.record_level(level.key, stars, self.heist_time, slack)
        xp = (100 if first else 20) + 40 * gained
        p.add_xp(xp)
        p.unlock("first_crack")
        if self.alarms == 0:
            p.unlock("ghost")
        if level.key == "and_gate":
            p.unlock("and_gate")
        if proof:
            p.unlock("minsky")
        if slack is not None and slack >= 2.0:
            p.unlock("wide")
        if p.total_stars() >= 15:
            p.unlock("stars_15")
        if p.campaign_cleared() >= len(LEVELS):
            p.unlock("campaign")
        if p.total_stars() >= 3 * len(LEVELS):
            p.unlock("stars_all")
        self.result = {"stars": stars, "slack": slack, "xp": xp, "gained": gained, "first": first, "proof": proof}
        self.audio.play("door")
        items = []
        if self.index + 1 < len(LEVELS):
            items.append(MenuItem("NEXT VAULT", "next", color=GREEN))
        items += [MenuItem("RETRY", "retry", color=CYAN), MenuItem("VAULTS", "levels", color=TEXT_DIM)]
        width, gap = 200, 16
        total = len(items) * width + (len(items) - 1) * gap
        self.menu = Menu(self.app, items, 600 - total // 2, 640, width, 44, gap, horizontal=True)

    def fail(self):
        self.set_state("failed")
        self.board.set_phase("frozen")
        self.board.controls_enabled = False
        self.audio.play("lose")
        items = [MenuItem("RETRY", "retry", color=CYAN), MenuItem("VAULTS", "levels", color=TEXT_DIM)]
        self.menu = Menu(self.app, items, 600 - 208, 486, 200, 44, 16, horizontal=True)

    # ----------------------------------------------------------------- update
    def update(self, dt):
        super().update(dt)
        self.state_t += dt
        board = self.board
        board.update(dt)
        if self.state in ("play", "scan", "alarm", "snap"):
            self.heist_time += dt
        if self.state == "intro":
            self.typer.update(dt, self.audio)
        if self.message:
            self.message[2] -= dt
            if self.message[2] <= 0:
                self.message = None
        board.banner = {"scan": ("LOCKING IN: SCANNING EVERY UNIT", CYAN),
                        "alarm": ("ALARM! BOUNDARY REJECTED", RED),
                        "snap": ("COUNTER-ATTACK: PERCEPTRON RETRAINED", AMBER)}.get(self.state)
        for event in board.take_events():
            self.on_board_event(event)
        if self.state == "proving" and self.state_t >= 1.8:
            self.win(proof=True)
        elif self.state == "won":
            if "win" not in self.once and self.state_t >= 1.3:
                self.once.add("win")
                self.audio.play("win")
            for k in range(self.result["stars"]):
                key = "star%d" % k
                if key not in self.once and self.state_t >= 1.85 + 0.25 * k:
                    self.once.add(key)
                    self.audio.play("star")
        elif self.state == "failed" and "slam" not in self.once and self.state_t >= 0.25:
            self.once.add("slam")
            self.app.add_shake(0.9)
        if self.menu:
            self.menu.update(dt)

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        board = self.board
        coaching = self.state == "play" and (self.coach is not None or self.coach_note)
        board.label_avoid = [self.COACH_RECT] if coaching else []
        board.draw(surf)
        self.draw_top(surf)
        y = board.draw_params(surf, PANEL.top + 14)
        self.draw_status(surf, y + 8)
        if self.state == "play" and (self.coach is not None or self.coach_note):
            self.draw_coach(surf)
        if self.message:
            self.draw_message(surf)
        self.draw_alarm_flash(surf)
        if self.state == "intro":
            self.draw_intro(surf)
        elif self.state == "proving":
            self.draw_proving(surf)
        elif self.state == "won":
            self.draw_won(surf)
        elif self.state == "failed":
            self.draw_failed(surf)

    def draw_top(self, surf):
        gfx = self.gfx
        gfx.text(surf, gfx.title, self.level.name.upper(), (FLOOR.left - 1, 12), TEXT)
        gfx.text(surf, gfx.small, "VAULT {} OF {}  ·  {}".format(self.index + 1, len(LEVELS), self.level.concept),
                 (FLOOR.left, 52), TEXT_DIM)
        right = PANEL.right
        gfx.text(surf, gfx.label, "HEIST TIME", (right, 16), TEXT_DIM, "topright")
        gfx.text(surf, gfx.mid, clock_text(self.heist_time), (right, 32), TEXT, "topright")
        right -= 150
        limit = self.level.max_alarms
        gfx.text(surf, gfx.label, "ALARMS {}/{}".format(self.alarms, limit), (right, 16),
                 RED if self.alarms else TEXT_DIM, "topright")
        pip_w, gap = 20, 5
        total = limit * pip_w + (limit - 1) * gap
        hot = self.state in ("alarm", "snap")
        for k in range(limit):
            rect = pygame.Rect(right - total + k * (pip_w + gap), 38, pip_w, 10)
            if k < self.alarms:
                glow = 0.5 + 0.5 * math.sin(self.time * 12.0) if hot and k == self.alarms - 1 else 0.0
                pygame.draw.rect(surf, mix(RED, WHITE, glow * 0.6), rect, border_radius=3)
            else:
                pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=3)

    def draw_status(self, surf, y):
        gfx = self.gfx
        board = self.board
        level = self.level
        left, right = PANEL.left + 22, PANEL.right - 22
        gfx.text(surf, gfx.label, "OBJECTIVE", (left, y), CYAN)
        best = self.profile.stars(level.key)
        gfx.text(surf, gfx.tiny, "BEST", (right - 64, y + 1), TEXT_FAINT, "topright")
        for k in range(3):
            draw_star(surf, right - 48 + k * 20, y + 6, 7, GOLD if k < best else TEXT_FAINT, k < best, 1)
        y += 20
        slack, errors = board.margin_now(shown=True)
        meets_margin = errors <= level.allowed_errors and slack is not None and slack >= level.margin_goal
        goals = (
            ("Crack it, or prove no line can (X)" if level.impossible else "Crack the vault", True),
            ("Trip at most 1 alarm", self.alarms <= 1),
            ("No alarms" if level.impossible else "No alarms, margin ≥ {:.2f}".format(level.margin_goal),
             self.alarms == 0 and (level.impossible or meets_margin)),
        )
        for k, (text, live) in enumerate(goals):
            for s in range(k + 1):
                draw_star(surf, left + 6 + s * 14, y + 8, 6, GOLD if live else TEXT_FAINT, live, 1)
            gfx.text(surf, gfx.small, text, (left + 50, y + 1), TEXT if live else TEXT_FAINT)
            y += 20
        y += 6
        w1, w2, b = board.brain.params
        bots = [u for u in board.units if u.shown_label == 1]
        drones = [u for u in board.units if u.shown_label == 0]
        bots_ok = sum(1 for u in bots if w1 * u.x + w2 * u.y + b > 0)
        drones_ok = sum(1 for u in drones if not w1 * u.x + w2 * u.y + b > 0)
        pygame.draw.circle(surf, GREEN, (left + 6, y + 8), 6)
        gfx.text(surf, gfx.small, "BOTS {}/{} safe".format(bots_ok, len(bots)), (left + 18, y),
                 GREEN if bots_ok == len(bots) else AMBER)
        pygame.draw.polygon(surf, RED, ((left + 232, y + 1), (left + 239, y + 14), (left + 225, y + 14)))
        gfx.text(surf, gfx.small, "DRONES {}/{} on alarm".format(drones_ok, len(drones)), (left + 246, y),
                 GREEN if drones_ok == len(drones) else AMBER)
        y += 22
        if errors == 0 and slack is not None:
            good = level.impossible or slack >= level.margin_goal
            text = "All set: ENTER to lock in.  Margin {:.2f}".format(slack)
            color = GREEN if good else AMBER
            if not good:
                text += " (goal {:.2f})".format(level.margin_goal)
        elif errors <= level.allowed_errors and not level.impossible:
            text, color = "{} error, {} allowed.  Margin {:.2f}".format(errors, level.allowed_errors, slack or 0.0), GREEN
        else:
            text, color = "{} unit{} on the wrong side".format(errors, "" if errors == 1 else "s"), AMBER
        gfx.text(surf, gfx.small, text, (left, y), color)
        y += 30
        gfx.text(surf, gfx.label, "COUNTER-ATTACK LOG", (left, y), CYAN)
        gfx.text(surf, gfx.tiny, "learning rate {:g}".format(LEARNING_RATE), (right, y + 1), TEXT_DIM, "topright")
        y += 19
        lines = board.update_lines() or (
            ("Lock in a wrong boundary and the perceptron", TEXT_DIM),
            ("retrains on one unit it got wrong:", TEXT_DIM),
            ("  w_i ← w_i + lr·(target - predicted)·x_i", TEXT),
            ("  b   ← b   + lr·(target - predicted)", TEXT))
        for line, color in lines:
            gfx.text(surf, gfx.small, line, (left, y), color)
            y += 17
        self.draw_keys(surf, PANEL.bottom - 58, (
            ((["ENTER"], "lock in"), (["X"], "impossible?"), (["F"], "flip"), (["R"], "restart")),
            ((["Q", "E"], "turn"), (["ESC"], "pause"), ([], "mouse: drag ends / beam")),
        ))

    COACH_RECT = pygame.Rect(FLOOR.left + 16, FLOOR.top + 150, 330, 104)

    def draw_coach(self, surf):
        gfx = self.gfx
        text = self.coach_note or COACH[self.coach]
        rect = self.COACH_RECT
        surf.blit(gfx.plate(rect.size, (8, 10, 22, 232), 10), rect)
        pygame.draw.rect(surf, AMBER if self.coach_note else CYAN, rect, 1, border_radius=10)
        draw_nyx(surf, rect.left + 32, rect.top + 36, 20, self.time, talking=(self.time % 3.0) < 1.2)
        gfx.text(surf, gfx.label, "NYX", (rect.left + 20, rect.top + 70), CYAN)
        gfx.paragraph(surf, gfx.small, text, rect.left + 66, rect.top + 12, rect.width - 80, TEXT, gap=4)

    def draw_message(self, surf):
        text, color, life = self.message
        gfx = self.gfx
        rect = pygame.Rect(0, 0, gfx.body.size(text)[0] + 36, 38)
        rect.center = (FLOOR.centerx, FLOOR.bottom - 40)
        alpha = 255 * min(1.0, life / 0.4)
        surf.blit(gfx.plate(rect.size, (24, 8, 14, 230), 10), rect)
        pygame.draw.rect(surf, color, rect, 2, border_radius=10)
        gfx.text(surf, gfx.body, text, rect.center, color, "center", alpha)

    def draw_goal_row(self, surf, y, centre_x):
        gfx = self.gfx
        level = self.level
        goals = ("crack it", "≤ 1 alarm",
                 "no alarms" if level.impossible else "no alarms, margin ≥ {:.2f}".format(level.margin_goal))
        widths = [k * 14 + 18 + gfx.small.size(text)[0] for k, text in enumerate(goals)]
        x = centre_x - (sum(widths) + 28 * 2) / 2
        for k, text in enumerate(goals):
            for s in range(k + 1):
                draw_star(surf, x + 6 + s * 14, y + 8, 6, GOLD, True, 1)
            gfx.text(surf, gfx.small, text, (x + (k + 1) * 14 + 4, y + 1), TEXT)
            x += widths[k] + 28

    def draw_intro(self, surf):
        gfx = self.gfx
        gfx.dim(surf, 165)
        card = pygame.Rect(0, 0, 800, 448)
        card.center = (600, 372)
        panel(surf, card, (9, 12, 24), mix(PANEL_EDGE, CYAN, 0.5), 14, 2)
        gfx.text(surf, gfx.label, "VAULT {} OF {}".format(self.index + 1, len(LEVELS)), (card.centerx, card.top + 20),
                 AMBER, "midtop")
        gfx.draw_banner(surf, self.level.name.upper(), (card.centerx, card.top + 74), WHITE, CYAN, gfx.big)
        gfx.text(surf, gfx.body, self.level.concept, (card.centerx, card.top + 110), TEXT_DIM, "midtop")
        box = pygame.Rect(card.left + 24, card.top + 142, card.width - 48, 136)
        draw_dialogue(surf, gfx, box, "NYX", self.typer, self.time, hint="")
        y = box.bottom + 16
        gfx.text(surf, gfx.label, "TIP", (card.left + 30, y + 1), AMBER)
        y = gfx.paragraph(surf, gfx.small, self.level.tip, card.left + 64, y, card.width - 100, TEXT, gap=4)
        self.draw_goal_row(surf, max(y + 8, card.bottom - 76), card.centerx)
        pulse = 0.65 + 0.35 * math.sin(self.time * 4.0)
        label = "ENTER  start the heist" if self.typer.done else "ENTER  skip"
        gfx.text(surf, gfx.mid, label, (card.centerx, card.bottom - 30), CYAN, "center", 255 * pulse)

    def draw_proving(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 120 * clamp(t / 0.4, 0.0, 1.0), (20, 6, 40))
        scale = ease_out_back(clamp(t / 0.5, 0.0, 1.0))
        if scale > 0.05:
            image, glow = gfx.banner("NOT LINEARLY SEPARABLE", (240, 230, 255), VIOLET, gfx.big)
            w, h = max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale))
            img = pygame.transform.smoothscale(image, (w, h))
            surf.blit(glow, glow.get_rect(center=(600, 330)), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(img, img.get_rect(center=(600, 330)))
        if t > 0.6:
            gfx.text(surf, gfx.title, "Q.E.D.", (600, 396), GOLD, "center", 255 * clamp((t - 0.6) / 0.3, 0, 1))

    def draw_won(self, surf):
        gfx = self.gfx
        t = self.state_t
        result = self.result
        fade = clamp((t - 0.3) / 0.5, 0.0, 1.0)
        if fade <= 0.0:
            return
        gfx.dim(surf, 214 * fade, (3, 10, 9))
        cx, cy = 600, 196
        unlocked = clamp((t - 1.35) / 0.35, 0.0, 1.0)
        if unlocked > 0.0:
            gfx.fx.fill(BLACK)
            for reach, level in ((620, 0.03), (420, 0.055), (260, 0.085)):
                ray = scale_color(GREEN, level * unlocked)
                for k in range(12):
                    angle = t * 0.2 + k * math.tau / 12
                    pygame.draw.polygon(gfx.fx, ray, ((cx, cy),
                                                      (cx + math.cos(angle - 0.05) * reach, cy + math.sin(angle - 0.05) * reach),
                                                      (cx + math.cos(angle + 0.05) * reach, cy + math.sin(angle + 0.05) * reach)))
            surf.blit(gfx.fx, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        draw_vault_door(surf, cx, cy, t, unlocked, radius=100)
        reveal = clamp((t - 1.0) / 0.5, 0.0, 1.0)
        title = "PROVEN IMPOSSIBLE" if result["proof"] else "VAULT CRACKED"
        if reveal > 0.0:
            image, glow = gfx.banner(title, (224, 255, 238), GREEN)
            rect = image.get_rect(center=(cx, 372))
            shown = int((rect.width + 80) * reveal)
            surf.set_clip(pygame.Rect(rect.left - 40, rect.top - 40, shown, rect.height + 80))
            surf.blit(glow, glow.get_rect(center=rect.center), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(image, rect)
            surf.set_clip(None)
            if reveal < 1.0:
                pygame.draw.rect(surf, WHITE, (rect.left - 42 + shown, rect.top + 6, 4, rect.height - 12))
        for k in range(3):
            start = 1.75 + 0.25 * k
            if t < start:
                continue
            pop = ease_out_back(clamp((t - start) / 0.3, 0.0, 1.0))
            earned = k < result["stars"]
            x = cx + (k - 1) * 74
            if earned:
                gfx.add_glow(surf, x, 450, 40, GOLD, 0.45 * pop)
            draw_star(surf, x, 450, 26 * pop, GOLD if earned else (60, 66, 84), earned, 3)

        def fade_in(start):
            return 255 * clamp((t - start) / 0.4, 0.0, 1.0)

        stats = "TIME {}     ALARMS {}/{}".format(clock_text(self.heist_time), self.alarms, self.level.max_alarms)
        if result["slack"] is not None:
            stats += "     MARGIN {:.2f}".format(result["slack"])
        gfx.text(surf, gfx.mid, stats, (cx, 506), TEXT, "center", fade_in(2.3))
        xp = "+{} XP".format(result["xp"])
        if result["gained"] and not result["first"]:
            xp += "   NEW STAR RECORD"
        gfx.text(surf, gfx.body, xp, (cx, 538), GOLD, "center", fade_in(2.45))
        text = self.level.win_text
        if text:
            y = 566
            for line in gfx.wrap(gfx.small, text, 820):
                gfx.text(surf, gfx.small, line, (cx, y), TEXT_DIM, "midtop", fade_in(2.55))
                y += 18
        if t >= 2.7 and self.menu:
            self.menu.draw(surf, gfx, self.time)

    def draw_failed(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 120 * clamp(t / 0.3, 0.0, 1.0), (40, 0, 9))
        surf.blit(get_shutter(gfx), (0, int(lerp(-720, 0, bounce(t / 0.7)))))
        if t < 0.8:
            return
        box = pygame.Rect(0, 0, 720, 330)
        box.center = (600, 380)
        surf.blit(gfx.plate(box.size, (12, 6, 9, 240), 14), box)
        pygame.draw.rect(surf, RED, box, 2, border_radius=14)
        gfx.draw_banner(surf, "VAULT LOCKDOWN", (600, 272), (255, 226, 231), RED, gfx.big)
        gfx.text(surf, gfx.body, "{} alarms tripped. The perceptron out-learned you.".format(self.alarms),
                 (600, 320), TEXT, "center")
        gfx.text(surf, gfx.label, "TIP", (box.left + 40, 352), AMBER)
        gfx.paragraph(surf, gfx.small, self.level.tip, box.left + 76, 351, box.width - 116, TEXT_DIM, gap=4)
        if self.menu:
            self.menu.draw(surf, gfx, self.time)


# ---------------------------------------------------------------------------
# Endless
# ---------------------------------------------------------------------------
class WavePlan:
    def __init__(self, number, units, separable, line, modifiers, timer, boss):
        self.number = number
        self.units = units
        self.separable = separable
        self.line = line
        self.modifiers = modifiers
        self.timer = timer
        self.boss = boss


def plan_wave(n, rng, perks):
    """Wave n of an endless run: units, rules and timer.  Every 5th wave is a boss."""
    boss = n % 5 == 0
    timer = max(7.0, 15.0 - 0.45 * (n - 1)) + 3.0 * perks.get("chrono", 0)
    count = min(8, 3 + n // 2)
    gap = max(0.6, 2.4 - 0.12 * (n - 1))
    spread = 1.0 + 0.03 * n
    mods = []
    motion = None
    disguise = 0
    line = None
    if boss:
        timer += 4.0
        mods.append("BOSS")
        kind = rng.choice(("xor", "ring", "sandwich", "split", "split"))
        if kind == "xor":
            points = xor_layout(rng, 2 if n < 15 else 3)
        elif kind == "ring":
            points = ring_layout(rng, 3, 6 if n < 15 else 8)
        elif kind == "sandwich":
            points = sandwich_layout(rng, 4, 6)
        else:
            points, line = separable_layout(rng, count, count, max(0.8, gap), spread, clusters=2)
        errors, best = min_linear_errors(points)
        separable = errors == 0
        if separable and line is None:
            line = best
    else:
        squeeze = n >= 8 and rng.random() < 0.35
        drift = n >= 3 and rng.random() < min(0.65, 0.15 + 0.05 * n)
        spin = drift and n >= 7 and rng.random() < 0.5
        if squeeze:
            gap = max(0.45, gap * 0.6)
            mods.append("SQUEEZE")
        if spin:
            points, line = separable_layout(rng, count, count, gap, spread, radius=3.9, centred=True)
            omega = min(0.32, 0.1 + 0.012 * n) * rng.choice((-1.0, 1.0))
            motion = Motion("spin", centre=WORLD_CENTRE, omega=omega)
            mods.append("SPIN")
        elif drift:
            amplitude = min(1.5, 0.5 + 0.06 * n)
            angle = rng.uniform(0.0, math.pi)
            points, line = separable_layout(rng, count, count, gap, spread, box=(0.7 + amplitude, 9.3 - amplitude))
            motion = Motion("sway", direction=(math.cos(angle), math.sin(angle)), amplitude=amplitude,
                            period=rng.uniform(5.0, 8.0), phase=rng.uniform(0.0, math.tau))
            mods.append("DRIFT")
        else:
            points, line = separable_layout(rng, count, count, gap, spread)
        separable = True
        if n >= 6 and rng.random() < min(0.5, 0.1 + 0.03 * n):
            disguise = 1 if n < 12 else 2
            mods.append("IMPOSTERS")
    units = [Unit(x, y, label, motion) for x, y, label in points]
    if disguise:
        drones = [u for u in units if u.label == 0]
        for u in rng.sample(drones, min(disguise, len(drones))):
            u.disguised = True
    return WavePlan(n, units, separable, line, mods, timer, boss)


class EndlessScene(PlayScene):
    def __init__(self, app, daily=False, seed=None):
        super().__init__(app)
        self.daily = daily
        self.date = today()
        if seed is None:
            seed = daily_seed(self.date) if daily else random.randrange(1 << 30)
        self.rng = random.Random(seed)
        self.max_waves = 10 if daily else None
        self.board = Board(app, theme=SECTORS[0][1])
        self.board.skin = app.profile.skin
        self.board.show_tags = False
        self.board.set_params(*random_start(self.rng, []))
        self.wave = 0
        self.score = 0
        self.shown_score = 0.0
        self.shields = 3
        self.max_shields = 5
        self.combo = 0
        self.best_combo = 0
        self.perks = {}
        self.trainer = 0
        self.insurance = 0
        self.stats = {"correct": 0, "wrong": 0, "proofs": 0, "perfect": 0, "time": 0.0, "cleared": 0}
        self.plan = None
        self.offer = []
        self.perk_focus = 1
        self.timer = self.timer_max = 1.0
        self.enter_time = 1.0
        self.early_bonus = 0
        self.shield_flash = 0.0
        self.message = None
        self.first_card = True
        self.boss_beaten = False
        self.state = None
        self.state_t = 0.0
        self.once = set()
        self.next_wave()

    def set_state(self, name):
        self.state = name
        self.state_t = 0.0
        self.once = set()

    # ------------------------------------------------------------ wave flow
    def next_wave(self):
        self.wave += 1
        if self.max_waves and self.wave > self.max_waves:
            self.wave = self.max_waves
            self.complete()
            return
        for target, aid in ((5, "wave5"), (10, "wave10"), (20, "wave20")):
            if self.wave >= target and not self.daily:
                self.profile.unlock(aid)
        index, _, color = sector_info(self.wave)
        self.audio.set_tempo(116 + 3 * min(6, index))
        if (self.wave - 1) % 5 == 0:
            self.board.set_theme(color)
            self.set_state("sector")
            self.audio.play("power_on")
        else:
            self.start_wave()

    def start_wave(self):
        self.plan = plan_wave(self.wave, self.rng, self.perks)
        board = self.board
        board.set_units(self.plan.units, animate=True)
        board.motion_speed = 0.65 ** self.perks.get("stabilizer", 0)
        board.show_z = "lens" in self.perks
        board.laser_override = None
        board.set_phase("control")
        board.controls_enabled = True
        self.enter_time = ENTER_TIME + 0.06 * max(0, len(self.plan.units) - 1) + 0.1
        for u in self.plan.units:
            if u.disguised:
                u.reveal_at = self.enter_time + max(2.5, self.plan.timer * 0.45)
        self.timer = self.timer_max = self.plan.timer
        self.early_bonus = 0
        self.set_state("enter")
        self.audio.play("teleport")

    def lock_in(self, early):
        if self.state != "play":
            return
        self.early_bonus = int(round(self.timer * 12)) if early and self.timer > 0.5 else 0
        self.board.begin_scan()
        self.set_state("scan")
        self.profile.bump("lockins")

    def leave_wave(self):
        self.set_state("exit")
        self.board.set_phase("frozen")
        self.board.controls_enabled = False
        self.board.dismiss_units()

    def complete(self):
        self.set_state("complete")
        self.board.set_phase("frozen")
        self.board.controls_enabled = False
        self.audio.play("win")

    def game_over(self):
        self.set_state("gameover")
        self.board.set_phase("frozen")
        self.board.controls_enabled = False
        self.audio.play("lose")

    def to_results(self):
        summary = {"daily": self.daily, "score": self.score, "wave": self.wave,
                   "cleared": self.stats["cleared"], "correct": self.stats["correct"], "wrong": self.stats["wrong"],
                   "best_combo": self.best_combo, "proofs": self.stats["proofs"], "perfect": self.stats["perfect"],
                   "time": self.stats["time"], "completed": self.state == "complete",
                   "date_key": daily_key(self.date), "daily_no": daily_number(self.date)}
        self.app.replace(ResultsScene(self.app, summary))

    # -------------------------------------------------------------- scoring
    def mult(self):
        return 1 + min(7, self.combo // 10)

    def lucky(self):
        return 1.0 + 0.25 * self.perks.get("lucky", 0)

    def award(self, points, x, y, label=None, color=GOLD, size="mid", delay=0.0):
        gained = int(round(points * self.lucky()))
        self.score += gained
        self.board.popups.add(label.format(gained) if label else "+{}".format(gained), x, y, color, size, 1.2,
                              42, delay)
        for target, aid in ((10000, "score10k"), (50000, "score50k")):
            if self.score >= target and not self.daily:
                self.profile.unlock(aid)
        return gained

    def lose_shield(self):
        self.shields = max(0, self.shields - 1)
        self.shield_flash = 1.0
        self.audio.play("shield")
        self.app.add_shake(0.8)

    def break_combo(self):
        if self.insurance > 0 and self.combo > 0:
            self.insurance -= 1
            self.board.popups.add("COMBO INSURED", FLOOR.centerx, FLOOR.top + 120, PINK, "label", 1.4)
            return
        self.combo = 0

    # ------------------------------------------------------------- actions
    def declare(self):
        """X: claim that no straight line can split this wave."""
        if self.state != "play":
            return
        board = self.board
        board.set_phase("frozen")
        board.controls_enabled = False
        self.profile.bump("x_calls")
        self.boss_beaten = not self.plan.separable
        if not self.plan.separable:
            self.stats["proofs"] += 1
            self.profile.unlock("proof")
            self.award(500 + 50 * self.wave, FLOOR.centerx, FLOOR.centery + 40, "PROOF +{}", VIOLET, "title")
            if self.shields < self.max_shields:
                self.shields += 1
                board.popups.add("+1 SHIELD", FLOOR.centerx, FLOOR.centery + 90, GREEN, "mid", 1.4, 30, 0.3)
            self.stats["cleared"] += 1
            self.audio.play("proof")
            for u in board.units:
                x, y = board.unit_screen(u)
                board.particles.spark(x, y, VIOLET, count=14, speed=170, life=0.8)
            self.set_state("proof")
        else:
            self.audio.play("wrong")
            self.lose_shield()
            self.break_combo()
            if self.plan.line is not None:
                board.show_ghost(self.plan.line, 2.4)
            self.message = ["WRONG: a straight line could split this one (dashed)", RED, 2.4]
            self.set_state("wrong_x")

    def auto_train(self):
        if self.state != "play":
            return
        board = self.board
        if self.trainer <= 0:
            self.audio.play("ui_back")
            return
        w1, w2, b = board.brain.params
        wrong = [u for u in board.active_units() if (1 if w1 * u.x + w2 * u.y + b > 0 else 0) != u.shown_label]
        if not wrong:
            board.popups.add("NOTHING TO FIX", FLOOR.centerx, FLOOR.top + 120, CYAN, "label", 1.0)
            self.audio.play("ui_back")
            return
        unit = self.rng.choice(wrong)
        self.trainer -= 1
        self.profile.unlock("trainer")
        board.counter_attack(unit, unit.x, unit.y, assist=True, label=unit.shown_label)
        self.set_state("assist")

    def offer_perks(self):
        pool = [p[0] for p in PERKS if not (p[0] == "lens" and "lens" in self.perks)
                and not (p[0] == "shield" and self.shields >= self.max_shields)]
        self.offer = self.rng.sample(pool, 3)
        self.perk_focus = 1
        self.set_state("perk")
        self.audio.play("perk")

    def take_perk(self, name):
        self.perks[name] = self.perks.get(name, 0) + 1
        if name == "shield":
            self.shields = min(self.max_shields, self.shields + 1)
        elif name == "trainer":
            self.trainer += 3
        elif name == "insurance":
            self.insurance += 1
        self.audio.play("levelup")
        self.next_wave()

    # ------------------------------------------------------------------ input
    def perk_rects(self):
        width, height, gap = 300, 270, 30
        left = 600 - (3 * width + 2 * gap) // 2
        return [pygame.Rect(left + i * (width + gap), 236, width, height) for i in range(3)]

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state in ("gameover", "complete"):
                self.to_results()
            else:
                self.pause()
            return True
        click = event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        confirm = event.type == pygame.KEYDOWN and event.key in CONFIRM
        if self.state == "sector":
            if (confirm or click or (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE)) \
                    and self.state_t > 0.4:
                self.first_card = False
                self.start_wave()
            return True
        if self.state == "perk":
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.perk_focus = (self.perk_focus - 1) % 3
                    self.audio.play("ui_move")
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.perk_focus = (self.perk_focus + 1) % 3
                    self.audio.play("ui_move")
                elif event.key in CONFIRM + (pygame.K_SPACE,) and self.state_t > 0.5:
                    self.take_perk(self.offer[self.perk_focus])
            elif event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(self.perk_rects()):
                    if rect.collidepoint(event.pos) and i != self.perk_focus:
                        self.perk_focus = i
                        self.audio.play("ui_move")
            elif click and self.state_t > 0.5:
                for i, rect in enumerate(self.perk_rects()):
                    if rect.collidepoint(event.pos):
                        self.take_perk(self.offer[i])
            return True
        if self.state in ("gameover", "complete"):
            if (confirm or click) and self.state_t > 1.0:
                self.to_results()
            return True
        if self.board.handle_event(event):
            return True
        if self.state == "play" and event.type == pygame.KEYDOWN:
            if event.key in CONFIRM:
                self.lock_in(early=True)
                return True
            if event.key == pygame.K_x:
                self.declare()
                return True
            if event.key == pygame.K_t:
                self.auto_train()
                return True
        return False

    # ----------------------------------------------------------------- events
    def on_board_event(self, event):
        kind = event[0]
        board = self.board
        if kind == "judge":
            unit, ok = event[1], event[2]
            x, y = board.unit_screen(unit)
            if ok:
                self.combo += 1
                self.best_combo = max(self.best_combo, self.combo)
                self.stats["correct"] += 1
                self.profile.bump("correct")
                self.award(25 * self.mult(), x, y - 26)
                self.audio.play_ok(self.combo)
                if self.combo in (10, 20, 30, 40, 50, 60, 70):
                    board.popups.add("COMBO ×{}".format(self.mult()), x, y - 56, PINK, "label", 1.2)
                if self.combo >= 20:
                    self.profile.unlock("combo20")
                if self.combo >= 50:
                    self.profile.unlock("combo50")
                if unit.judged_dist is not None and unit.judged_dist < 0.05:
                    self.profile.unlock("close")
                    board.popups.add("CLOSE SHAVE!", x, y - 56, AMBER, "label", 1.2)
            else:
                self.stats["wrong"] += 1
                self.break_combo()
                self.audio.play("bad")
                board.popups.add("✗", x, y - 26, RED, "title", 0.9)
        elif kind == "scan_done":
            wrong = [u for u in board.units if u.verdict is False]
            if not wrong:
                self.boss_beaten = self.plan.boss
                self.perfect_wave()
            else:
                self.boss_beaten = False
                self.lose_shield()
                if not self.plan.separable:
                    self.message = ["No line could split that boss vault. Next time press X!", VIOLET, 3.0]
                target = self.rng.choice(wrong)
                board.begin_alarm(target)
                self.set_state("alarm")
        elif kind == "alarm_done":
            target = board.target
            self.set_state("snap")
            board.counter_attack(target)
        elif kind == "snap_done":
            if self.state == "assist":
                self.set_state("play")
                board.set_phase("control")
                if self.timer <= 0.0:
                    self.lock_in(early=False)
            elif self.state == "snap":
                if self.shields <= 0:
                    self.game_over()
                else:
                    self.leave_wave()
        elif kind == "units_gone" and self.state == "exit":
            if self.max_waves and self.wave >= self.max_waves:
                self.complete()
            elif self.plan is not None and self.plan.boss:
                self.offer_perks()
            else:
                self.next_wave()

    def perfect_wave(self):
        board = self.board
        self.stats["perfect"] += 1
        self.stats["cleared"] += 1
        cx, cy = FLOOR.centerx, FLOOR.centery
        self.award(100 + 20 * self.wave, cx, cy - 40, "PERFECT WAVE +{}", GREEN, "title")
        slack = board.judged_margin() or 0.0
        if slack >= 2.0:
            self.profile.unlock("wide")
        bonus = min(300, int(slack * 120)) * (1 + self.perks.get("miner", 0))
        if bonus > 0:
            self.award(bonus, cx, cy + 4, "MARGIN {:.2f}".format(slack) + "  +{}", CYAN, "mid", 0.25)
        if self.early_bonus:
            self.award(self.early_bonus, cx, cy + 40, "SPEED +{}", AMBER, "mid", 0.5)
        board.laser_override = (GREEN, 1.05)
        self.audio.play("wave_clear")
        self.set_state("celebrate")

    # ----------------------------------------------------------------- update
    def update(self, dt):
        super().update(dt)
        self.state_t += dt
        board = self.board
        board.update(dt)
        self.shown_score = approach(self.shown_score, self.score, 8.0, dt)
        if abs(self.shown_score - self.score) < 1.0:
            self.shown_score = float(self.score)
        self.shield_flash = max(0.0, self.shield_flash - dt * 1.5)
        if self.message:
            self.message[2] -= dt
            if self.message[2] <= 0:
                self.message = None
        state = self.state
        if state in ("enter", "play", "scan", "alarm", "snap", "assist", "celebrate", "exit"):
            self.stats["time"] += dt
        if state == "sector":
            if self.state_t >= (5.0 if self.first_card else 2.6):
                self.first_card = False
                self.start_wave()
        elif state == "enter":
            if self.state_t >= self.enter_time:
                self.set_state("play")
        elif state in ("play", "assist"):
            before = self.timer
            self.timer -= dt
            for mark in (3, 2, 1):
                if before > mark >= self.timer:
                    self.audio.play("count")
            if self.timer <= 0.0 and state == "play":
                self.lock_in(early=False)
        elif state == "celebrate" and self.state_t >= 1.0:
            self.leave_wave()
        elif state == "proof" and self.state_t >= 1.8:
            self.leave_wave()
        elif state == "wrong_x" and self.state_t >= 2.2:
            if self.shields <= 0:
                self.game_over()
            else:
                self.leave_wave()
        elif state == "gameover":
            if "slam" not in self.once and self.state_t >= 0.25:
                self.once.add("slam")
                self.app.add_shake(0.9)
            if self.state_t >= 3.2:
                self.to_results()
        elif state == "complete" and self.state_t >= 3.0:
            self.to_results()
        board.banner = {"scan": ("SCANNING", CYAN), "alarm": ("ALARM! SHIELD LOST", RED),
                        "snap": ("COUNTER-ATTACK: PERCEPTRON RETRAINED", AMBER),
                        "assist": ("AUTO-TRAINER: ONE LEARNING STEP", CYAN)}.get(state)
        for event in board.take_events():
            self.on_board_event(event)
        index = (self.wave - 1) // 5
        intensity = 1
        if state in ("play", "assist", "scan"):
            intensity = 1 + (1 if index >= 1 or self.combo >= 10 else 0)
            if self.timer < self.timer_max * 0.35 or self.combo >= 30:
                intensity = 3
        self.audio.set_intensity(intensity)

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        board = self.board
        board.draw(surf)
        self.draw_top(surf)
        self.draw_timer(surf)
        self.draw_chips(surf)
        y = board.draw_params(surf, PANEL.top + 14, compact=True)
        self.draw_side(surf, y + 8)
        if self.message:
            self.draw_message(surf)
        self.draw_alarm_flash(surf)
        state = self.state
        if state == "sector":
            self.draw_sector_card(surf)
        elif state == "perk":
            self.draw_perks(surf)
        elif state == "proof":
            self.draw_proof(surf)
        elif state == "gameover":
            self.draw_gameover(surf)
        elif state == "complete":
            self.draw_complete(surf)

    def draw_top(self, surf):
        gfx = self.gfx
        index, name, color = sector_info(self.wave)
        title = "WAVE {}".format(self.wave) + (" / {}".format(self.max_waves) if self.max_waves else "")
        if self.daily:
            title = "DAILY #{}  ·  ".format(daily_number(self.date)) + title
        gfx.text(surf, gfx.title, title, (FLOOR.left - 1, 12), TEXT)
        gfx.text(surf, gfx.small, "SECTOR {}  ·  {}".format(index + 1, name), (FLOOR.left, 52), color)
        right = PANEL.right
        gfx.text(surf, gfx.value, score_text(self.shown_score), (right, 10), GOLD, "topright")
        best = self.profile.daily_record() if self.daily else None
        best_score = (best or {}).get("score", 0) if self.daily else self.profile.endless_best
        gfx.text(surf, gfx.tiny, "BEST " + score_text(best_score), (right, 46), TEXT_DIM, "topright")
        x = right - 250
        gfx.text(surf, gfx.label, "SHIELDS", (x, 16), RED if self.shield_flash > 0 else TEXT_DIM, "topright")
        for k in range(self.max_shields):
            cx = x - 112 + k * 23
            filled = k < self.shields
            flash = self.shield_flash if k == self.shields else 0.0
            if filled:
                draw_shield(surf, cx, 46, 9, GREEN)
            else:
                draw_shield(surf, cx, 46, 9, mix(PANEL_EDGE, RED, flash), False)

    def draw_timer(self, surf):
        if self.state not in ("play", "assist", "scan", "enter"):
            return
        gfx = self.gfx
        frac = clamp(self.timer / self.timer_max, 0.0, 1.0) if self.state != "enter" else 1.0
        color = mix(RED, AMBER, frac * 2.0) if frac < 0.5 else mix(AMBER, sector_info(self.wave)[2], (frac - 0.5) * 2)
        bar = pygame.Rect(FLOOR.left, FLOOR.top + 1, int(FLOOR.width * frac), 5)
        pygame.draw.rect(surf, color, bar)
        text = "{:.1f}s".format(max(0.0, self.timer))
        rect = pygame.Rect(0, 0, 74, 30)
        rect.topright = (FLOOR.right - 10, FLOOR.top + 12)
        surf.blit(gfx.plate(rect.size), rect)
        hot = frac < 0.3 and self.state == "play"
        pulse = 0.5 + 0.5 * math.sin(self.time * 12.0) if hot else 0.0
        gfx.text(surf, gfx.mid, text, rect.center, mix(color, WHITE, pulse * 0.5), "center")

    def draw_chips(self, surf):
        if not self.plan or self.state in ("sector", "perk"):
            return
        gfx = self.gfx
        x = FLOOR.left + 12
        y = FLOOR.bottom - 34
        colors = {"BOSS": VIOLET, "DRIFT": CYAN, "SPIN": CYAN, "SQUEEZE": AMBER, "IMPOSTERS": RED}
        for name in self.plan.modifiers:
            width = gfx.label.size(name)[0] + 18
            rect = pygame.Rect(x, y, width, 22)
            surf.blit(gfx.plate(rect.size, (8, 10, 20, 220), 6), rect)
            pygame.draw.rect(surf, colors.get(name, TEXT), rect, 1, border_radius=6)
            gfx.text(surf, gfx.label, name, rect.center, colors.get(name, TEXT), "center")
            x += width + 8

    def draw_side(self, surf, y):
        gfx = self.gfx
        board = self.board
        left, right = PANEL.left + 22, PANEL.right - 22
        gfx.text(surf, gfx.label, "COMBO", (left, y), CYAN)
        gfx.text(surf, gfx.tiny, "BEST {}".format(self.best_combo), (right, y + 1), TEXT_FAINT, "topright")
        y += 16
        gfx.text(surf, gfx.value, str(self.combo), (left, y), WHITE if self.combo else TEXT_FAINT)
        mult = self.mult()
        gfx.text(surf, gfx.value, "×{}".format(mult), (right, y), PINK if mult > 1 else TEXT_FAINT, "topright")
        y += 38
        track = pygame.Rect(left, y, right - left, 6)
        pygame.draw.rect(surf, (30, 41, 66), track, border_radius=3)
        progress = (self.combo % 10) / 10.0 if mult < 8 else 1.0
        pygame.draw.rect(surf, PINK, (track.left, track.top, int(track.width * progress), track.height),
                         border_radius=3)
        y += 18
        gfx.text(surf, gfx.label, "PERKS", (left, y), CYAN)
        if self.insurance:
            gfx.text(surf, gfx.tiny, "insured mistakes: {}".format(self.insurance), (right, y + 1), PINK, "topright")
        y += 20
        if not self.perks:
            gfx.paragraph(surf, gfx.small, "None yet. Beat a boss vault (every 5th wave) to choose one.", left, y,
                          right - left, TEXT_FAINT, gap=3)
            y += 40
        else:
            col = 0
            for name in PERK_INFO:
                if name not in self.perks:
                    continue
                x = left + col * 218
                draw_perk_icon(surf, gfx, name, x + 11, y + 10, 11, self.time)
                label = PERK_INFO[name][1]
                if name == "trainer":
                    label += " ({} left)".format(self.trainer)
                elif self.perks[name] > 1:
                    label += " ×{}".format(self.perks[name])
                gfx.text(surf, gfx.tiny, label, (x + 28, y + 4), TEXT)
                col += 1
                if col == 2:
                    col = 0
                    y += 24
            if col:
                y += 24
            y += 4
        gfx.text(surf, gfx.label, "THIS WAVE", (left, y), CYAN)
        y += 19
        if self.plan and self.state not in ("sector", "perk"):
            bots = sum(1 for u in board.units if u.shown_label == 1)
            gfx.text(surf, gfx.small, "{} bots · {} drones".format(bots, len(board.units) - bots), (left, y), TEXT_DIM)
            y += 19
            errors = board.errors_now(shown=True)
            if self.state in ("play", "enter"):
                if errors == 0:
                    bonus = int(round(self.timer * 12))
                    text, color = "All set: ENTER to scan now (+{} speed)".format(bonus), GREEN
                else:
                    text, color = "{} unit{} on the wrong side".format(errors, "" if errors == 1 else "s"), AMBER
                gfx.text(surf, gfx.small, text, (left, y), color)
        keys = [((["ENTER"], "scan now"), (["X"], "no line can"), (["F"], "flip"))]
        second = [(["Q", "E"], "turn"), (["ESC"], "pause")]
        if self.trainer:
            second.insert(0, (["T"], "auto-train ×{}".format(self.trainer)))
        keys.append(tuple(second))
        self.draw_keys(surf, PANEL.bottom - 58, keys)

    def draw_message(self, surf):
        text, color, life = self.message
        gfx = self.gfx
        rect = pygame.Rect(0, 0, gfx.body.size(text)[0] + 36, 38)
        rect.center = (FLOOR.centerx, FLOOR.bottom - 64)
        surf.blit(gfx.plate(rect.size, (20, 8, 24, 232), 10), rect)
        pygame.draw.rect(surf, color, rect, 2, border_radius=10)
        gfx.text(surf, gfx.body, text, rect.center, color, "center", 255 * min(1.0, life / 0.4))

    def draw_sector_card(self, surf):
        gfx = self.gfx
        t = self.state_t
        index, name, color = sector_info(self.wave)
        gfx.dim(surf, 190 * clamp(t / 0.3, 0.0, 1.0), (4, 6, 12))
        slide = ease_out(clamp(t / 0.5, 0.0, 1.0))
        cy = 250
        gfx.text(surf, gfx.mid, "SECTOR {}".format(index + 1), (600, cy - 60), mix(BLACK, color, slide), "center")
        image, glow = gfx.banner(name, WHITE, color, gfx.big)
        x = lerp(-400, 600, slide)
        surf.blit(glow, glow.get_rect(center=(x, cy)), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(image, image.get_rect(center=(x, cy)))
        first, last = self.wave, self.wave + 4
        if self.max_waves:
            last = min(last, self.max_waves)
        gfx.text(surf, gfx.body, "Waves {} to {}  ·  boss vault on wave {}".format(first, last, last), (600, cy + 50),
                 TEXT_DIM, "center")
        if self.first_card:
            box = pygame.Rect(0, 0, 780, 240)
            box.center = (600, 474)
            surf.blit(gfx.plate(box.size, (8, 10, 22, 236), 12), box)
            pygame.draw.rect(surf, scale_color(color, 0.8), box, 1, border_radius=12)
            lines = (
                ("Each wave: set the laser before the timer runs out. ENTER scans early for a speed bonus.", TEXT),
                ("Every correct unit builds your combo (×2 at 10, ×3 at 20...). A centred laser earns margin points.",
                 TEXT),
                ("A wrong unit costs a SHIELD, and the perceptron retrains on it. Lose all 3 and the run ends.", AMBER),
                ("Boss vaults (every 5th wave) may have NO separating line. If so, press X to prove it.", VIOLET),
            )
            y = box.top + 20
            for text, ink in lines:
                y = gfx.paragraph(surf, gfx.body, text, box.left + 28, y, box.width - 56, ink, gap=3) + 8
        pulse = 0.6 + 0.4 * math.sin(self.time * 4.0)
        gfx.text(surf, gfx.body, "ENTER  go", (600, 660), CYAN, "center", 255 * pulse * clamp(t / 0.6, 0, 1))

    def draw_perks(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 200 * clamp(t / 0.3, 0.0, 1.0), (4, 6, 12))
        gfx.draw_banner(surf, "BOSS DOWN" if self.boss_beaten else "SECTOR SURVIVED", (600, 130), WHITE, VIOLET,
                        gfx.big)
        gfx.text(surf, gfx.body, "Choose one upgrade for the rest of the run", (600, 180), TEXT_DIM, "center")
        for i, rect in enumerate(self.perk_rects()):
            name = self.offer[i]
            _, title, text = PERK_INFO[name]
            appear = ease_out_back(clamp((t - 0.1 * i) / 0.4, 0.0, 1.0))
            if appear <= 0.02:
                continue
            r = rect.move(0, int((1.0 - appear) * 80))
            focused = i == self.perk_focus
            panel(surf, r, (14, 18, 34), VIOLET if focused else PANEL_EDGE, 14, 2 if focused else 1)
            if focused:
                gfx.add_glow(surf, r.centerx, r.top + 70, 70, VIOLET, 0.35)
            draw_perk_icon(surf, gfx, name, r.centerx, r.top + 70, 34, self.time)
            gfx.text(surf, gfx.mid, title, (r.centerx, r.top + 128), WHITE if focused else TEXT, "center")
            y = r.top + 156
            for line in gfx.wrap(gfx.small, text, r.width - 40):
                gfx.text(surf, gfx.small, line, (r.centerx, y), TEXT_DIM, "midtop")
                y += 18
            owned = self.perks.get(name, 0)
            if owned:
                gfx.text(surf, gfx.tiny, "owned ×{}".format(owned), (r.centerx, r.bottom - 22), PINK, "center")
        pulse = 0.6 + 0.4 * math.sin(self.time * 4.0)
        gfx.text(surf, gfx.body, "← →  choose     ENTER  take it", (600, 560), CYAN, "center", 255 * pulse)

    def draw_proof(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 100 * clamp(t / 0.4, 0.0, 1.0), (20, 6, 40))
        if t > 0.1:
            gfx.draw_banner(surf, "NOT LINEARLY SEPARABLE", (FLOOR.centerx, FLOOR.top + 150), (240, 230, 255), VIOLET,
                            gfx.title)

    def draw_gameover(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 120 * clamp(t / 0.3, 0.0, 1.0), (40, 0, 9))
        surf.blit(get_shutter(gfx), (0, int(lerp(-720, 0, bounce(t / 0.7)))))
        if t < 0.8:
            return
        box = pygame.Rect(0, 0, 640, 220)
        box.center = (600, 360)
        surf.blit(gfx.plate(box.size, (12, 6, 9, 240), 14), box)
        pygame.draw.rect(surf, RED, box, 2, border_radius=14)
        gfx.draw_banner(surf, "VAULT LOCKDOWN", (600, 318), (255, 226, 231), RED, gfx.big)
        gfx.text(surf, gfx.mid, "FINAL SCORE  " + score_text(self.score), (600, 372), GOLD, "center")
        gfx.text(surf, gfx.small, "Out of shields on wave {}".format(self.wave), (600, 404), TEXT_DIM, "center")

    def draw_complete(self, surf):
        gfx = self.gfx
        t = self.state_t
        gfx.dim(surf, 190 * clamp(t / 0.4, 0.0, 1.0), (3, 10, 9))
        gfx.draw_banner(surf, "DAILY HEIST COMPLETE", (600, 300), (224, 255, 238), GREEN, gfx.big)
        gfx.text(surf, gfx.mid, "FINAL SCORE  " + score_text(self.score), (600, 360), GOLD, "center")


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------
class PauseScene(Scene):
    overlay = True

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        endless = isinstance(game, EndlessScene)
        items = [MenuItem("RESUME", "resume", color=GREEN), MenuItem("RESTART", "restart", color=CYAN),
                 MenuItem("HOW TO PLAY", "help", color=VIOLET),
                 MenuItem("ABANDON RUN" if endless else "VAULT LIST", "quit", color=RED if endless else TEXT_DIM)]
        self.menu = Menu(app, items, 600 - 150, 250, 300, 52, 12)
        self.help = False

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.help:
                self.help = False
            else:
                self.app.pop()
                self.audio.play("ui_back")
            return True
        if self.help:
            if (event.type == pygame.KEYDOWN and event.key in CONFIRM) or \
                    (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
                self.help = False
            return True
        action = self.menu.handle_event(event)
        if action == "resume":
            self.app.pop()
        elif action == "restart":
            self.app.pop()
            if isinstance(self.game, EndlessScene):
                self.app.go_endless(self.game.daily)
            else:
                self.game.restart()
        elif action == "help":
            self.help = True
        elif action == "quit":
            self.app.pop()
            if isinstance(self.game, EndlessScene):
                self.app.go_menu()
            else:
                self.app.go_levels(self.game.index)
        return True

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)

    def draw(self, surf):
        gfx = self.gfx
        gfx.dim(surf, 175, (4, 6, 12))
        if self.help:
            draw_controls(surf, gfx)
            return
        gfx.draw_banner(surf, "PAUSED", (600, 170), WHITE, CYAN, gfx.big)
        self.menu.draw(surf, gfx, self.time)
        gfx.text(surf, gfx.small, "ESC resumes", (600, 560), TEXT_DIM, "center")


def draw_controls(surf, gfx):
    box = pygame.Rect(0, 0, 820, 520)
    box.center = (600, 370)
    surf.blit(gfx.plate(box.size, (8, 10, 22, 240), 14), box)
    pygame.draw.rect(surf, CYAN, box, 1, border_radius=14)
    gfx.text(surf, gfx.title, "HOW TO PLAY", (box.centerx, box.top + 22), WHITE, "midtop")
    y = box.top + 74
    for keys, text in CONTROLS_HELP:
        gfx.text(surf, gfx.label, keys, (box.left + 220, y + 2), AMBER, "topright")
        gfx.text(surf, gfx.body, text, (box.left + 244, y), TEXT)
        y += 30
    gfx.text(surf, gfx.small, "ENTER or ESC to close", (box.centerx, box.bottom - 24), TEXT_DIM, "center")


# ---------------------------------------------------------------------------
# Results of an endless or daily run
# ---------------------------------------------------------------------------
class NameEntry:
    LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def __init__(self, initial):
        initial = "".join(c for c in (initial or "ACE").upper() if c in self.LETTERS)[:3]
        self.chars = list(initial.ljust(3, "A"))
        self.slot = 0
        self.done = False

    @property
    def name(self):
        return "".join(self.chars)

    def handle_event(self, event, audio):
        if event.type != pygame.KEYDOWN:
            return False
        if event.key in CONFIRM:
            self.done = True
            audio.play("ui_select")
        elif event.key == pygame.K_LEFT:
            self.slot = (self.slot - 1) % 3
            audio.play("ui_move")
        elif event.key == pygame.K_RIGHT:
            self.slot = (self.slot + 1) % 3
            audio.play("ui_move")
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            i = self.LETTERS.index(self.chars[self.slot])
            self.chars[self.slot] = self.LETTERS[(i + (1 if event.key == pygame.K_UP else -1)) % len(self.LETTERS)]
            audio.play("tick")
        elif event.key == pygame.K_BACKSPACE:
            self.slot = max(0, self.slot - 1)
            audio.play("ui_back")
        elif event.unicode and event.unicode.upper() in self.LETTERS:
            self.chars[self.slot] = event.unicode.upper()
            self.slot = min(2, self.slot + 1)
            audio.play("type")
        else:
            return False
        return True

    def draw(self, surf, gfx, cx, y, time):
        for i, char in enumerate(self.chars):
            x = cx + (i - 1) * 64
            rect = pygame.Rect(0, 0, 54, 66)
            rect.center = (x, y)
            focused = i == self.slot
            panel(surf, rect, (14, 18, 34), GOLD if focused else PANEL_EDGE, 8, 2)
            gfx.text(surf, gfx.big, char, rect.center, WHITE if focused else TEXT, "center")
            if focused:
                pulse = 0.5 + 0.5 * math.sin(time * 6)
                pygame.draw.line(surf, mix(GOLD, WHITE, pulse), (rect.left + 10, rect.bottom - 8),
                                 (rect.right - 10, rect.bottom - 8), 3)


class ResultsScene(Scene):
    music = "menu"

    def __init__(self, app, summary):
        super().__init__(app)
        self.summary = s = summary
        self.attract = Attract(26)
        p = self.profile
        self.daily = s["daily"]
        judged = s["correct"] + s["wrong"]
        self.accuracy = s["correct"] / judged if judged else 0.0
        self.xp = s["score"] // 25 + 15 * s["cleared"] + (150 if self.daily and s["completed"] else 0)
        p.add_xp(self.xp)
        p.bump("runs")
        if self.daily:
            self.new_best = p.record_daily(s["date_key"], s["score"], s["cleared"], s["completed"])
            if s["completed"]:
                p.unlock("daily")
            self.entry = None
        else:
            self.new_best = p.record_run(s["score"], s["wave"])
            self.entry = NameEntry(p.data.get("last_name")) if p.qualifies(s["score"]) else None
        self.position = None
        self.shown = 0.0
        items = [MenuItem("PLAY AGAIN", "again", color=GREEN), MenuItem("MAIN MENU", "menu", color=TEXT_DIM)]
        self.menu = Menu(app, items, 600 - 216, 646, 210, 44, 12, horizontal=True)

    @property
    def text_input(self):
        return self.entry is not None and not self.entry.done

    def handle_event(self, event):
        if self.entry is not None and not self.entry.done:
            if self.entry.handle_event(event, self.audio) and self.entry.done:
                self.position = self.profile.add_score(self.entry.name, self.summary["score"], self.summary["wave"])
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go_menu()
            return True
        action = self.menu.handle_event(event)
        if action == "again":
            self.app.go_endless(self.daily)
        elif action == "menu":
            self.app.go_menu()
        return True

    def update(self, dt):
        super().update(dt)
        self.attract.update(dt)
        self.menu.update(dt)
        target = self.summary["score"]
        if self.time > 0.4 and self.shown < target:
            before = int(self.shown)
            self.shown = min(target, self.shown + max(1.0, target * dt / 1.4))
            if int(self.shown) // 250 != before // 250:
                self.audio.play("tick")

    def draw(self, surf):
        gfx = self.gfx
        s = self.summary
        self.attract.draw(surf, gfx, power=0.35)
        gfx.dim(surf, 150, (4, 6, 12))
        if self.daily:
            title = "DAILY HEIST #{}".format(s["daily_no"]) + (" COMPLETE" if s["completed"] else "")
        else:
            title = "RUN OVER"
        gfx.draw_banner(surf, title, (600, 70), WHITE, GREEN if s["completed"] else CYAN, gfx.big)
        left = pygame.Rect(60, 120, 520, 500)
        panel(surf, left, (10, 14, 26), PANEL_EDGE, 14)
        gfx.text(surf, gfx.label, "SCORE", (left.centerx, left.top + 20), TEXT_DIM, "midtop")
        gfx.text(surf, gfx.huge, score_text(self.shown), (left.centerx, left.top + 84), GOLD, "center")
        if self.new_best and self.shown >= s["score"]:
            pulse = 0.6 + 0.4 * math.sin(self.time * 6)
            gfx.text(surf, gfx.mid, "NEW BEST!", (left.centerx, left.top + 138), mix(GOLD, WHITE, pulse), "center")
        stats = (("WAVES CLEARED", str(s["cleared"])), ("ACCURACY", "{:.0f}%".format(self.accuracy * 100)),
                 ("BEST COMBO", str(s["best_combo"])), ("PERFECT WAVES", str(s["perfect"])),
                 ("PROOFS (X)", str(s["proofs"])), ("TIME", clock_text(s["time"])))
        for i, (label, value) in enumerate(stats):
            col, row = i % 2, i // 2
            x = left.left + 40 + col * 240
            y = left.top + 176 + row * 62
            gfx.text(surf, gfx.label, label, (x, y), TEXT_DIM)
            gfx.text(surf, gfx.value, value, (x, y + 18), TEXT)
        name, into, need = self.profile.rank_progress()
        y = left.top + 372
        gfx.text(surf, gfx.mid, "+{} XP".format(self.xp), (left.left + 40, y), GOLD)
        gfx.text(surf, gfx.body, "RANK: " + name.upper(), (left.right - 40, y + 4), CYAN, "topright")
        bar = pygame.Rect(left.left + 40, y + 36, left.width - 80, 10)
        pygame.draw.rect(surf, (30, 41, 66), bar, border_radius=5)
        frac = 1.0 if need is None else into / need
        pygame.draw.rect(surf, CYAN, (bar.left, bar.top, int(bar.width * frac), bar.height), border_radius=5)
        if self.daily:
            share = "Hyperplane Heist · Daily #{} · {} pts · {}/10 waves".format(s["daily_no"], score_text(s["score"]),
                                                                          s["cleared"])
            box = pygame.Rect(left.left + 24, left.bottom - 66, left.width - 48, 48)
            panel(surf, box, (16, 22, 40), GOLD, 8)
            gfx.text(surf, gfx.small, share, (box.centerx, box.top + 8), WHITE, "midtop")
            gfx.text(surf, gfx.tiny, "Screenshot it and challenge your friends to beat today's vault.",
                     (box.centerx, box.top + 28), TEXT_DIM, "midtop")
        right = pygame.Rect(620, 120, 520, 500)
        panel(surf, right, (10, 14, 26), PANEL_EDGE, 14)
        if self.entry is not None and not self.entry.done:
            gfx.text(surf, gfx.title, "TOP 10!", (right.centerx, right.top + 40), GOLD, "midtop")
            gfx.text(surf, gfx.body, "Enter your initials", (right.centerx, right.top + 96), TEXT, "midtop")
            self.entry.draw(surf, gfx, right.centerx, right.top + 190, self.time)
            gfx.text(surf, gfx.small, "type letters, or ↑ ↓ to change and ← → to move", (right.centerx, right.top + 262),
                     TEXT_DIM, "midtop")
            gfx.text(surf, gfx.small, "ENTER to save", (right.centerx, right.top + 286), TEXT_DIM, "midtop")
        elif self.daily:
            self.draw_daily_list(surf, right)
        else:
            self.draw_leaderboard(surf, right)
        self.menu.draw(surf, gfx, self.time)

    def draw_leaderboard(self, surf, rect):
        gfx = self.gfx
        gfx.text(surf, gfx.label, "ENDLESS LEADERBOARD", (rect.left + 30, rect.top + 22), CYAN)
        rows = self.profile.leaderboard()
        if not rows:
            gfx.text(surf, gfx.body, "No scores yet.", (rect.centerx, rect.centery), TEXT_DIM, "center")
        for i, row in enumerate(rows):
            y = rect.top + 56 + i * 42
            highlight = i == self.position
            if highlight:
                pygame.draw.rect(surf, (40, 34, 12), (rect.left + 16, y - 6, rect.width - 32, 36), border_radius=6)
            color = GOLD if highlight else (TEXT if i < 3 else TEXT_DIM)
            gfx.text(surf, gfx.mid, "{:>2}".format(i + 1), (rect.left + 30, y), color)
            gfx.text(surf, gfx.mid, row["name"], (rect.left + 90, y), color)
            gfx.text(surf, gfx.small, "wave {}".format(row["wave"]), (rect.left + 190, y + 5), TEXT_DIM)
            gfx.text(surf, gfx.mid, score_text(row["score"]), (rect.right - 30, y), color, "topright")

    def draw_daily_list(self, surf, rect):
        gfx = self.gfx
        gfx.text(surf, gfx.label, "YOUR DAILY HEISTS", (rect.left + 30, rect.top + 22), CYAN)
        days = sorted(self.profile.data["daily"].items(), reverse=True)[:9]
        for i, (key, record) in enumerate(days):
            y = rect.top + 60 + i * 44
            color = GOLD if key == self.summary["date_key"] else TEXT
            gfx.text(surf, gfx.mid, key, (rect.left + 30, y), color)
            gfx.text(surf, gfx.small, "{}/10 waves".format(record.get("waves", 0)), (rect.left + 210, y + 5), TEXT_DIM)
            gfx.text(surf, gfx.mid, score_text(record.get("score", 0)), (rect.right - 30, y), color, "topright")
