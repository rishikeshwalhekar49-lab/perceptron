"""Hyperplane Heist: the base class every screen derives from."""


class Scene:
    music = None            # "menu", "game", "academy", or None to keep the current track
    overlay = False         # True: the scene underneath is drawn first (pause menus)
    text_input = False      # True: letter keys belong to the scene (global M = mute is off)

    def __init__(self, app):
        self.app = app
        self.gfx = app.gfx
        self.audio = app.audio
        self.profile = app.profile
        self.time = 0.0

    def enter(self):
        pass

    def leave(self):
        pass

    def handle_event(self, event):
        return False

    def update(self, dt):
        self.time += dt

    def draw(self, surf):
        pass
