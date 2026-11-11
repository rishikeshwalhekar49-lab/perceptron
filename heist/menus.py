"""Hyperplane Heist: the main menu, vault select, profile, records and settings."""
import math

import pygame

from .core import clamp, score_text
from .gfx import (AMBER, CYAN, GOLD, GREEN, INK, PANEL_EDGE, PINK, RED, SKIN_COLORS, TEXT, TEXT_DIM, TEXT_FAINT,
                  VIOLET, WHITE, beam, draw_lock, draw_nyx, draw_shield, draw_star, mix, panel, scale_color,
                  skin_color)
from .levels import LEVELS
from .save import (ACHIEVEMENTS, LESSON_IDS, RANKS, SKIN_ORDER, SKIN_RULES, daily_key, daily_number)
from .scene import Scene
from .ui import Attract, Menu, MenuItem

CONFIRM = (pygame.K_RETURN, pygame.K_KP_ENTER)

FACTS = (
    "The Mark I Perceptron (1960) learned to recognise shapes from a 20 × 20 grid of photocells.",
    "If w and b start at zero, the learning rate doesn't change which mistakes a perceptron makes.",
    "Multiply every weight and the bias by the same positive number and the boundary doesn't move.",
    "A single perceptron can compute AND, OR and NAND, but never XOR.",
    "On separable data the perceptron is guaranteed to stop making mistakes (Novikoff, 1962).",
    "The weight vector always points into the SAFE side, at a right angle to the laser.",
    "Today's neural networks still compute weighted sums plus a bias. They just stack billions of them.",
    "Support vector machines pick the separating line with the widest margin.",
    "Logistic regression is a perceptron that swaps the hard step for a smooth sigmoid.",
)


def draw_rank_badge(surf, gfx, cx, cy, rank_index, time):
    color = (TEXT_DIM, CYAN, GREEN, AMBER, VIOLET, PINK, GOLD)[min(rank_index, 6)]
    gfx.add_glow(surf, cx, cy, 56, color, 0.35)
    draw_shield(surf, cx, cy, 34, scale_color(color, 0.35))
    draw_shield(surf, cx, cy, 34, color, False)
    for k in range(min(rank_index + 1, 7)):
        angle = -math.pi / 2 + (k - min(rank_index, 6) / 2) * 0.32
        draw_star(surf, cx + math.cos(angle) * 18, cy + 4 + math.sin(angle) * 18 + 14, 4, color)
    gfx.text(surf, gfx.mid, RANKS[rank_index][1][0], (cx, cy - 6), WHITE, "center")


class MainMenuScene(Scene):
    music = "menu"

    def __init__(self, app, focus=None):
        super().__init__(app)
        self.attract = Attract(30)
        p = self.profile
        daily = p.daily_record()
        lessons = len(p.lessons)
        items = [
            MenuItem("CAMPAIGN", "campaign", "12 vaults · {} of 36 stars".format(p.total_stars()), color=CYAN),
            MenuItem("ENDLESS HEIST", "endless", "best {} · wave {}".format(score_text(p.endless_best),
                                                                           p.endless_best_wave) if p.endless_best
                     else "waves, bosses, perks: how far can you go?", color=PINK),
            MenuItem("DAILY HEIST", "daily", "#{} · {}".format(
                daily_number(), "best " + score_text(daily["score"]) if daily else "same vault for everyone today"),
                color=GOLD),
            MenuItem("ACADEMY", "academy", "learn how a perceptron works · {}/{} lessons".format(lessons, len(LESSON_IDS)),
                     color=VIOLET),
            MenuItem("HALL OF FAME", "records", "leaderboard and daily records", color=AMBER),
            MenuItem("PROFILE", "profile", "rank, achievements, laser skins", color=GREEN),
            MenuItem("SETTINGS", "settings", "sound, effects, display", color=TEXT_DIM),
            MenuItem("QUIT", "quit", color=RED),
        ]
        self.menu = Menu(app, items, 70, 186, 420, 52, 7)
        actions = [item.action for item in items]
        if focus in actions:
            self.menu.focus = actions.index(focus)
        self.fact = int(self.app.time / 7.0) % len(FACTS)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.quit()
            return True
        action = self.menu.handle_event(event)
        if action == "campaign":
            self.app.go_levels(self.first_open_level())
        elif action == "endless":
            self.app.go_endless(False)
        elif action == "daily":
            self.app.go_endless(True)
        elif action == "academy":
            self.app.go_academy()
        elif action == "records":
            self.app.replace(RecordsScene(self.app))
        elif action == "profile":
            self.app.replace(ProfileScene(self.app))
        elif action == "settings":
            self.app.replace(SettingsScene(self.app))
        elif action == "quit":
            self.app.quit()
        return True

    def first_open_level(self):
        keys = [level.key for level in LEVELS]
        for i, key in enumerate(keys):
            if self.profile.stars(key) == 0:
                return i
        return 0

    def update(self, dt):
        super().update(dt)
        self.attract.update(dt)
        self.menu.update(dt)
        self.fact = int(self.app.time / 7.0) % len(FACTS)

    def draw(self, surf):
        gfx = self.gfx
        self.attract.draw(surf, gfx, skin_color(self.profile.skin, self.time))
        gfx.dim(surf, 70, (4, 6, 12))
        gfx.draw_banner(surf, "HYPERPLANE HEIST", (600, 78), WHITE, CYAN)
        gfx.text(surf, gfx.body, "One laser. One perceptron. Crack the vault, then learn exactly how it thinks.",
                 (600, 140), TEXT_DIM, "center")
        self.menu.draw(surf, gfx, self.time)
        # profile card
        card = pygame.Rect(560, 186, 570, 170)
        surf.blit(gfx.plate(card.size, (8, 10, 22, 225), 14), card)
        pygame.draw.rect(surf, PANEL_EDGE, card, 1, border_radius=14)
        name, into, need = self.profile.rank_progress()
        rank_i = [r[1] for r in RANKS].index(name)
        draw_rank_badge(surf, gfx, card.left + 70, card.top + 78, rank_i, self.time)
        gfx.text(surf, gfx.label, "YOUR RANK", (card.left + 140, card.top + 24), TEXT_DIM)
        gfx.text(surf, gfx.title, name.upper(), (card.left + 140, card.top + 42), WHITE)
        bar = pygame.Rect(card.left + 140, card.top + 92, card.width - 170, 10)
        pygame.draw.rect(surf, (30, 41, 66), bar, border_radius=5)
        frac = 1.0 if need is None else into / need
        pygame.draw.rect(surf, CYAN, (bar.left, bar.top, int(bar.width * frac), bar.height), border_radius=5)
        xp_text = "{} XP".format(self.profile.xp) + ("" if need is None else "  ·  {} to {}".format(
            need - into, RANKS[rank_i + 1][1]))
        gfx.text(surf, gfx.small, xp_text, (bar.left, bar.bottom + 8), TEXT_DIM)
        got = len(self.profile.data["achievements"])
        gfx.text(surf, gfx.small, "{} / {} achievements".format(got, len(ACHIEVEMENTS)), (bar.left, bar.bottom + 30),
                 GOLD)
        # fact card
        fact = pygame.Rect(560, 376, 570, 128)
        surf.blit(gfx.plate(fact.size, (8, 10, 22, 225), 14), fact)
        pygame.draw.rect(surf, scale_color(VIOLET, 0.7), fact, 1, border_radius=14)
        draw_nyx(surf, fact.left + 52, fact.top + 62, 26, self.time, talking=(self.app.time % 7.0) < 1.5,
                 color=VIOLET)
        gfx.text(surf, gfx.label, "DID YOU KNOW?", (fact.left + 108, fact.top + 20), VIOLET)
        gfx.paragraph(surf, gfx.body, FACTS[self.fact], fact.left + 108, fact.top + 44, fact.width - 130, TEXT)
        # what's new strip
        strip = pygame.Rect(560, 524, 570, 114)
        surf.blit(gfx.plate(strip.size, (8, 10, 22, 225), 14), strip)
        pygame.draw.rect(surf, PANEL_EDGE, strip, 1, border_radius=14)
        gfx.text(surf, gfx.label, "TODAY'S DAILY HEIST", (strip.left + 24, strip.top + 18), GOLD)
        record = self.profile.daily_record()
        status = ("Best today: {} pts on {}/10 waves".format(score_text(record["score"]), record["waves"])
                  if record else "Not cracked yet. Everyone gets the same 10 waves today.")
        gfx.text(surf, gfx.body, status, (strip.left + 24, strip.top + 44), TEXT)
        gfx.text(surf, gfx.small, "Vault #{}  ·  {}".format(daily_number(), daily_key()), (strip.left + 24,
                                                                                          strip.top + 72), TEXT_DIM)
        gfx.text(surf, gfx.tiny, "↑ ↓ choose   ENTER select   M sound   ESC quit", (600, 694), TEXT_FAINT, "center")


class LevelSelectScene(Scene):
    music = "menu"

    def __init__(self, app, focus=0):
        super().__init__(app)
        self.focus = clamp(focus, 0, len(LEVELS) - 1)
        self.keys = [level.key for level in LEVELS]
        self.cards = [pygame.Rect(70 + (i % 4) * 268, 128 + (i // 4) * 150, 250, 134) for i in range(len(LEVELS))]

    def unlocked(self, i):
        return self.profile.level_unlocked(i, self.keys)

    def open(self, i):
        if self.unlocked(i):
            self.audio.play("ui_select")
            self.app.go_campaign(i)
        else:
            self.audio.play("ui_back")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go_menu("campaign")
                return True
            moves = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1, pygame.K_UP: -4, pygame.K_DOWN: 4}
            if event.key in moves:
                self.focus = clamp(self.focus + moves[event.key], 0, len(LEVELS) - 1)
                self.audio.play("ui_move")
            elif event.key in CONFIRM + (pygame.K_SPACE,):
                self.open(self.focus)
            elif event.key == pygame.K_a:
                self.open_lesson()
            return True
        if event.type == pygame.MOUSEMOTION:
            for i, rect in enumerate(self.cards):
                if rect.collidepoint(event.pos) and i != self.focus:
                    self.focus = i
                    self.audio.play("ui_move")
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.cards):
                if rect.collidepoint(event.pos):
                    self.focus = i
                    self.open(i)
        return True

    def open_lesson(self):
        lesson = LEVELS[self.focus].lesson
        if lesson in LESSON_IDS:
            from .academy import LessonScene
            self.audio.play("ui_select")
            self.app.replace(LessonScene(self.app, LESSON_IDS.index(lesson)))

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        gfx.draw_banner(surf, "CAMPAIGN", (600, 52), WHITE, CYAN, gfx.big)
        gfx.text(surf, gfx.body, "{} / 36 stars".format(self.profile.total_stars()), (600, 92), GOLD, "center")
        for i, rect in enumerate(self.cards):
            level = LEVELS[i]
            open_ = self.unlocked(i)
            focused = i == self.focus
            stars = self.profile.stars(level.key)
            accent = CYAN if open_ else TEXT_FAINT
            panel(surf, rect, (18, 24, 42) if focused else (12, 16, 30), accent if focused else PANEL_EDGE, 12,
                  2 if focused else 1)
            if focused and open_:
                gfx.add_glow(surf, rect.centerx, rect.top + 50, 70, CYAN, 0.3)
            gfx.text(surf, gfx.label, "VAULT {}".format(i + 1), (rect.left + 18, rect.top + 14), accent)
            if open_:
                gfx.text(surf, gfx.mid, level.name, (rect.left + 18, rect.top + 36), WHITE)
                for line_i, line in enumerate(gfx.wrap(gfx.tiny, level.concept, rect.width - 36)[:2]):
                    gfx.text(surf, gfx.tiny, line, (rect.left + 18, rect.top + 66 + line_i * 14), TEXT_DIM)
                for k in range(3):
                    draw_star(surf, rect.left + 28 + k * 26, rect.bottom - 22, 10, GOLD if k < stars else (52, 58, 76),
                              k < stars)
            else:
                draw_lock(surf, rect.centerx, rect.centery - 6, 22, TEXT_FAINT)
                gfx.text(surf, gfx.tiny, "clear vault {} to open".format(i), (rect.centerx, rect.bottom - 24),
                         TEXT_FAINT, "center")
        level = LEVELS[self.focus]
        info = pygame.Rect(70, 586, 1060, 92)
        surf.blit(gfx.plate(info.size, (8, 10, 22, 225), 12), info)
        pygame.draw.rect(surf, PANEL_EDGE, info, 1, border_radius=12)
        if self.unlocked(self.focus):
            record = self.profile.level_record(level.key)
            gfx.text(surf, gfx.mid, level.name, (info.left + 24, info.top + 16), WHITE)
            gfx.text(surf, gfx.small, level.tip, (info.left + 24, info.top + 48), TEXT_DIM)
            if record:
                best = "best time {:.1f}s".format(record.get("best_time", 0))
                if record.get("best_margin") is not None:
                    best += "  ·  best margin {:.2f}".format(record["best_margin"])
                gfx.text(surf, gfx.small, best, (info.right - 24, info.top + 20), GOLD, "topright")
            if level.lesson in LESSON_IDS:
                gfx.text(surf, gfx.small, "A: open the related Academy lesson", (info.right - 24, info.top + 62),
                         VIOLET, "topright")
        else:
            gfx.text(surf, gfx.mid, "Locked", (info.left + 24, info.top + 30), TEXT_FAINT)
        gfx.text(surf, gfx.tiny, "arrows choose   ENTER play   ESC back", (600, 698), TEXT_FAINT, "center")


class ProfileScene(Scene):
    music = "menu"

    def __init__(self, app):
        super().__init__(app)
        self.section = 0            # 0 = achievements, 1 = skins
        self.focus = 0
        self.skin_focus = SKIN_ORDER.index(self.profile.skin)
        self.tiles = [pygame.Rect(60 + (i % 3) * 236, 196 + (i // 3) * 50, 226, 42) for i in range(len(ACHIEVEMENTS))]
        self.skin_rows = [pygame.Rect(800, 196 + i * 58, 340, 50) for i in range(len(SKIN_ORDER))]

    def equip(self, i):
        name = SKIN_ORDER[i]
        if self.profile.skin_unlocked(name):
            self.profile.set_setting("skin", name)
            self.audio.play("ui_select")
        else:
            self.audio.play("ui_back")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go_menu("profile")
            elif event.key == pygame.K_TAB:
                self.section = 1 - self.section
                self.audio.play("ui_move")
            elif self.section == 0:
                moves = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1, pygame.K_UP: -3, pygame.K_DOWN: 3}
                if event.key in moves:
                    self.focus = clamp(self.focus + moves[event.key], 0, len(ACHIEVEMENTS) - 1)
                    self.audio.play("ui_move")
            else:
                if event.key in (pygame.K_UP, pygame.K_DOWN):
                    self.skin_focus = (self.skin_focus + (1 if event.key == pygame.K_DOWN else -1)) % len(SKIN_ORDER)
                    self.audio.play("ui_move")
                elif event.key in CONFIRM + (pygame.K_SPACE,):
                    self.equip(self.skin_focus)
            return True
        if event.type == pygame.MOUSEMOTION:
            for i, rect in enumerate(self.tiles):
                if rect.collidepoint(event.pos):
                    self.section, self.focus = 0, i
            for i, rect in enumerate(self.skin_rows):
                if rect.collidepoint(event.pos):
                    self.section, self.skin_focus = 1, i
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.skin_rows):
                if rect.collidepoint(event.pos):
                    self.equip(i)
        return True

    def draw(self, surf):
        gfx = self.gfx
        p = self.profile
        surf.blit(gfx.backdrop, (0, 0))
        name, into, need = p.rank_progress()
        rank_i = [r[1] for r in RANKS].index(name)
        draw_rank_badge(surf, gfx, 100, 92, rank_i, self.time)
        gfx.text(surf, gfx.label, "PROFILE", (160, 40), TEXT_DIM)
        gfx.text(surf, gfx.title, name.upper(), (160, 58), WHITE)
        bar = pygame.Rect(160, 104, 420, 10)
        pygame.draw.rect(surf, (30, 41, 66), bar, border_radius=5)
        pygame.draw.rect(surf, CYAN, (bar.left, bar.top, int(bar.width * (1.0 if need is None else into / need)),
                                      bar.height), border_radius=5)
        gfx.text(surf, gfx.small, "{} XP".format(p.xp), (bar.right + 14, bar.top - 3), TEXT_DIM)
        stats = ("stars {}/36".format(p.total_stars()), "endless best {}".format(score_text(p.endless_best)),
                 "units classified {}".format(p.stat("correct")), "lessons {}/{}".format(len(p.lessons),
                                                                                       len(LESSON_IDS)))
        gfx.text(surf, gfx.small, "   ·   ".join(stats), (160, 126), TEXT_DIM)
        gfx.text(surf, gfx.label, "ACHIEVEMENTS  {}/{}".format(len(p.data["achievements"]), len(ACHIEVEMENTS)),
                 (60, 170), GOLD if self.section == 0 else TEXT_DIM)
        for i, (aid, title, description, xp) in enumerate(ACHIEVEMENTS):
            rect = self.tiles[i]
            got = p.has(aid)
            focused = self.section == 0 and i == self.focus
            panel(surf, rect, (22, 26, 20) if got else (12, 16, 30), GOLD if focused else (mix(PANEL_EDGE, GOLD, 0.4)
                                                                                         if got else PANEL_EDGE), 8,
                  2 if focused else 1)
            draw_star(surf, rect.left + 20, rect.centery, 9, GOLD if got else (52, 58, 76), got)
            font = gfx.small if gfx.small.size(title)[0] <= rect.width - 46 else gfx.tiny
            gfx.text(surf, font, title, (rect.left + 38, rect.centery), WHITE if got else TEXT_FAINT, "midleft")
        aid, title, description, xp = ACHIEVEMENTS[self.focus]
        info = pygame.Rect(60, 610, 700, 70)
        surf.blit(gfx.plate(info.size, (8, 10, 22, 225), 12), info)
        pygame.draw.rect(surf, PANEL_EDGE, info, 1, border_radius=12)
        gfx.text(surf, gfx.mid, title, (info.left + 20, info.top + 12), GOLD if p.has(aid) else WHITE)
        gfx.text(surf, gfx.small, description + "   +{} XP".format(xp), (info.left + 20, info.top + 42), TEXT_DIM)
        gfx.text(surf, gfx.label, "LASER SKINS", (800, 170), CYAN if self.section == 1 else TEXT_DIM)
        for i, skin in enumerate(SKIN_ORDER):
            rect = self.skin_rows[i]
            unlocked = p.skin_unlocked(skin)
            equipped = p.skin == skin
            focused = self.section == 1 and i == self.skin_focus
            panel(surf, rect, (16, 20, 36), CYAN if focused else PANEL_EDGE, 10, 2 if focused else 1)
            color = skin_color(skin, self.time)
            if unlocked:
                gfx.fx.fill((0, 0, 0), (rect.left + 14, rect.top + 6, 90, rect.height - 12))
                gfx.fx.set_clip((rect.left + 14, rect.top + 6, 90, rect.height - 12))
                beam(gfx.fx, (rect.left + 14, rect.centery), (rect.left + 104, rect.centery), color, 0.9,
                     layers=((16, 0.08), (10, 0.18), (6, 0.4), (3, 0.7)))
                gfx.fx.set_clip(None)
                surf.blit(gfx.fx, (rect.left + 14, rect.top + 6), (rect.left + 14, rect.top + 6, 90, rect.height - 12),
                          special_flags=pygame.BLEND_RGB_ADD)
            else:
                draw_lock(surf, rect.left + 58, rect.centery - 6, 14, TEXT_FAINT)
            gfx.text(surf, gfx.body, SKIN_COLORS[skin][0], (rect.left + 120, rect.top + 7), WHITE if unlocked
                     else TEXT_FAINT)
            gfx.text(surf, gfx.tiny, "EQUIPPED" if equipped else (SKIN_RULES[skin] if not unlocked else "ENTER to equip"),
                     (rect.left + 120, rect.top + 29), GREEN if equipped else TEXT_DIM)
        gfx.text(surf, gfx.tiny, "arrows choose   TAB achievements / skins   ESC back", (600, 698), TEXT_FAINT, "center")


class RecordsScene(Scene):
    music = "menu"

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE,) + CONFIRM:
            self.app.go_menu("records")
        return True

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        gfx.draw_banner(surf, "HALL OF FAME", (600, 56), WHITE, AMBER, gfx.big)
        left = pygame.Rect(60, 110, 520, 560)
        right = pygame.Rect(620, 110, 520, 560)
        for rect in (left, right):
            panel(surf, rect, (10, 14, 26), PANEL_EDGE, 14)
        gfx.text(surf, gfx.label, "ENDLESS TOP 10", (left.left + 28, left.top + 22), PINK)
        rows = self.profile.leaderboard()
        if not rows:
            gfx.text(surf, gfx.body, "No runs yet. Endless Heist awaits.", left.center, TEXT_DIM, "center")
        for i, row in enumerate(rows):
            y = left.top + 60 + i * 48
            color = (GOLD, (210, 214, 230), (205, 140, 90))[i] if i < 3 else TEXT
            gfx.text(surf, gfx.mid, "{:>2}".format(i + 1), (left.left + 28, y), color)
            gfx.text(surf, gfx.mid, row["name"], (left.left + 84, y), color)
            gfx.text(surf, gfx.small, "wave {}  ·  {}".format(row["wave"], row["date"]), (left.left + 160, y + 5),
                     TEXT_DIM)
            gfx.text(surf, gfx.mid, score_text(row["score"]), (left.right - 28, y), color, "topright")
        gfx.text(surf, gfx.label, "DAILY HEISTS", (right.left + 28, right.top + 22), GOLD)
        days = sorted(self.profile.data["daily"].items(), reverse=True)[:10]
        if not days:
            gfx.text(surf, gfx.body, "No daily heists yet.", right.center, TEXT_DIM, "center")
        for i, (key, record) in enumerate(days):
            y = right.top + 60 + i * 48
            today = key == daily_key()
            gfx.text(surf, gfx.mid, key, (right.left + 28, y), GOLD if today else TEXT)
            gfx.text(surf, gfx.small, "{}/10 waves{}".format(record.get("waves", 0),
                                                            "  ✓" if record.get("finished") else ""),
                     (right.left + 210, y + 5), TEXT_DIM)
            gfx.text(surf, gfx.mid, score_text(record.get("score", 0)), (right.right - 28, y),
                     GOLD if today else TEXT, "topright")
        gfx.text(surf, gfx.tiny, "ESC back", (600, 694), TEXT_FAINT, "center")


class SettingsScene(Scene):
    music = "menu"
    ROWS = (("music", "Music volume"), ("sfx", "Effects volume"), ("muted", "Sound"), ("shake", "Screen shake"),
            ("flashes", "Flashing effects"), ("fullscreen", "Fullscreen"), ("reset", "Reset all progress"))

    def __init__(self, app):
        super().__init__(app)
        self.focus = 0
        self.confirm = 0

    def change(self, step):
        key = self.ROWS[self.focus][0]
        settings = self.profile.settings
        if key in ("music", "sfx"):
            value = round(clamp(settings.get(key, 0.5) + 0.1 * step, 0.0, 1.0), 1)
            self.profile.set_setting(key, value)
            self.audio.play("tick" if key == "music" else "ok3")
        elif key == "fullscreen":
            self.app.toggle_fullscreen()
            self.audio.play("ui_select")
        elif key == "reset":
            self.confirm += 1
            self.audio.play("wrong" if self.confirm == 1 else "ui_select")
            if self.confirm >= 2:
                self.app.reset_progress()
                self.confirm = 0
        else:
            self.profile.set_setting(key, not settings.get(key))
            self.audio.play("ui_select")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go_menu("settings")
            elif event.key in (pygame.K_UP, pygame.K_DOWN):
                self.focus = (self.focus + (1 if event.key == pygame.K_DOWN else -1)) % len(self.ROWS)
                self.confirm = 0
                self.audio.play("ui_move")
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                if self.ROWS[self.focus][0] != "reset":
                    self.change(1 if event.key == pygame.K_RIGHT else -1)
            elif event.key in CONFIRM + (pygame.K_SPACE,):
                self.change(1)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.ROWS)):
                if pygame.Rect(260, 160 + i * 64, 680, 52).collidepoint(event.pos):
                    self.focus = i
                    self.change(1)
        return True

    def value_text(self, key):
        s = self.profile.settings
        if key in ("music", "sfx"):
            return "{:d}%".format(int(round(s.get(key, 0.5) * 100)))
        if key == "muted":
            return "OFF (muted)" if s.get("muted") else "ON"
        if key == "flashes":
            return "FULL" if s.get("flashes", True) else "REDUCED"
        if key == "reset":
            return ("press ENTER again to erase everything" if self.confirm == 1 else "ENTER")
        return "ON" if s.get(key) else "OFF"

    def draw(self, surf):
        gfx = self.gfx
        surf.blit(gfx.backdrop, (0, 0))
        gfx.draw_banner(surf, "SETTINGS", (600, 70), WHITE, CYAN, gfx.big)
        for i, (key, label) in enumerate(self.ROWS):
            rect = pygame.Rect(260, 160 + i * 64, 680, 52)
            focused = i == self.focus
            danger = key == "reset"
            panel(surf, rect, (18, 24, 42) if focused else (12, 16, 30),
                  (RED if danger else CYAN) if focused else PANEL_EDGE, 10, 2 if focused else 1)
            gfx.text(surf, gfx.mid, label, (rect.left + 24, rect.centery), RED if danger else WHITE, "midleft")
            if key in ("music", "sfx"):
                bar = pygame.Rect(rect.right - 300, rect.centery - 4, 200, 8)
                pygame.draw.rect(surf, (30, 41, 66), bar, border_radius=4)
                pygame.draw.rect(surf, CYAN, (bar.left, bar.top, int(bar.width * self.profile.settings.get(key, 0.5)),
                                              bar.height), border_radius=4)
            color = AMBER if (danger and self.confirm) else TEXT
            gfx.text(surf, gfx.body, self.value_text(key), (rect.right - 24, rect.centery), color, "midright")
        note = self.profile.save_error
        path = self.profile.path or "(not saving)"
        gfx.text(surf, gfx.tiny, "Progress is saved to " + path, (600, 640), TEXT_FAINT, "center")
        if note:
            gfx.text(surf, gfx.tiny, "Could not save: " + note, (600, 658), RED, "center")
        gfx.text(surf, gfx.tiny, "↑ ↓ choose   ← → change   ESC back", (600, 694), TEXT_FAINT, "center")
