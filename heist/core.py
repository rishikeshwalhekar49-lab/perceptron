"""Hyperplane Heist: the maths, with no pygame in sight.

Holds the Perceptron, the geometry of its decision boundary, how units move,
and the generators that lay out units for the game modes and the Academy.
Everything here is deterministic for a given random.Random, so it can be
tested on its own.
"""
import math
import random
import sys

WEB = sys.platform == "emscripten"          # running in a browser (pygbag / WebAssembly)
WORLD_LO, WORLD_HI = 0.0, 10.0
WORLD_CENTRE = (5.0, 5.0)
FLOOR_BOUNDS = (WORLD_LO, WORLD_HI, WORLD_LO, WORLD_HI)     # (x1 min, x1 max, x2 min, x2 max)
PARAM_STEP = 0.01               # one key tap changes a parameter by this much
SAFE_BOX = (0.7, 9.3)           # units are placed inside this square so their sprites stay on the floor


# ---------------------------------------------------------------------------
# The Perceptron
# ---------------------------------------------------------------------------
class Perceptron:
    """A single perceptron with two inputs: the vault's entire security brain.

    Its decision boundary is the line  w1*x1 + w2*x2 + b = 0.
    """

    def __init__(self, rng=None):
        rng = rng or random
        # Small random starting values.
        self.weights = [rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)]     # [w1, w2]
        self.bias = rng.uniform(-0.5, 0.5)                                  # b

    def activation(self, x1, x2):
        """The weighted sum z = w1*x1 + w2*x2 + b."""
        return self.weights[0] * x1 + self.weights[1] * x2 + self.bias

    def predict(self, x1, x2):
        """Return 1 (Safe) if w1*x1 + w2*x2 + b > 0, else 0 (Alarm)."""
        return 1 if self.activation(x1, x2) > 0 else 0

    def train(self, x1, x2, target_label, learning_rate):
        """One step of the perceptron learning rule.

        If the prediction is wrong:
            w_i = w_i + learning_rate * (target_label - predict_label) * x_i
            b   = b   + learning_rate * (target_label - predict_label)
        Returns True if the parameters changed.
        """
        predict_label = self.predict(x1, x2)
        if predict_label == target_label:
            return False
        error = target_label - predict_label          # +1 or -1
        self.weights[0] += learning_rate * error * x1
        self.weights[1] += learning_rate * error * x2
        self.bias += learning_rate * error
        return True

    # Conveniences for the game. They are not part of the learning rule.
    @property
    def params(self):
        return self.weights[0], self.weights[1], self.bias

    def set_params(self, w1, w2, b):
        self.weights = [float(w1), float(w2)]
        self.bias = float(b)

    def copy(self):
        twin = Perceptron.__new__(Perceptron)
        twin.weights = list(self.weights)
        twin.bias = self.bias
        return twin


# ---------------------------------------------------------------------------
# Small maths helpers
# ---------------------------------------------------------------------------
def lerp(a, b, t):
    return a + (b - a) * t


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def inv_lerp(a, b, value):
    return 0.0 if b == a else (value - a) / (b - a)


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t):
    t = clamp(t, 0.0, 1.0)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def ease_out_back(t, overshoot=1.70158):
    t = clamp(t, 0.0, 1.0) - 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0


def spring(t):
    """0 -> 1 with an overshoot: how the laser snaps after a counter-attack."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-7.0 * t) * math.cos(13.0 * t)


def bounce(t):
    """0 -> 1 like something heavy dropping and bouncing to rest."""
    t = clamp(t, 0.0, 1.0)
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def approach(current, target, rate, dt):
    """Move exponentially towards target; `rate` is per second."""
    return target + (current - target) * math.exp(-rate * dt)


def wrap_angle(angle):
    return (angle + math.pi) % math.tau - math.pi


def rotate_point(x, y, angle, cx, cy):
    c, s = math.cos(angle), math.sin(angle)
    dx, dy = x - cx, y - cy
    return cx + c * dx - s * dy, cy + s * dx + c * dy


def quantize(value):
    """Snap to the 0.01 control grid (and never return -0.0)."""
    return round(value, 2) + 0.0


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------
def fmt(value):
    """Two decimals, never '-0.00'."""
    return "{:.2f}".format(round(value, 2) + 0.0)


def signed(value):
    return "{:+.2f}".format(round(value, 2) + 0.0)


def clock_text(seconds):
    tenths = int(max(0.0, seconds) * 10)
    return "{:02d}:{:02d}.{}".format(tenths // 600, (tenths // 10) % 60, tenths % 10)


def score_text(value):
    return "{:,}".format(int(value))


# ---------------------------------------------------------------------------
# Geometry of the decision boundary
# ---------------------------------------------------------------------------
def boundary_endpoints(w1, w2, b, bounds=FLOOR_BOUNDS):
    """Two points on the line w1*x1 + w2*x2 + b = 0 where it meets the edges of
    `bounds`.  Returns None when the line misses the area, or when there is no
    line at all (w1 = w2 = 0)."""
    x_lo, x_hi, y_lo, y_hi = bounds
    eps = 1e-9
    hits = []
    if abs(w2) > eps:                           # crossings with the left / right edges
        for x1 in (x_lo, x_hi):
            x2 = -(w1 * x1 + b) / w2
            if y_lo - eps <= x2 <= y_hi + eps:
                hits.append((x1, clamp(x2, y_lo, y_hi)))
    if abs(w1) > eps:                           # crossings with the bottom / top edges
        for x2 in (y_lo, y_hi):
            x1 = -(w2 * x2 + b) / w1
            if x_lo - eps <= x1 <= x_hi + eps:
                hits.append((clamp(x1, x_lo, x_hi), x2))
    best, best_length = None, 1e-6              # a corner hit shows up twice: keep the widest pair
    for i in range(len(hits)):
        for j in range(i + 1, len(hits)):
            length = math.hypot(hits[i][0] - hits[j][0], hits[i][1] - hits[j][1])
            if length > best_length:
                best, best_length = (hits[i], hits[j]), length
    return best


def bounds_corners(bounds=FLOOR_BOUNDS):
    x_lo, x_hi, y_lo, y_hi = bounds
    return ((x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi))


def clip_to_side(polygon, w1, w2, b, positive):
    """The part of `polygon` on one side of the boundary (Sutherland-Hodgman).

    positive=True keeps where w1*x1 + w2*x2 + b > 0 (what predict() calls Safe);
    positive=False keeps the rest, including the line itself (Alarm)."""
    def inside(value):
        return value > 0 if positive else value <= 0

    out = []
    for i, p in enumerate(polygon):
        q = polygon[(i + 1) % len(polygon)]
        fp = w1 * p[0] + w2 * p[1] + b
        fq = w1 * q[0] + w2 * q[1] + b
        if inside(fp):
            out.append(p)
        if inside(fp) != inside(fq):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def polygon_centroid(points):
    """(centroid, area) of a simple polygon; centroid is None if it has no area."""
    area = cx = cy = 0.0
    for i, (x0, y0) in enumerate(points):
        x1, y1 = points[(i + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-6:
        return None, 0.0
    return (cx / (3.0 * area), cy / (3.0 * area)), abs(area) / 2.0


def to_pose(w1, w2, b, centre=WORLD_CENTRE):
    """Boundary as (angle of its normal, signed distance from `centre`).

    Used to animate the laser smoothly between two boundaries.  Returns None
    when w1 = w2 = 0 (no line)."""
    norm = math.hypot(w1, w2)
    if norm < 1e-9:
        return None
    offset = -(w1 * centre[0] + w2 * centre[1] + b) / norm
    return math.atan2(w2, w1), offset


def from_pose(theta, offset, centre=WORLD_CENTRE):
    """Inverse of to_pose: unit-length (w1, w2) and the matching b."""
    n1, n2 = math.cos(theta), math.sin(theta)
    return n1, n2, -(n1 * centre[0] + n2 * centre[1] + offset)


def signed_distance(w1, w2, b, x1, x2):
    """Distance from (x1, x2) to the line, positive on the safe side; None without a line."""
    norm = math.hypot(w1, w2)
    if norm < 1e-12:
        return None
    return (w1 * x1 + w2 * x2 + b) / norm


def project_onto_line(w1, w2, b, x1, x2):
    """The point on the line closest to (x1, x2), or None without a line."""
    nn = w1 * w1 + w2 * w2
    if nn < 1e-18:
        return None
    z = w1 * x1 + w2 * x2 + b
    return x1 - w1 * z / nn, x2 - w2 * z / nn


def line_through(p, q, ref=None, norm=0.5):
    """(w1, w2, b) for the line through points p and q.

    The weights get length `norm` and, if `ref` is given, keep pointing the same
    way as the weight vector `ref` (so the safe side does not flip while a
    player drags the laser).  None if p and q coincide."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    n1, n2 = -dy / length, dx / length
    if ref is not None and n1 * ref[0] + n2 * ref[1] < 0:
        n1, n2 = -n1, -n2
    n1, n2 = n1 * norm, n2 * norm
    return n1, n2, -(n1 * p[0] + n2 * p[1])


def rotate_about(w1, w2, b, angle, pivot):
    """Turn the line by `angle` radians around `pivot` (counter-clockwise)."""
    value = w1 * pivot[0] + w2 * pivot[1] + b
    c, s = math.cos(angle), math.sin(angle)
    v1, v2 = c * w1 - s * w2, s * w1 + c * w2
    return v1, v2, value - (v1 * pivot[0] + v2 * pivot[1])


def translate_line(w1, w2, b, distance):
    """Slide the line `distance` world units along its weight vector."""
    return w1, w2, b - distance * math.hypot(w1, w2)


def flip_params(w1, w2, b):
    """Same line, sides swapped."""
    return -w1, -w2, -b


def count_errors(w1, w2, b, points):
    """How many (x1, x2, label) points the boundary misclassifies (same rule as predict)."""
    errors = 0
    for x1, x2, label in points:
        if (1 if w1 * x1 + w2 * x2 + b > 0 else 0) != label:
            errors += 1
    return errors


def margin(w1, w2, b, points):
    """(slack, errors).  slack is the distance from the line to the closest
    correctly classified point, or None without a line or a correct point."""
    norm = math.hypot(w1, w2)
    errors = 0
    slack = None
    for x1, x2, label in points:
        z = w1 * x1 + w2 * x2 + b
        if (1 if z > 0 else 0) != label:
            errors += 1
        elif norm > 1e-12:
            distance = abs(z) / norm
            if slack is None or distance < slack:
                slack = distance
    return slack, errors


def min_linear_errors(points):
    """Fewest points that any single straight line misclassifies, and one such line.

    points: (x1, x2, label) triples.  Returns (errors, (w1, w2, b)).

    An optimal line can be slid and turned until it runs through two of the
    points without changing which side any other point is on.  So it is enough
    to try the line through every pair, nudged so those two points land on each
    combination of sides, in both orientations.  Exact for points in general
    position; with three or more points on one line it can only overestimate.
    """
    n = len(points)
    ones = sum(1 for p in points if p[2] == 1)
    if ones * 2 <= n:
        best, best_line = ones, (0.0, 0.0, -1.0)          # "everything is 0"
    else:
        best, best_line = n - ones, (0.0, 0.0, 1.0)       # "everything is 1"
    if best == 0 or n < 2:
        return best, best_line
    nudge = 1e-7
    turn = (math.cos(nudge), math.sin(nudge))
    for i in range(n):
        xi, yi = points[i][0], points[i][1]
        for j in range(i + 1, n):
            xj, yj = points[j][0], points[j][1]
            dx, dy = xj - xi, yj - yi
            length = math.hypot(dx, dy)
            if length < 1e-12:
                continue
            u1, u2 = -dy / length, dx / length
            candidates = []
            for px, py in ((xi, yi), (xj, yj), ((xi + xj) / 2.0, (yi + yj) / 2.0)):
                for s in (turn[1], -turn[1]):
                    c = turn[0]
                    v1, v2 = c * u1 - s * u2, s * u1 + c * u2
                    candidates.append((v1, v2, -(v1 * px + v2 * py)))
            base = -(u1 * xi + u2 * yi)
            candidates.append((u1, u2, base + nudge))
            candidates.append((u1, u2, base - nudge))
            for v1, v2, c0 in candidates:
                for sign in (1.0, -1.0):
                    w1, w2, b = sign * v1, sign * v2, sign * c0
                    errors = 0
                    for x1, x2, label in points:
                        if (1 if w1 * x1 + w2 * x2 + b > 0 else 0) != label:
                            errors += 1
                            if errors >= best:
                                break
                    if errors < best:
                        best, best_line = errors, (w1, w2, b)
                        if best == 0:
                            return 0, best_line
    return best, best_line


def is_separable(points):
    return min_linear_errors(points)[0] == 0


# ---------------------------------------------------------------------------
# How units move
# ---------------------------------------------------------------------------
class Motion:
    """Where a unit is at time t.  Positions are recomputed from t, never
    integrated, so the same times always give the same positions.

    kind  "still"   stays put
          "spin"    turns around `centre` at `omega` rad/s
          "patrol"  walks to `to` and back every `period` seconds
          "sway"    slides along `direction` by up to `amplitude`
    """

    def __init__(self, kind="still", centre=WORLD_CENTRE, omega=0.0, to=None, period=6.0, phase=0.0,
                 direction=(1.0, 0.0), amplitude=0.0):
        self.kind = kind
        self.centre = centre
        self.omega = omega
        self.to = to
        self.period = period
        self.phase = phase
        self.direction = direction
        self.amplitude = amplitude

    def position(self, x, y, t):
        if self.kind == "spin":
            return rotate_point(x, y, self.omega * t, self.centre[0], self.centre[1])
        if self.kind == "patrol" and self.to is not None:
            k = 0.5 - 0.5 * math.cos(math.tau * t / self.period + self.phase)
            return lerp(x, self.to[0], k), lerp(y, self.to[1], k)
        if self.kind == "sway":
            s = self.amplitude * math.sin(math.tau * t / self.period + self.phase)
            return x + self.direction[0] * s, y + self.direction[1] * s
        return x, y


# ---------------------------------------------------------------------------
# Layout generators.  Points are (x1, x2, label): label 1 = bot, 0 = drone.
# ---------------------------------------------------------------------------
def _in_box(x, y, box):
    return box[0] <= x <= box[1] and box[0] <= y <= box[1]


def _clear(x, y, placed, gap):
    gap2 = gap * gap
    for px, py, _ in placed:
        if (x - px) ** 2 + (y - py) ** 2 < gap2:
            return False
    return True


def _split(count, parts):
    base, extra = divmod(count, parts)
    return [base + (1 if k < extra else 0) for k in range(parts)]


def _scatter(rng, placed, count, label, centre, theta, along, depth, spread_along, spread_across,
             half_gap, min_gap, box, radius, tries=3000):
    """Add `count` points of one label around a spot `along` the line and `depth` away from it."""
    n1, n2 = math.cos(theta), math.sin(theta)       # unit normal, pointing at the label-1 side
    t1, t2 = -n2, n1                                # unit tangent, along the line
    side = 1.0 if label == 1 else -1.0
    made = 0
    for _ in range(tries):
        if made == count:
            break
        a = along + rng.gauss(0.0, spread_along)
        d = side * abs(depth + rng.gauss(0.0, spread_across))
        if abs(d) < half_gap:
            continue
        x = centre[0] + t1 * a + n1 * d
        y = centre[1] + t2 * a + n2 * d
        if not _in_box(x, y, box):
            continue
        if radius is not None and math.hypot(x - WORLD_CENTRE[0], y - WORLD_CENTRE[1]) > radius:
            continue
        if not _clear(x, y, placed, min_gap):
            continue
        placed.append((x, y, label))
        made += 1
    return made == count


def separable_layout(rng, n_pos, n_neg, gap, spread=1.0, min_gap=0.85, box=SAFE_BOX, radius=None,
                     clusters=1, centred=False):
    """Bots (label 1) and drones (label 0) on opposite sides of a random line,
    with at least `gap` world units between the two groups.

    Returns (points, (w1, w2, b)): the true line has |w| = 0.5 and its weights
    point at the bots.  `clusters` > 1 splits each side into groups spread
    along the line; `radius` keeps every point that close to the floor centre
    (for layouts that spin)."""
    for _ in range(80):
        theta = rng.uniform(0.0, math.tau)
        if centred:
            centre = WORLD_CENTRE
        else:
            centre = (WORLD_CENTRE[0] + rng.uniform(-0.9, 0.9), WORLD_CENTRE[1] + rng.uniform(-0.9, 0.9))
        placed = []
        ok = True
        for label, count in ((1, n_pos), (0, n_neg)):
            for k, part in enumerate(_split(count, clusters)):
                if part == 0:
                    continue
                if clusters == 1:
                    along = rng.uniform(-0.6, 0.6)
                else:
                    along = lerp(-2.5, 2.5, (k + 0.5) / clusters) + rng.uniform(-0.3, 0.3)
                depth = gap / 2.0 + spread * rng.uniform(0.7, 1.4)
                if not _scatter(rng, placed, part, label, centre, theta, along, depth,
                                1.05 * spread, 0.5 * spread, gap / 2.0, min_gap, box, radius):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            w1, w2 = 0.5 * math.cos(theta), 0.5 * math.sin(theta)
            return placed, (w1, w2, -(w1 * centre[0] + w2 * centre[1]))
    raise RuntimeError("could not place {} + {} units with gap {}".format(n_pos, n_neg, gap))


def _cluster_points(rng, placed, count, label, cx, cy, spread, min_gap, box, tries=3000):
    made = 0
    for _ in range(tries):
        if made == count:
            break
        x, y = cx + rng.gauss(0.0, spread), cy + rng.gauss(0.0, spread)
        if _in_box(x, y, box) and _clear(x, y, placed, min_gap):
            placed.append((x, y, label))
            made += 1
    return made == count


def xor_layout(rng, per_cluster=2, min_gap=0.85, box=SAFE_BOX):
    """Four squads in the corners, diagonal pairs sharing a label: XOR.  No line separates it."""
    for _ in range(80):
        lo, hi = 2.6, 7.4
        diagonal = 1 if rng.random() < 0.5 else 0
        corners = (((lo, lo), diagonal), ((hi, hi), diagonal), ((lo, hi), 1 - diagonal), ((hi, lo), 1 - diagonal))
        placed = []
        if all(_cluster_points(rng, placed, per_cluster, label, cx + rng.uniform(-0.4, 0.4),
                               cy + rng.uniform(-0.4, 0.4), 0.5, min_gap, box)
               for (cx, cy), label in corners):
            return placed
    raise RuntimeError("could not place an XOR layout")


def ring_layout(rng, n_inner, n_outer, min_gap=0.85, box=SAFE_BOX):
    """One label huddled in the middle, the other in a ring around it.  Not separable."""
    for _ in range(80):
        inner = 1 if rng.random() < 0.5 else 0
        cx, cy = WORLD_CENTRE[0] + rng.uniform(-0.5, 0.5), WORLD_CENTRE[1] + rng.uniform(-0.5, 0.5)
        placed = []
        if not _cluster_points(rng, placed, n_inner, inner, cx, cy, 0.6, min_gap, box):
            continue
        start = rng.uniform(0.0, math.tau)
        ok = True
        for k in range(n_outer):
            for _ in range(200):
                angle = start + k * math.tau / n_outer + rng.uniform(-0.2, 0.2)
                radius = rng.uniform(2.7, 3.4)
                x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
                if _in_box(x, y, box) and _clear(x, y, placed, min_gap):
                    placed.append((x, y, 1 - inner))
                    break
            else:
                ok = False
                break
        if ok:
            return placed
    raise RuntimeError("could not place a ring layout")


def sandwich_layout(rng, n_middle, n_outer, min_gap=0.85, box=SAFE_BOX):
    """One label in a band, the other on both sides of it.  Not separable."""
    for _ in range(80):
        middle = 1 if rng.random() < 0.5 else 0
        theta = rng.uniform(0.0, math.pi)
        n1, n2 = math.cos(theta), math.sin(theta)
        t1, t2 = -n2, n1
        cx, cy = WORLD_CENTRE
        placed = []
        ok = True
        for k in range(n_middle):
            for _ in range(300):
                a = lerp(-3.0, 3.0, (k + 0.5) / n_middle) + rng.uniform(-0.3, 0.3)
                d = rng.uniform(-0.45, 0.45)
                x, y = cx + t1 * a + n1 * d, cy + t2 * a + n2 * d
                if _in_box(x, y, box) and _clear(x, y, placed, min_gap):
                    placed.append((x, y, middle))
                    break
            else:
                ok = False
                break
        for k in range(n_outer if ok else 0):
            side = 1.0 if k % 2 == 0 else -1.0
            for _ in range(300):
                a = rng.uniform(-3.0, 3.0)
                d = side * rng.uniform(1.8, 3.0)
                x, y = cx + t1 * a + n1 * d, cy + t2 * a + n2 * d
                if _in_box(x, y, box) and _clear(x, y, placed, min_gap):
                    placed.append((x, y, 1 - middle))
                    break
            else:
                ok = False
                break
        if ok:
            return placed
    raise RuntimeError("could not place a sandwich layout")


def noisy_layout(rng, n_pos, n_neg, gap, flips=1, **kwargs):
    """A separable layout with `flips` units relabelled deep inside the other
    group: faulty sensors.  Returns (points, true_line, flipped_indices).

    Retries until the best possible line really makes exactly `flips` errors:
    a relabelled unit on the edge of its group can occasionally be split off
    by some other line, and then it would not be noise at all."""
    for _ in range(50):
        points, line = separable_layout(rng, n_pos, n_neg, gap, **kwargs)
        w1, w2, b = line
        order = sorted(range(len(points)), key=lambda i: -abs(w1 * points[i][0] + w2 * points[i][1] + b))
        flipped = order[:flips]
        noisy = [(x, y, 1 - label) if i in flipped else (x, y, label) for i, (x, y, label) in enumerate(points)]
        if min_linear_errors(noisy)[0] == flips:
            return noisy, line, flipped
    raise RuntimeError("could not make a noisy layout with {} unavoidable errors".format(flips))


def random_start(rng, points, bounds=FLOOR_BOUNDS, min_length=4.0, tries=600):
    """Small random weights (on the 0.01 grid) whose laser is visible on the
    floor and does not already solve `points`."""
    for _ in range(tries):
        brain = Perceptron(rng)
        w1, w2, b = (quantize(v) for v in brain.params)
        ends = boundary_endpoints(w1, w2, b, bounds)
        if ends is None or math.hypot(ends[0][0] - ends[1][0], ends[0][1] - ends[1][1]) < min_length:
            continue
        if points and count_errors(w1, w2, b, points) == 0:
            continue
        return w1, w2, b
    return 0.3, -0.31, -0.19
