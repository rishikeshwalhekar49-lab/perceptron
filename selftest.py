"""Self-test for Hyperplane Heist.  No window opens: it runs on SDL's dummy drivers.

It checks the Perceptron and the boundary geometry, every campaign vault, the
board controls and the counter-attack (exactly one learning-rule step per
failed lock-in), endless wave generation and scoring, the daily heist, the
save file, the Academy's claims and quiz, and drives every screen with random
input.  It never touches your real save file.

Usage:  python selftest.py            (about a minute)
"""
import math
import os
import random
import sys
import tempfile
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
WORK = tempfile.mkdtemp(prefix="heist-selftest-")
os.environ["HYPERPLANE_HEIST_SAVE"] = os.path.join(WORK, "save.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
screen = pygame.display.set_mode((1200, 720))

from heist import academy, core, menus, play  # noqa: E402
from heist.app import App  # noqa: E402
from heist.board import FLOOR, LEARNING_RATE, Board, Unit  # noqa: E402
from heist.core import (Perceptron, boundary_endpoints, bounds_corners, clip_to_side, count_errors,  # noqa: E402
                        line_through, margin, min_linear_errors, polygon_centroid, rotate_about, signed_distance)
from heist.levels import LEVELS  # noqa: E402
from heist.save import CAMPAIGN_SIZE, Profile  # noqa: E402

DT = 1 / 60
checks = 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(msg)


def close(a, b, tol=1e-9):
    return math.isclose(a, b, abs_tol=tol)


def section(name):
    print("·", name)


def best_line(points):
    """(margin, (w1, w2, b)) of the widest separating line, |w| = 0.5, by angle search."""
    best = (-1e9, None)
    for k in range(1440):
        th = k * math.tau / 1440
        c, s = math.cos(th), math.sin(th)
        pos = [c * x + s * y for x, y, label in points if label == 1]
        neg = [c * x + s * y for x, y, label in points if label == 0]
        m = (min(pos) - max(neg)) / 2
        if m > best[0]:
            best = (m, (0.5 * c, 0.5 * s, -0.5 * (min(pos) + max(neg)) / 2))
    return best


# ---------------------------------------------------------------- the Perceptron
section("perceptron")
p = Perceptron(random.Random(1))
check(len(p.weights) == 2 and all(isinstance(w, float) for w in p.weights) and isinstance(p.bias, float),
      "weights: two floats, bias: float")
for seed in range(200):
    q = Perceptron(random.Random(seed))
    check(all(abs(v) <= 0.5 for v in q.weights + [q.bias]), "small random start")
p.set_params(1.0, -2.0, 0.5)
check(p.predict(1, 0) == 1 and p.predict(0, 1) == 0, "predict uses w1*x1 + w2*x2 + b > 0")
p.set_params(1.0, 1.0, -2.0)
check(p.predict(1, 1) == 0, "exactly on the line -> 0")
p.set_params(1.0, 1.0, 0.0)
check(p.train(2.0, 3.0, 1, 0.1) is False and p.params == (1.0, 1.0, 0.0), "no update when right")
check(p.train(2.0, 3.0, 0, 0.1) is True, "update when wrong")
check(close(p.weights[0], 0.8) and close(p.weights[1], 0.7) and close(p.bias, -0.1), "rule, target 0")
p.set_params(-1.0, -1.0, 0.0)
p.train(2.0, 3.0, 1, 0.5)
check(close(p.weights[0], 0.0) and close(p.weights[1], 0.5) and close(p.bias, 0.5), "rule, target 1")

# ------------------------------------------------------------------- geometry
section("geometry")
rng = random.Random(5)
for _ in range(4000):
    w1, w2, b = rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-30, 30)
    ends = boundary_endpoints(w1, w2, b)
    if ends:
        for x1, x2 in ends:
            check(abs(w1 * x1 + w2 * x2 + b) < 1e-6, "endpoint lies on the line")
            check(0 <= x1 <= 10 and 0 <= x2 <= 10, "endpoint inside the floor")
    pos = clip_to_side(bounds_corners(), w1, w2, b, True)
    neg = clip_to_side(bounds_corners(), w1, w2, b, False)
    a_pos = polygon_centroid(pos)[1] if len(pos) >= 3 else 0.0
    a_neg = polygon_centroid(neg)[1] if len(neg) >= 3 else 0.0
    check(abs(a_pos + a_neg - 100.0) < 1e-6, "zones tile the floor")
    n1, n2, nb = core.from_pose(*core.to_pose(w1, w2, b))
    norm = math.hypot(w1, w2)
    check(abs(n1 - w1 / norm) < 1e-9 and abs(nb - b / norm) < 1e-9, "pose round trip")
    pivot = core.project_onto_line(w1, w2, b, 5.0, 5.0)
    r = rotate_about(w1, w2, b, rng.uniform(-1, 1), pivot)
    check(abs(r[0] * pivot[0] + r[1] * pivot[1] + r[2]) < 1e-6, "rotation keeps the pivot on the line")
    t = core.translate_line(w1, w2, b, 1.5)
    check(abs(signed_distance(*t, *pivot) + 1.5) < 1e-6, "translate moves the line by the distance")
    f = core.flip_params(w1, w2, b)
    check((boundary_endpoints(*f) is None) == (ends is None), "flip keeps the line")
check(boundary_endpoints(0.0, 0.0, 1.0) is None and boundary_endpoints(1.0, 1.0, 5.0) is None, "no line cases")
line = line_through((1, 1), (4, 5), ref=(0.6, -0.8), norm=0.5)
check(abs(math.hypot(line[0], line[1]) - 0.5) < 1e-9 and line[0] * 0.6 + line[1] * -0.8 > 0, "line_through keeps w")
check(abs(line[0] * 1 + line[1] * 1 + line[2]) < 1e-9 and abs(line[0] * 4 + line[1] * 5 + line[2]) < 1e-9,
      "line_through passes both points")
check(min_linear_errors([(0, 0, 0), (1, 1, 0), (0, 1, 1), (1, 0, 1)])[0] == 1, "XOR needs one error")
check(min_linear_errors([(0, 0, 0), (1, 1, 1)])[0] == 0, "two points are separable")
slack, errors = margin(-0.4, -0.4, 4.2, [(2, 2, 1), (8, 7, 0)])
check(errors == 0 and abs(slack - 1.8 / math.hypot(0.4, 0.4)) < 1e-9, "margin = closest unit (the drone)")

# --------------------------------------------------------------- generators
section("layout generators")
for n in range(1, 31):
    count, gap = min(8, 3 + n // 2), max(0.6, 2.4 - 0.12 * (n - 1))
    for trial in range(6):
        pts, line = core.separable_layout(rng, count, count, gap, 1.0 + 0.03 * n)
        check(count_errors(*line, pts) == 0, "generated line separates its layout")
        check(margin(*line, pts)[0] >= gap / 2 - 1e-9, "generated layout keeps its gap")
        check(all(0.7 <= x <= 9.3 and 0.7 <= y <= 9.3 for x, y, _ in pts), "inside the floor")
for _ in range(25):
    for pts in (core.xor_layout(rng, 2), core.ring_layout(rng, 3, 7), core.sandwich_layout(rng, 4, 6)):
        check(min_linear_errors(pts)[0] > 0, "boss layouts are not separable")
    pts, line, flipped = core.noisy_layout(rng, 5, 5, 1.5, flips=1)
    check(min_linear_errors(pts)[0] == 1, "one faulty sensor = one unavoidable error")

# ------------------------------------------------------------------- vaults
section("campaign vaults")
check(len(LEVELS) == CAMPAIGN_SIZE, "12 vaults")
for level in LEVELS:
    pts = level.points(0.0)
    errors, _ = min_linear_errors(pts)
    if level.impossible:
        check(errors > 0, level.key + ": the impossible vault really is")
        continue
    check(errors == level.allowed_errors, level.key + ": exactly the allowed errors are unavoidable")
    if level.allowed_errors == 0:
        check(best_line(pts)[0] >= level.margin_goal, level.key + ": the 3-star margin is reachable")
    if level.start:
        check(count_errors(*level.start, pts) > 0, level.key + ": the start is not already solved")
    if level.key == "patrol":
        route = []
        for x, y, label, motion, _ in level.units:
            route += [(*motion.position(x, y, k / 20 * motion.period), label) for k in range(21)]
        check(min_linear_errors(route)[0] == 0 and best_line(route)[0] >= level.margin_goal,
              "patrol routes are separable with the goal margin")
    for t in (0.0, 7.0, 13.0, 29.0):
        check(all(0.5 <= x <= 9.5 and 0.5 <= y <= 9.5 for x, y, _ in level.points(t)), level.key + ": on floor")


# ------------------------------------------------------------- app helpers
def make_app(audio=False):
    app = App(screen, profile=Profile(os.path.join(WORK, "p%d.json" % random.randrange(10 ** 9))), audio=audio)
    app.profile.settings["shake"] = False
    app.start()
    run(app, 5)
    return app


def run(app, frames, draw=False):
    for _ in range(frames):
        app.update(DT)
        if draw:
            app.draw()
    while app.fade is not None:
        app.update(DT)


def key(app, k, down=True, mod=0, unicode=""):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP, key=k, mod=mod, unicode=unicode))


def tap(app, k, unicode=""):
    key(app, k, True, unicode=unicode)
    key(app, k, False)


def start_vault(app, index):
    app.go_campaign(index)
    run(app, 3)
    scene = app.top
    tap(app, pygame.K_RETURN)
    tap(app, pygame.K_RETURN)
    run(app, 2)
    return scene


train_calls = []
_original_train = Perceptron.train


def counting_train(self, x1, x2, target_label, learning_rate):
    train_calls.append((x1, x2, target_label, learning_rate))
    return _original_train(self, x1, x2, target_label, learning_rate)


Perceptron.train = counting_train

# --------------------------------------------------------------- board controls
section("board controls")
app = make_app()
board = Board(app, units=[Unit(2, 2, 1), Unit(8, 8, 0)], params=(0.3, 0.2, -1.0))


def bkey(k, down=True):
    board.handle_event(pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP, key=k, mod=0))


def btap(k):
    bkey(k)
    bkey(k, False)


for k, index, delta in ((pygame.K_RIGHT, 0, 0.01), (pygame.K_LEFT, 0, -0.01), (pygame.K_UP, 1, 0.01),
                        (pygame.K_DOWN, 1, -0.01), (pygame.K_w, 2, 0.01), (pygame.K_s, 2, -0.01),
                        (pygame.K_SPACE, 2, 0.01)):
    before = board.params
    btap(k)
    for i in range(3):
        check(close(board.params[i], before[i] + (delta if i == index else 0.0)), "each key moves only its parameter")
before = board.params
bkey(pygame.K_LSHIFT)
btap(pygame.K_SPACE)
bkey(pygame.K_LSHIFT, False)
check(close(board.params[2], before[2] - 0.01), "SHIFT + SPACE lowers b")
before = board.params
bkey(pygame.K_RIGHT)
for _ in range(60):
    board.update(DT)
bkey(pygame.K_RIGHT, False)
check(0.45 < board.params[0] - before[0] < 0.9, "holding sweeps")
before = board.params
btap(pygame.K_f)
check(all(close(a, -b) for a, b in zip(board.params, before)), "F flips every sign")
before = board.params
btap(pygame.K_q)
check(close(math.hypot(*board.params[:2]), math.hypot(*before[:2]), 0.01), "Q turns without rescaling w")
check(all(close(v, round(v, 2)) for v in board.params), "a turn snaps to the 0.01 grid on release")
board.locks = {"w1", "w2"}
before = board.params
for k in (pygame.K_RIGHT, pygame.K_UP, pygame.K_q, pygame.K_f):
    btap(k)
check(board.params == before, "locked weights do not move")
btap(pygame.K_w)
check(close(board.params[2], before[2] + 0.01), "the unlocked bias still moves")
board.locks = set()
board.set_params(0.3, 0.2, -2.0)
a, e = board.segment_now()
w_before = board.params[:2]
fixed = board.vp.to_world(*e)
board.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(a[0]), int(a[1])), button=1))
board.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(FLOOR.centerx, FLOOR.top + 40), rel=(0, 0),
                                      buttons=(1, 0, 0)))
board.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(FLOOR.centerx, FLOOR.top + 40), button=1))
w1, w2, b = board.params
check(abs(w1 * fixed[0] + w2 * fixed[1] + b) < 0.05, "an end drag pivots on the other end")
check(w1 * w_before[0] + w2 * w_before[1] > 0, "dragging keeps the safe side")
seg = board.segment_now()
mid = (int((seg[0][0] + seg[1][0]) / 2), int((seg[0][1] + seg[1][1]) / 2))
board.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=mid, button=1))
board.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(mid[0] + 60, mid[1]), rel=(0, 0), buttons=(1, 0, 0)))
board.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(mid[0] + 60, mid[1]), button=1))
check(close(board.params[0], w1) and close(board.params[1], w2) and not close(board.params[2], b),
      "a beam drag changes only the bias")

# ------------------------------------------------------- scan and counter-attack
section("scan and counter-attack")
board = Board(app, params=(0.3, 0.3, -3.0))
board.set_units([Unit(2, 2, 1), Unit(3, 1, 1), Unit(8, 7, 0), Unit(9, 9, 0)], animate=False)
board.begin_scan()
judged = []
for _ in range(120):
    board.update(DT)
    judged += [(ev[1], ev[2]) for ev in board.take_events() if ev[0] == "judge"]
check(len(judged) == 4 and len({id(u) for u, _ in judged}) == 4, "every unit judged exactly once")
check(all(ok == (board.brain.predict(u.x, u.y) == u.label) for u, ok in judged), "verdict = predict")
wrong = [u for u, ok in judged if not ok]
check(len(wrong) == 4, "the flipped line gets every unit wrong")
train_calls.clear()
old = board.params
target = wrong[0]
board.counter_attack(target)
check(len(train_calls) == 1, "one counter-attack = one training step")
error = target.label - (1 if old[0] * target.jx + old[1] * target.jy + old[2] > 0 else 0)
expected = (old[0] + LEARNING_RATE * error * target.jx, old[1] + LEARNING_RATE * error * target.jy,
            old[2] + LEARNING_RATE * error)
check(all(close(a, b, 1e-12) for a, b in zip(board.params, expected)), "the snap is the learning-rule update")
for _ in range(60):
    board.update(DT)
check(board.phase == "frozen" and any(ev[0] == "snap_done" for ev in board.take_events()), "the snap finishes")
check(board.display_params() == board.params, "after the snap the drawn laser is the real one")

# ------------------------------------------------------------------ campaign
section("campaign flows")
app = make_app()
for index, level in enumerate(LEVELS):
    scene = start_vault(app, index)
    check(isinstance(scene, play.CampaignScene) and scene.state == "play", level.key + ": intro, then play")
    scene.board.motion_speed = 0.0                  # freeze patrols and the carousel for exact checks
    pts = scene.board.points()
    train_calls.clear()
    keep = [p for p in pts if not (level.allowed_errors and p[2] == 1 and p[0] > 6)]     # drop the outlier
    if level.impossible:
        scene.board.set_params(0.3, 0.3, -3.0)
    else:
        scene.board.set_params(*core.flip_params(*best_line(keep)[1]))
    tap(app, pygame.K_RETURN)
    run(app, 200)
    check(scene.alarms == 1 and len(train_calls) == 1, level.key + ": a failed lock-in = one alarm, one step")
    if level.impossible:
        tap(app, pygame.K_x)
        run(app, 140)
        check(scene.state == "won" and scene.result["proof"] and scene.result["stars"] == 2, "X proves XOR")
        continue
    tap(app, pygame.K_x)
    check(scene.alarms == 2, level.key + ": X on a solvable vault costs an alarm")
    scene.board.set_params(*best_line(keep)[1])
    tap(app, pygame.K_RETURN)
    run(app, 200)
    check(scene.state == "won", level.key + ": the widest line cracks it")
    check(scene.result["stars"] == 1, level.key + ": two alarms = one star")
check(app.profile.campaign_cleared() == len(LEVELS) and app.profile.has("campaign"), "every vault recorded")
check(app.profile.has("and_gate") and app.profile.has("minsky"), "vault achievements")
scene = start_vault(app, 0)
scene.board.set_params(-0.40, -0.40, 4.20)
tap(app, pygame.K_RETURN)
run(app, 120)
check(scene.state == "won" and scene.result["stars"] == 3, "a clean, wide lock-in = 3 stars")
check(app.profile.has("ghost") and app.profile.has("wide"), "ghost and wide berth")
scene = start_vault(app, 1)
train_calls.clear()
for _ in range(LEVELS[1].max_alarms):
    scene.board.set_params(-0.4, -0.4, 1.0)
    tap(app, pygame.K_RETURN)
    run(app, 200)
check(scene.state == "failed" and len(train_calls) == LEVELS[1].max_alarms, "lockdown after the last alarm")

# -------------------------------------------------------------------- endless
section("endless waves")
for seed in range(12):
    r = random.Random(seed)
    for n in range(1, 31):
        plan = play.plan_wave(n, r, {})
        pts = [(u.x, u.y, u.label) for u in plan.units]
        check(plan.separable == (min_linear_errors(pts)[0] == 0), "the separable flag is honest")
        check(plan.boss == (n % 5 == 0), "a boss every 5th wave")
        if plan.separable:
            check(count_errors(*plan.line, pts) == 0, "the true line separates the wave")
        for t in (0.0, 1.7, 4.4, 9.1, 20.0):
            for u in plan.units:
                x, y = u.motion.position(u.bx, u.by, t) if u.motion else (u.bx, u.by)
                check(0.5 <= x <= 9.5 and 0.5 <= y <= 9.5, "moving units stay on the floor")
                if u.motion is not None:
                    moved = [(*u2.motion.position(u2.bx, u2.by, t), u2.label) for u2 in plan.units]
                    check(min_linear_errors(moved)[0] == 0 or not plan.separable, "moving waves stay separable")
                    break


def solve_wave(e):
    e.board.motion_speed = 0.0
    pts = e.board.points()
    e.board.set_params(*best_line(pts)[1])


app = make_app()
app.go_endless(False)
run(app, 3)
e = app.top
check(isinstance(e, play.EndlessScene) and e.state == "sector", "endless opens on the sector card")
saw_proof = False
for wave in range(1, 13):
    for _ in range(100):
        if e.state == "play":
            break
        if e.state in ("sector", "perk"):
            tap(app, pygame.K_RETURN)
        run(app, 20)
    check(e.wave == wave and e.state == "play", "waves advance one by one")
    if e.plan.separable:
        solve_wave(e)
        score = e.score
        tap(app, pygame.K_RETURN)
        run(app, 80)
        check(e.score > score and e.state in ("celebrate", "exit"), "a perfect wave scores")
    else:
        shields = e.shields
        tap(app, pygame.K_x)
        saw_proof = True
        check(e.state == "proof" and e.shields == min(5, shields + 1), "X on a boss with no line = +1 shield")
    run(app, 120)
check(app.profile.has("wave10") and (app.profile.has("proof") or not saw_proof), "run achievements")
for _ in range(100):
    if e.state == "play":
        break
    tap(app, pygame.K_RETURN)
    run(app, 20)
if e.plan.separable:
    shields = e.shields
    tap(app, pygame.K_x)
    check(e.shields == shields - 1 and e.board.ghost is not None, "a wrong X costs a shield and shows the line")
train_calls.clear()
for _ in range(20):
    for _ in range(100):
        if not isinstance(app.top, play.EndlessScene) or e.state in ("play", "gameover"):
            break
        tap(app, pygame.K_RETURN)
        run(app, 20)
    if not isinstance(app.top, play.EndlessScene) or e.state == "gameover":
        break
    e.board.motion_speed = 0.0
    e.board.set_params(*core.flip_params(*best_line(e.board.points())[1]))
    tap(app, pygame.K_RETURN)
    run(app, 160)
run(app, 260)
check(isinstance(app.top, play.ResultsScene), "out of shields -> results")
check(e.shields == 0 and len(train_calls) >= 1, "each failed wave retrains once")
res = app.top
if res.entry is not None:
    for ch in "QED":
        tap(app, getattr(pygame, "K_" + ch.lower()), ch)
    tap(app, pygame.K_RETURN)
    check(app.profile.leaderboard()[res.position]["name"] == "QED", "initials saved to the leaderboard")
app.go_endless(True)
run(app, 3)
d = app.top
for _ in range(600):
    if not isinstance(app.top, play.EndlessScene):
        break
    if d.state in ("sector", "perk", "complete"):
        tap(app, pygame.K_RETURN)
    elif d.state == "play":
        if d.plan.separable:
            solve_wave(d)
            tap(app, pygame.K_RETURN)
        else:
            tap(app, pygame.K_x)
    run(app, 30)
check(isinstance(app.top, play.ResultsScene) and app.top.summary["completed"], "the daily ends after 10 waves")
check(app.profile.daily_record() is not None and app.profile.has("daily"), "the daily is recorded")
d1 = play.EndlessScene(app, daily=True)
d2 = play.EndlessScene(app, daily=True)
d1.start_wave()
d2.start_wave()
check([(u.bx, u.by, u.label) for u in d1.plan.units] == [(u.bx, u.by, u.label) for u in d2.plan.units],
      "the daily heist is the same for everyone")

# ---------------------------------------------------------------- save file
section("save file")
path = os.path.join(WORK, "roundtrip.json")
prof = Profile(path)
prof.record_level("first_night", 2, 12.5, 1.4)
prof.add_xp(350)
prof.unlock("ghost")
for score in (500, 900, 100, 1200, 50, 700, 300, 800, 950, 60, 20, 2000):
    prof.add_score("ABC", score, 3)
prof.save()
again = Profile(path)
check(again.stars("first_night") == 2 and again.has("ghost") and again.xp == prof.xp, "save round trip")
scores = [row["score"] for row in again.leaderboard()]
check(scores == sorted(scores, reverse=True) and len(scores) == 10 and 20 not in scores, "top 10, sorted")
check(again.skin_unlocked("emerald") and not again.skin_unlocked("gold"), "skin unlock rules")
with open(path, "w") as handle:
    handle.write("{not json")
broken = Profile(path)
with open(path + ".bak") as handle:
    check(broken.xp == 0 and handle.read() == "{not json", "a corrupt save is set aside as .bak")
check(Profile(None).path is None, "a profile without a path never writes")

# ------------------------------------------------------------------- academy
section("academy")
tr = academy.Trainer(academy.TRAIN_POINTS, 0.1, academy.TRAIN_START)
check(tr.run() and count_errors(*tr.brain.params, academy.TRAIN_POINTS) == 0, "the trainer converges")
noisy = academy.Trainer(academy.NOISY_POINTS, 0.1)
noisy.run(max_steps=5000)
check(not noisy.converged, "noisy data never converges")
mistakes = set()
radius, gamma, bound = academy.mistake_bound(academy.TRAIN_POINTS, academy.TRUE_LINE)
for lr in (0.01, 0.1, 1.0, 3.7):
    z = academy.Trainer(academy.TRAIN_POINTS, lr, (0.0, 0.0, 0.0))
    z.run()
    mistakes.add(z.updates)
    check(z.updates <= bound, "Novikoff's bound holds")
check(len(mistakes) == 1, "from zero, the learning rate does not change the mistakes")
check(count_errors(*academy.TRUE_LINE, academy.TRAIN_POINTS) == 0, "the lesson's true line separates its data")
qr = random.Random(3)
for _ in range(400):
    for kind in ("classify", "update", "slope", "distance"):
        prompt, options, why = academy.generated_question(qr, kind)
        check(len(options) == 4 and len(set(options)) == 4, "every generated question has 4 distinct options")
for question, options, why in academy.BANK:
    check(len(options) == 4 and len(set(options)) == 4, "bank questions have 4 distinct options")

# ------------------------------------------------------------ every screen
section("every screen, random input")
app = make_app(audio=True)
keys = [pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s, pygame.K_SPACE,
        pygame.K_q, pygame.K_e, pygame.K_f, pygame.K_x, pygame.K_t, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
        pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_TAB, pygame.K_p, pygame.K_r, pygame.K_a, pygame.K_LSHIFT]
mash = random.Random(99)
openers = [lambda: app.go_menu(), lambda: app.go_levels(0), lambda: app.go_endless(False),
           lambda: app.go_endless(True), lambda: app.go_academy(), lambda: app.go_quiz(),
           lambda: app.replace(menus.ProfileScene(app)), lambda: app.replace(menus.SettingsScene(app)),
           lambda: app.replace(menus.RecordsScene(app))]
openers += [(lambda i=i: app.go_campaign(i)) for i in range(len(LEVELS))]
openers += [(lambda i=i: app.replace(academy.LessonScene(app, i))) for i in range(len(academy.LESSONS))]
types = set()
for opener in openers:
    opener()
    run(app, 2)
    down = set()
    for frame in range(500):
        if mash.random() < 0.12:
            k = mash.choice(keys)
            if k in down:
                key(app, k, False)
                down.discard(k)
            else:
                key(app, k, True, unicode=pygame.key.name(k)[:1])
                down.add(k)
        if mash.random() < 0.05:
            pos = (mash.randrange(1200), mash.randrange(720))
            kind = mash.choice((pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP))
            if kind == pygame.MOUSEMOTION:
                app.handle_event(pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(1, 0, 0)))
            else:
                app.handle_event(pygame.event.Event(kind, pos=pos, button=mash.choice((1, 1, 3))))
        app.update(mash.choice((DT, DT, DT, 0.05, 0.001)))
        if frame % 4 == 0:
            app.draw()
        types.add(type(app.top).__name__)
        if isinstance(app.top, menus.SettingsScene):
            app.top.confirm = 0                     # never let the mash erase progress
    for k in down:
        key(app, k, False)
check({"MainMenuScene", "LevelSelectScene", "CampaignScene", "EndlessScene", "AcademyScene", "LessonScene",
       "QuizScene", "ProfileScene", "SettingsScene", "RecordsScene"} <= types, "random input visited every screen")
print("  screens reached:", ", ".join(sorted(types)))

# ---------------------------------------------------------------- frame cost
section("frame cost")
app = make_app(audio=True)
for name, opener in (("menu", lambda: app.go_menu()), ("campaign", lambda: app.go_campaign(6)),
                     ("endless + lens", lambda: app.go_endless(False)),
                     ("heatmap lesson", lambda: app.replace(academy.LessonScene(app, 1)))):
    opener()
    run(app, 3)
    if isinstance(app.top, play.CampaignScene):
        tap(app, pygame.K_RETURN)
        tap(app, pygame.K_RETURN)
    if isinstance(app.top, play.EndlessScene):
        app.top.perks["lens"] = 1
        run(app, 30)
        tap(app, pygame.K_RETURN)
        for _ in range(20):
            if app.top.state == "play":
                break
            run(app, 10)
        app.top.board.show_z = True
    run(app, 60)
    start = time.perf_counter()
    for i in range(120):
        app.update(DT)
        app.draw()
    cost = (time.perf_counter() - start) / 120 * 1000
    print("  %-15s %.2f ms per frame" % (name, cost))
    check(cost < 16.0, name + " fits in a 60 fps frame")

print("ALL OK: %d checks passed" % checks)
