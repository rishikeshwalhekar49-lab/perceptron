"""Build the browser version of Hyperplane Heist with pygbag (pygame compiled to WebAssembly).

    .venv/bin/python -m pip install pygbag==0.9.3
    .venv/bin/python tools/build_web.py            # build into build/web/
    .venv/bin/python tools/build_web.py --serve    # build and serve at http://localhost:8000

The result in build/web/ (index.html, hyperplane-heist.apk, favicon.png,
preview.png) is a static site that GitHub Pages, itch.io or any web server can
host.  The page loads the Python runtime from pygbag's CDN, so players need to
be online.  Served from localhost, though, the page fetches the runtime from
pygbag's own server on port 8000, so test with --serve rather than a plain web
server.

The page comes from tools/web/index.tmpl: the branded loading screen and the
tags for link previews.  preview.png, the card that LinkedIn and others show
for a shared link, is drawn here by the game's own code, so it never goes stale.
Only main.py and heist/ go into the game archive: no demo GIF, no tests.
"""
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "build", "web-src")
APP = os.path.join(WORK, "hyperplane-heist")
OUT = os.path.join(ROOT, "build", "web")
TEMPLATE = os.path.join(ROOT, "tools", "web", "index.tmpl")
SITE_URL = "https://rishikeshwalhekar49-lab.github.io/perceptron/"     # where the gh-pages branch is served
CARD_SIZE = (1200, 630)                                                 # the size link previews expect


def stage_template():
    """tools/web/index.tmpl with the site's address filled in; pygbag fills in the rest."""
    with open(TEMPLATE, encoding="utf-8") as source:
        page = source.read()
    staged = os.path.join(WORK, "index.tmpl")
    with open(staged, "w", encoding="utf-8") as target:
        target.write(page.replace("{{heist.site_url}}", SITE_URL))
    return staged


def widest_line(points, scale=0.4):
    """The line with the widest margin that puts every label-1 point on its positive side.

    It tries every tenth of a degree, then scales the result to HUD-sized numbers on the 0.01 grid.
    """
    best = None
    for step in range(3600):
        angle = math.radians(step / 10.0)
        w1, w2 = math.cos(angle), math.sin(angle)
        low = min(w1 * x + w2 * y for x, y, label in points if label == 1)
        high = max(w1 * x + w2 * y for x, y, label in points if label == 0)
        if best is None or low - high > best[0]:
            best = (low - high, w1, w2, -(low + high) / 2.0)
    gap, w1, w2, b = best
    if gap <= 0:
        raise ValueError("no straight line separates these points")
    return round(w1 * scale, 2), round(w2 * scale, 2), round(b * scale, 2)


def render_preview(path):
    """Draw preview.png: the first vault, solved with its widest-margin laser, beside the title."""
    import pygame
    from heist.app import App
    from heist.board import FLOOR
    from heist.core import Perceptron
    from heist.gfx import CYAN, GOLD, GREEN, SCREEN_H, SCREEN_W, TEXT, TEXT_DIM, make_backdrop
    from heist.play import CampaignScene
    from heist.save import Profile

    app = App(pygame.display.set_mode((SCREEN_W, SCREEN_H)), profile=Profile(path=None, autosave=False),
              audio=False)
    app.profile.settings["shake"] = False
    app.start()
    app.replace(CampaignScene(app, 0), fade=False)
    scene = app.top
    for _ in range(2):                                  # finish the intro text, then start, as a player would
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r",
                                            scancode=0))
    scene.coach = scene.coach_note = None               # no tutorial bubble on the card
    params = widest_line(scene.board.points())
    scene.board.set_params(*params)
    judge = Perceptron()
    judge.set_params(*params)
    if any(judge.predict(x, y) != label for x, y, label in scene.board.points()):
        raise RuntimeError("the preview's laser puts a unit on the wrong side")
    for _ in range(150):                                # let the units arrive and the glow settle
        app.update(1 / 60.0)
    app.draw()

    gfx = app.gfx
    card = make_backdrop(*CARD_SIZE)
    floor = app.canvas.subsurface(FLOOR.inflate(6, 6)).copy()      # the floor and its frame, no HUD text
    card.blit(pygame.transform.smoothscale(floor, (566, 566)), (32, 32))
    cx = 900                                            # the centre of the column right of the floor
    gfx.draw_banner(card, "HYPERPLANE HEIST", (cx, 150), TEXT, CYAN, gfx.font(50, True))
    gfx.text(card, gfx.font(22), "A vault guarded by one perceptron.", (cx, 214), TEXT, "center")
    gfx.text(card, gfx.font(30, True), "w₁·x₁ + w₂·x₂ + b = 0", (cx, 300), GOLD, "center")
    gfx.text(card, gfx.font(19), "12 vaults · endless · daily · academy", (cx, 372), TEXT_DIM, "center")
    label = gfx.font(20, True)
    words = "▶  PLAY FREE IN YOUR BROWSER"
    pill = pygame.Rect(0, 0, label.size(words)[0] + 56, 56)
    pill.center = (cx, 470)
    pygame.draw.rect(card, (12, 40, 30), pill, border_radius=28)
    pygame.draw.rect(card, GREEN, pill, 2, border_radius=28)
    gfx.text(card, label, words, pill.center, GREEN, "center")
    pygame.image.save(card, path)


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(os.path.join(APP, "static"))          # pygbag copies static/ next to index.html, not into the archive
    shutil.copy(os.path.join(ROOT, "main.py"), APP)
    shutil.copytree(os.path.join(ROOT, "heist"), os.path.join(APP, "heist"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    template = stage_template()

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["HYPERPLANE_HEIST_AUDIO"] = "0"
    sys.path.insert(0, ROOT)
    import pygame
    from heist.gfx import make_icon
    pygame.init()
    icon = os.path.join(APP, "favicon.png")
    pygame.image.save(pygame.transform.smoothscale(make_icon(), (32, 32)), icon)
    render_preview(os.path.join(APP, "static", "preview.png"))
    pygame.quit()

    pygbag = [sys.executable, "-m", "pygbag", "--app_name", "hyperplane-heist", "--title", "Hyperplane Heist",
              "--width", "1200", "--height", "720", "--icon", icon, "--template", template]
    if "--serve" in sys.argv[1:]:
        print("Serving the browser build at http://localhost:8000 (Ctrl+C stops it)")
        try:
            subprocess.run(pygbag + [APP])          # without --build, pygbag builds and then serves
        except KeyboardInterrupt:
            pass
        return
    subprocess.run(pygbag + ["--build", APP], check=True)
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(APP, "build", "web"), OUT)
    open(os.path.join(OUT, ".nojekyll"), "w").close()   # GitHub Pages: serve the files as they are
    for name in sorted(os.listdir(OUT)):
        print("  build/web/{:<28} {:>9,} bytes".format(name, os.path.getsize(os.path.join(OUT, name))))
    print("Browser build ready in build/web/. To test it:  .venv/bin/python tools/build_web.py --serve")


if __name__ == "__main__":
    main()
