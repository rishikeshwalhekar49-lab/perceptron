"""Hyperplane Heist: the window, the scene stack, toasts and the main loop.

The loop is async so the same code runs on the desktop and in a browser
(pygbag hands control back to the page at every `await asyncio.sleep(0)`).
"""
import asyncio
import random

import pygame

from .audio import Audio, open_mixer
from .core import WEB, clamp, ease_out
from .gfx import (AMBER, BLACK, CYAN, GOLD, GREEN, SCREEN_H, SCREEN_W, TEXT_DIM, VIOLET, WHITE, Gfx, draw_star,
                  make_icon, panel, scale_color)
from .save import Profile

FPS = 60
FADE_OUT, FADE_IN = 0.16, 0.22
TOAST_LIFE = 3.6


class App:
    def __init__(self, screen, profile=None, audio=True):
        self.screen = screen
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H), 0, 32)
        self.profile = profile if profile is not None else Profile()
        self.gfx = Gfx()
        self.audio = Audio(self.profile.settings, enabled=audio)
        self.stack = []
        self.fade = None
        self.toasts = []
        self.shake = 0.0
        self.time = 0.0
        self.running = True
        self.rng = random.Random()

    # ------------------------------------------------------------- scenes
    @property
    def top(self):
        return self.stack[-1] if self.stack else None

    def start(self):
        from .menus import MainMenuScene
        self._swap(MainMenuScene(self))

    def _music(self):
        for scene in reversed(self.stack):
            if scene.music:
                self.audio.set_track(scene.music)
                return

    def _swap(self, scene):
        for old in self.stack:
            old.leave()
        self.stack = [scene]
        scene.enter()
        self._music()

    def push(self, scene):
        self.stack.append(scene)
        scene.enter()
        self._music()

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop().leave()
            self._music()

    def replace(self, scene, fade=True):
        if not fade:
            self._swap(scene)
        elif self.fade and not self.fade["swapped"]:
            self.fade["next"] = scene
        else:
            self.fade = {"t": 0.0, "next": scene, "swapped": False}

    def go_menu(self, focus=None):
        from .menus import MainMenuScene
        self.replace(MainMenuScene(self, focus))

    def go_levels(self, focus=0):
        from .menus import LevelSelectScene
        self.replace(LevelSelectScene(self, focus))

    def go_campaign(self, index):
        from .play import CampaignScene
        self.replace(CampaignScene(self, index))

    def go_endless(self, daily=False):
        from .play import EndlessScene
        self.replace(EndlessScene(self, daily=daily))

    def go_academy(self, focus=0):
        from .academy import AcademyScene
        self.replace(AcademyScene(self, focus))

    def go_quiz(self):
        from .academy import QuizScene
        self.replace(QuizScene(self))

    # ------------------------------------------------------------ helpers
    def add_shake(self, amount):
        if self.profile.settings.get("shake", True):
            self.shake = max(self.shake, amount)

    def toast(self, kind, title, detail):
        delay = sum(1 for t in self.toasts if t["age"] < 0.6) * 0.6
        self.toasts.append({"kind": kind, "title": title, "detail": detail, "age": -delay, "sounded": False})

    def quit(self):
        self.profile.save()
        if not WEB:                         # a web page cannot close itself; just keep the save
            self.running = False

    def toggle_fullscreen(self):
        try:
            pygame.display.toggle_fullscreen()
        except Exception:
            return
        self.profile.set_setting("fullscreen", not self.profile.settings.get("fullscreen"))

    def reset_progress(self):
        settings = dict(self.profile.settings)
        self.profile.data = Profile._defaults()
        self.profile.data["settings"] = settings
        self.profile._skins_known = set(self.profile.unlocked_skins())
        self.profile.save()
        self.toast("info", "PROGRESS ERASED", "A fresh start")

    # --------------------------------------------------------------- loop
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return
        top = self.top
        if event.type == pygame.KEYDOWN and not (top and top.text_input):
            if event.key == pygame.K_m:
                muted = not self.profile.settings.get("muted")
                self.profile.set_setting("muted", muted)
                if muted:
                    pygame.mixer.stop() if self.audio.ok else None
                self.toast("info", "SOUND OFF" if muted else "SOUND ON", "press M to toggle")
                return
            if event.key == pygame.K_F11:
                self.toggle_fullscreen()
                return
        if self.fade is not None or top is None:
            return
        top.handle_event(event)

    def update(self, dt):
        self.time += dt
        self.shake = max(0.0, self.shake - 2.4 * dt)
        self.audio.update(dt)
        self.profile.bump("playtime", dt)
        if self.fade is not None:
            self.fade["t"] += dt
            if not self.fade["swapped"] and self.fade["t"] >= FADE_OUT:
                self.fade["swapped"] = True
                self._swap(self.fade["next"])
            elif self.fade["t"] >= FADE_OUT + FADE_IN:
                self.fade = None
        top = self.top
        if top is not None:
            top.update(dt)
        for kind, title, detail in self.profile.pop_events():
            self.toast(kind, title, detail)
        for toast in self.toasts:
            toast["age"] += dt
            if toast["age"] >= 0 and not toast["sounded"]:
                toast["sounded"] = True
                self.audio.play({"achievement": "achievement", "rank": "levelup", "skin": "perk"}.get(toast["kind"],
                                                                                                       "ui_select"))
        self.toasts = [t for t in self.toasts if t["age"] < TOAST_LIFE]

    def draw(self):
        canvas = self.canvas
        start = len(self.stack) - 1
        while start > 0 and self.stack[start].overlay:
            start -= 1
        for scene in self.stack[start:]:
            scene.draw(canvas)
        self.draw_toasts(canvas)
        if self.fade is not None:
            t = self.fade["t"]
            alpha = 255 * (t / FADE_OUT if t < FADE_OUT else 1.0 - (t - FADE_OUT) / FADE_IN)
            self.gfx.dim(canvas, clamp(alpha, 0, 255), (2, 3, 8))
        offset = (0, 0)
        if self.shake > 0.0:
            reach = 12.0 * self.shake * self.shake
            offset = (int(self.rng.uniform(-reach, reach)), int(self.rng.uniform(-reach, reach)))
        if offset != (0, 0):
            self.screen.fill(BLACK)
        self.screen.blit(canvas, offset)

    def draw_toasts(self, surf):
        gfx = self.gfx
        y = 14
        for toast in self.toasts:
            age = toast["age"]
            if age < 0:
                continue
            if age < 0.3:
                slide = ease_out(age / 0.3)
            elif age > TOAST_LIFE - 0.35:
                slide = 1.0 - ease_out((age - (TOAST_LIFE - 0.35)) / 0.35)
            else:
                slide = 1.0
            width = 380
            rect = pygame.Rect(int(SCREEN_W - 14 - width * slide), y, width, 58)
            color = {"achievement": GOLD, "rank": CYAN, "skin": VIOLET}.get(toast["kind"], GREEN)
            surf.blit(gfx.plate(rect.size, (8, 10, 22, 240), 10), rect)
            pygame.draw.rect(surf, color, rect, 2, border_radius=10)
            if toast["kind"] == "achievement":
                draw_star(surf, rect.left + 30, rect.centery, 14, GOLD)
            else:
                pygame.draw.circle(surf, scale_color(color, 0.4), (rect.left + 30, rect.centery), 14)
                pygame.draw.circle(surf, color, (rect.left + 30, rect.centery), 14, 2)
            label = {"achievement": "ACHIEVEMENT UNLOCKED"}.get(toast["kind"], "")
            if label:
                gfx.text(surf, gfx.tiny, label, (rect.left + 56, rect.top + 7), color)
                gfx.text(surf, gfx.body, toast["title"], (rect.left + 56, rect.top + 20), WHITE)
                gfx.text(surf, gfx.tiny, toast["detail"], (rect.left + 56, rect.top + 40), TEXT_DIM)
            else:
                gfx.text(surf, gfx.body, toast["title"], (rect.left + 56, rect.top + 12), WHITE)
                gfx.text(surf, gfx.tiny, toast["detail"], (rect.left + 56, rect.top + 34), TEXT_DIM)
            y += 66

    async def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
            await asyncio.sleep(0)      # lets the browser breathe; costs nothing on the desktop


def main():
    asyncio.run(main_async())


async def main_async():
    try:
        import faulthandler
        faulthandler.enable()       # a native crash prints the Python stack instead of dying silently
    except Exception:
        pass
    open_mixer()                    # first, so pygame.init() never opens the unnamed default device
    pygame.init()
    pygame.display.set_caption("Hyperplane Heist")
    try:
        pygame.display.set_icon(make_icon())
    except pygame.error:
        pass
    # SCALED makes the desktop window resizable.  In a browser the page already scales the canvas and
    # converts clicks to canvas pixels, so SCALED would scale every click a second time (they land
    # about 17% off); the web build uses a plain window.
    scaled = 0 if WEB else getattr(pygame, "SCALED", 0)
    try:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), (scaled | pygame.RESIZABLE) if scaled else 0)
    except pygame.error:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    app = App(screen)
    if app.profile.settings.get("fullscreen") and not WEB:
        try:
            pygame.display.toggle_fullscreen()
        except Exception:
            app.profile.set_setting("fullscreen", False)
    app.start()
    await app.run()
    if not WEB:
        pygame.quit()
