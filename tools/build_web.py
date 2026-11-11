"""Build the browser version of Hyperplane Heist with pygbag (pygame compiled to WebAssembly).

    .venv/bin/python -m pip install pygbag==0.9.3
    .venv/bin/python tools/build_web.py            # build into build/web/
    .venv/bin/python tools/build_web.py --serve    # build and serve at http://localhost:8000

The result in build/web/ (index.html, hyperplane-heist.apk, favicon.png) is a
static site that GitHub Pages, itch.io or any web server can host.  The page
loads the Python runtime from pygbag's CDN, so players need to be online.
Served from localhost, though, the page fetches the runtime from pygbag's own
server on port 8000, so test with --serve rather than a plain web server.
Only main.py and heist/ are packaged: no demo GIF, no tests.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "build", "web-src")
APP = os.path.join(WORK, "hyperplane-heist")
OUT = os.path.join(ROOT, "build", "web")


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(APP)
    shutil.copy(os.path.join(ROOT, "main.py"), APP)
    shutil.copytree(os.path.join(ROOT, "heist"), os.path.join(APP, "heist"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, ROOT)
    import pygame
    from heist.gfx import make_icon
    pygame.init()
    icon = os.path.join(APP, "favicon.png")
    pygame.image.save(pygame.transform.smoothscale(make_icon(), (32, 32)), icon)
    pygame.quit()

    pygbag = [sys.executable, "-m", "pygbag", "--app_name", "hyperplane-heist", "--title", "Hyperplane Heist",
              "--width", "1200", "--height", "720", "--icon", icon]
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
