# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
.venv/bin/python hyperplane_heist.py         # play
.venv/bin/python selftest.py                 # headless self-test, about 10 s, no window
.venv/bin/python tools/build_web.py          # browser build into build/web/
.venv/bin/python tools/build_web.py --serve  # browser build, served at http://localhost:8000
```

- Use `.venv/bin/python`, not `python3`. pip has no pygame 2.6.1 build for Python 3.14 (this machine's default), so `.venv` is built from Homebrew's 3.11: `/opt/homebrew/bin/python3.11 -m venv .venv && .venv/bin/python -m pip install pygame pygbag==0.9.3`. pygame is the only runtime dependency. `requirements.txt` installs pygame-ce instead on Python 3.14 and newer; the self-test passes on 3.9 and 3.11 with pygame and on 3.14 with pygame-ce. pygbag is only for the browser build.
- The desktop game has no build step, and there is no linter or test framework. `selftest.py` is one ordered script of `check(condition, message)` calls that stops at the first failure and prints `ALL OK: N checks passed`. Later sections reuse objects from earlier ones, so a single section cannot be run alone.
- Progress is saved to `~/.hyperplane_heist/save.json`. `HYPERPLANE_HEIST_SAVE=/path` moves it and an empty value disables saving; `selftest.py` points it at a temp folder, so it never touches a real save.
- `hyperplane_heist_demo.gif` is a recorded, scripted tour. The recorder script is not in this repository, so the GIF goes stale when the visuals change.

## Architecture

`hyperplane_heist.py` (desktop) and `main.py` (browser) are only entry points. The game is the `heist/` package:

- `core.py` has no pygame: the `Perceptron` (the original spec's class, `predict` / `train`), boundary geometry, unit `Motion`, layout generators, and `min_linear_errors`, an exact "how few errors can any line make" test.
- `board.py` is the vault floor every mode plays on: units, the laser, the controls, the scanner, the counter-attack and all floor animation. It reports what happened through `take_events()` and never decides wins or scores.
- `play.py` holds the rules: `CampaignScene`, `EndlessScene` (with `plan_wave` and the perks), `PauseScene`, `ResultsScene`. `levels.py` is the 12 campaign vaults as data.
- `academy.py` holds the lessons (`Page` subclasses grouped in `LESSONS`) and `QuizScene`.
- `app.py` (`App`: scene stack, fades, toasts, global keys, main loop), `menus.py`, `ui.py`, `gfx.py`, `audio.py` and `save.py` (`Profile`) are the shell around them.

Rules that hold across files:

- **Only `Perceptron` classifies and learns.** `predict` returns 1 only when `w1*x1 + w2*x2 + b > 0` (a point on the line is 0). In the game, `train` is called only by `Board.counter_attack()`: once per failed campaign lock-in, once per failed endless wave, once per Auto-Trainer press. The Academy's `Trainer` calls it too. `selftest.py` wraps `train` and counts calls to enforce this.
- **Drawn versus real boundary.** Drawing reads `Board.display_params()`, which equals the live parameters except during the snap animation after a training step. Rules always read `board.brain`.
- **The 0.01 grid.** Keys move parameters in whole 0.01 steps. Mouse drags and Q/E turns are continuous and are snapped to the grid when the gesture ends and again in `begin_scan()`, so the numbers in the HUD are exactly what gets judged.
- **Shown versus true labels.** Imposter drones look like bots until revealed. Everything that gives live feedback (wrong-side rings, HUD counts, the margin corridor, the Auto-Trainer) uses `Unit.shown_label`; only judging uses `Unit.label`. Mixing them up leaks the imposters.
- **Navigation.** Scenes switch through `App.go_*` / `App.replace()`, which import scene modules lazily; `menus`, `play` and `academy` would otherwise import each other.
- **Randomness.** Gameplay randomness comes from the scene's own `random.Random`. The daily heist seeds it from the date, so every player gets the same waves; never draw gameplay values from the effects RNGs.
- **Sound.** All sound is synthesized at start-up (about 0.4 s). `Audio` reads the profile's settings on every call and turns into a no-op when the mixer cannot start.
- **Open audio before `pygame.init()`.** `main()` calls `open_mixer()` first, which on macOS opens the current default output device by name. Opening the unnamed default device makes SDL 2.28 (bundled with pygame 2.6.1) register a "default output changed" listener that can run after its device is gone, and the game dies with a segmentation fault when the output switches (this happened with a USB audio device). A named device avoids that listener; the trade-off is that sound stays on the start-up device. `HYPERPLANE_HEIST_AUDIO=0` runs with no audio device at all.

Design decisions worth knowing before changing rules:

- Endless waves are separable by construction and store their true line. Boss waves (every 5th) are XOR, ring or sandwich layouts, where X ("no line can do it") is the right answer, or split layouts, where X is wrong. The `separable` flag comes from `min_linear_errors`, never from the layout's name.
- A moving wave shares one rigid `Motion` across all its units, so it stays separable while it moves.
- `min_linear_errors` is O(n³). It is fine for a few dozen points at wave start, but not per frame.
- The noisy vault's `allowed_errors` must equal its unavoidable errors, and every vault's three-star margin must be reachable; `selftest.py` checks both.
- The spec's controls (arrows, W / S / SPACE, ENTER) must keep working. The mouse, Q / E, F, X and T are additions.

## Browser version

`tools/build_web.py` packages `main.py` and `heist/` with pygbag 0.9.3, which runs pygame-ce on CPython 3.12 compiled to WebAssembly and loads that runtime from its CDN. The published copy is the `gh-pages` branch of the `perceptron` remote, served by GitHub Pages at https://rishikeshwalhekar49-lab.github.io/perceptron/. To republish, rebuild and replace that branch's files with `build/web/` (including `.nojekyll`).

- pygbag decides what to load from `main.py`'s own imports, so `main.py` must `import pygame` even though `heist` imports it too. `pygame.mixer` is not imported automatically in the browser; `open_mixer()` imports it.
- The main loop is async: `App.run()` awaits `asyncio.sleep(0)` every frame to hand control back to the page. Anything that blocks inside a frame freezes the tab.
- `heist.core.WEB` (true under emscripten) turns off what a page can't do: `pygame.SCALED` (the page already converts clicks to canvas pixels, so SCALED would scale them twice and clicks land about 17% off), fullscreen, and quitting. Saves go to `localStorage` through `save.web_storage()`.
- Fonts are bundled in `heist/fonts/` (DejaVu Sans Mono) because a browser has no system fonts, and the game needs glyphs such as ₁, γ and ◀ that pygame's default font lacks.
- Every action must be reachable by mouse or touch (clickable key hints, BACK buttons, Academy zones), because web players often never touch the keyboard. The "mouse and touch" section of `selftest.py` checks this.
- Test with `tools/build_web.py --serve`. A plain static server fails on localhost, because the page then fetches the runtime from `localhost:8000/cdn`. When driving the page with automated clicks, SDL reports a click at the last mouse-move position, so hover before each click; real players aren't affected.
