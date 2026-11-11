"""Hyperplane Heist: drawing helpers, fonts, sprites and effects."""
import colorsys
import math
import os
import random

import pygame

from .core import (FLOOR_BOUNDS, boundary_endpoints, bounds_corners, clamp, clip_to_side, ease_out, lerp)

SCREEN_W, SCREEN_H = 1200, 720

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
INK = (8, 12, 21)
BG_TOP = (11, 15, 27)
BG_BOTTOM = (5, 7, 14)
FLOOR_FILL = (14, 20, 35)
GRID_MINOR = (23, 33, 55)
GRID_MAJOR = (35, 51, 84)
FLOOR_EDGE = (72, 106, 164)
PANEL_FILL = (13, 18, 32)
PANEL_EDGE = (40, 56, 90)
ROW_FILL = (18, 25, 43)
ROW_FLASH = (40, 74, 104)
TEXT = (216, 228, 246)
TEXT_DIM = (128, 146, 178)
TEXT_FAINT = (84, 100, 130)
CYAN = (88, 222, 255)
GREEN = (62, 232, 150)
RED = (255, 80, 104)
AMBER = (255, 192, 84)
VIOLET = (170, 140, 255)
PINK = (255, 110, 200)
GOLD = (255, 214, 92)
ARROW_GREEN = (132, 236, 186)

# Colour roles in formulas, used the same way everywhere
C_W = CYAN          # weights
C_B = AMBER         # bias
C_X = TEXT          # inputs
C_Z = VIOLET        # weighted sum
C_Y = GREEN         # outputs / labels
C_ETA = PINK        # learning rate

SKIN_COLORS = {
    "cyan": ("Classic Cyan", CYAN),
    "emerald": ("Emerald", (70, 245, 160)),
    "ruby": ("Ruby", (255, 70, 110)),
    "violet": ("Violet", (178, 130, 255)),
    "gold": ("Gold", (255, 205, 80)),
    "prism": ("Prism", None),           # cycles through the rainbow
}

# (width in px, brightness) from the faint outer halo to the bright inner glow
BEAM_LAYERS = ((44, 0.03), (36, 0.045), (29, 0.065), (23, 0.095), (18, 0.14),
               (14, 0.2), (10, 0.3), (7, 0.45), (5, 0.7))
THIN_BEAM = ((22, 0.05), (16, 0.09), (11, 0.16), (7, 0.3), (4, 0.6))

FONT_FILES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
def mix(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)), int(lerp(c1[2], c2[2], t)))


def scale_color(color, k):
    return (clamp(int(color[0] * k), 0, 255), clamp(int(color[1] * k), 0, 255), clamp(int(color[2] * k), 0, 255))


def hue_color(h, s=0.62, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def skin_color(name, time):
    entry = SKIN_COLORS.get(name) or SKIN_COLORS["cyan"]
    return entry[1] if entry[1] is not None else hue_color(time * 0.12)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------
def thick_line(surf, color, a, e, width):
    """A line of exact width at any angle (drawn as a quad)."""
    dx, dy = e[0] - a[0], e[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    hx, hy = -dy / length * width / 2.0, dx / length * width / 2.0
    pygame.draw.polygon(surf, color, ((a[0] + hx, a[1] + hy), (e[0] + hx, e[1] + hy),
                                      (e[0] - hx, e[1] - hy), (a[0] - hx, a[1] - hy)))


def beam(surf, a, e, color, power=1.0, core=True, extend=0.0, layers=BEAM_LAYERS):
    """A glowing laser from a to e.  `surf` is a black layer that gets added to the frame."""
    dx, dy = e[0] - a[0], e[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-6 or power <= 0.01:
        return
    ux, uy = dx / length, dy / length
    a = (a[0] - ux * extend, a[1] - uy * extend)
    e = (e[0] + ux * extend, e[1] + uy * extend)
    for width, level in layers:
        thick_line(surf, scale_color(color, level * power), a, e, width)
    if core:
        hot = scale_color(mix(color, WHITE, 0.82), min(1.0, power))
        thick_line(surf, hot, a, e, 2)
        for shift in (-1.2, 1.2):                   # anti-aliased edges for the bright core
            ox, oy = -uy * shift, ux * shift
            pygame.draw.aaline(surf, hot, (a[0] + ox, a[1] + oy), (e[0] + ox, e[1] + oy))


def draw_pulses(surf, a, e, color, time, spacing=170.0, speed=260.0, length=34.0, width=5):
    """Bright dashes of energy running along a beam."""
    dx, dy = e[0] - a[0], e[1] - a[1]
    total = math.hypot(dx, dy)
    if total < 60.0:
        return
    ux, uy = dx / total, dy / total
    d = (time * speed) % spacing
    hot = mix(color, WHITE, 0.85)
    while d < total:
        tail = max(0.0, d - length)
        thick_line(surf, hot, (a[0] + ux * tail, a[1] + uy * tail), (a[0] + ux * d, a[1] + uy * d), width)
        d += spacing


def draw_arc(surf, color, centre, radius, start, stop, width=2, steps=10):
    points = []
    for i in range(steps + 1):
        angle = lerp(start, stop, i / steps)
        points.append((centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle)))
    if len(points) >= 2:
        pygame.draw.lines(surf, color, False, points, max(1, int(width)))


def dashed_line(surf, color, a, e, width=1, dash=8.0, gap=6.0, offset=0.0):
    dx, dy = e[0] - a[0], e[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    d = -(offset % (dash + gap))
    while d < length:
        s, t = max(0.0, d), min(length, d + dash)
        if t > s:
            pygame.draw.line(surf, color, (a[0] + ux * s, a[1] + uy * s), (a[0] + ux * t, a[1] + uy * t), width)
        d += dash + gap


def draw_verdict(surf, x, y, ok, scale=1.0):
    """A tick or a cross in a little badge."""
    color = GREEN if ok else RED
    r = max(2, int(11 * scale))
    pygame.draw.circle(surf, INK, (x, y), r)
    pygame.draw.circle(surf, color, (x, y), r, 2)
    k = scale
    if ok:
        pygame.draw.lines(surf, color, False, [(x - 5 * k, y), (x - 1 * k, y + 4 * k), (x + 5 * k, y - 4 * k)], 3)
    else:
        pygame.draw.line(surf, color, (x - 4 * k, y - 4 * k), (x + 4 * k, y + 4 * k), 3)
        pygame.draw.line(surf, color, (x - 4 * k, y + 4 * k), (x + 4 * k, y - 4 * k), 3)


def draw_star(surf, cx, cy, r, color, filled=True, width=2):
    points = []
    for k in range(10):
        radius = r if k % 2 == 0 else r * 0.45
        angle = -math.pi / 2 + k * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    pygame.draw.polygon(surf, color, points, 0 if filled else width)


def draw_shield(surf, cx, cy, s, color, filled=True):
    points = [(cx, cy - s), (cx + 0.85 * s, cy - 0.62 * s), (cx + 0.78 * s, cy + 0.2 * s),
              (cx, cy + s), (cx - 0.78 * s, cy + 0.2 * s), (cx - 0.85 * s, cy - 0.62 * s)]
    pygame.draw.polygon(surf, color, points, 0 if filled else 2)
    if filled:
        pygame.draw.polygon(surf, mix(color, WHITE, 0.45), points, 1)


def draw_lock(surf, cx, cy, s, color):
    body = pygame.Rect(0, 0, int(1.3 * s), int(s))
    body.midtop = (int(cx), int(cy - 0.05 * s))
    pygame.draw.rect(surf, color, body, border_radius=max(1, int(0.2 * s)))
    draw_arc(surf, color, (cx, cy - 0.05 * s), 0.42 * s, math.pi, math.tau, max(2, int(0.22 * s)), 8)


def lightning(surf, a, e, color, rng, segments=7, jitter=9.0, width=2):
    dx, dy = e[0] - a[0], e[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length
    points = [a]
    for k in range(1, segments):
        t = k / segments
        off = rng.uniform(-jitter, jitter)
        points.append((a[0] + dx * t + px * off, a[1] + dy * t + py * off))
    points.append(e)
    pygame.draw.lines(surf, color, False, points, width)


def make_glow(radius, color, strength=1.0):
    """A soft round glow on black, meant to be added to the frame."""
    surf = pygame.Surface((radius * 2, radius * 2), 0, 32)
    for r in range(radius, 0, -1):
        k = (1.0 - r / radius) ** 2 * strength
        pygame.draw.circle(surf, scale_color(color, k), (radius, radius), r)
    return surf


def make_text_glow(font, string, color, pad=40, shrink=8):
    """A blurred copy of some text on black, meant to be added behind the crisp text."""
    ink = font.render(string, True, color)
    width, height = ink.get_width() + pad * 2, ink.get_height() + pad * 2
    base = pygame.Surface((width, height), 0, 32)
    base.blit(ink, (pad, pad))
    small = pygame.transform.smoothscale(base, (max(1, width // shrink), max(1, height // shrink)))
    return pygame.transform.smoothscale(small, (width, height))


def make_scan_strip(color, peak_alpha, height, width=120):
    """The scanner sweep: a band that fades out behind a bright leading edge."""
    surf = pygame.Surface((width, height), pygame.SRCALPHA, 32)
    for x in range(width):
        alpha = int(peak_alpha * (x / (width - 1)) ** 2.2)
        pygame.draw.line(surf, color + (alpha,), (x, 0), (x, height))
    edge = mix(color, WHITE, 0.6) + (min(255, int(peak_alpha * 2.4)),)
    pygame.draw.line(surf, edge, (width - 1, 0), (width - 1, height))
    pygame.draw.line(surf, edge, (width - 2, 0), (width - 2, height))
    return surf


def make_icon():
    surf = pygame.Surface((64, 64), pygame.SRCALPHA, 32)
    pygame.draw.rect(surf, FLOOR_FILL + (255,), surf.get_rect(), border_radius=12)
    pygame.draw.circle(surf, GREEN, (18, 44), 9)
    pygame.draw.polygon(surf, RED, ((46, 10), (57, 29), (35, 29)))
    pygame.draw.line(surf, CYAN, (8, 12), (56, 54), 5)
    pygame.draw.line(surf, WHITE, (8, 12), (56, 54), 1)
    return surf


def make_backdrop(width=SCREEN_W, height=SCREEN_H, top=BG_TOP, bottom=BG_BOTTOM):
    surf = pygame.Surface((width, height), 0, 32)
    for y in range(height):
        pygame.draw.line(surf, mix(top, bottom, y / max(1, height - 1)), (0, y), (width, y))
    return surf


def make_shutter():
    """The steel shutter that drops when a vault locks down."""
    surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA, 32)
    slat, gap = 66, 14
    y = 0
    while y < SCREEN_H:
        pygame.draw.rect(surf, (20, 22, 29, 244), (0, y, SCREEN_W, slat))
        pygame.draw.line(surf, (70, 74, 88, 255), (0, y), (SCREEN_W, y), 2)
        pygame.draw.line(surf, (6, 7, 10, 255), (0, y + slat - 2), (SCREEN_W, y + slat - 2), 2)
        for x in range(30, SCREEN_W, 120):
            pygame.draw.circle(surf, (58, 62, 74, 255), (x, y + slat // 2), 4)
        y += slat + gap
    return surf


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
def find_font_file():
    """A monospaced font file on this machine, or None to use pygame's default font."""
    for path in FONT_FILES:
        if os.path.exists(path):
            return path
    try:
        return pygame.font.match_font("menlo,consolas,dejavusansmono,liberationmono,couriernew,courier")
    except Exception:
        return None


def load_font(path, size, bold=False):
    try:
        font = pygame.font.Font(path, size) if path else pygame.font.Font(None, int(size * 1.3))
    except Exception:
        font = pygame.font.Font(None, int(size * 1.3))
    font.set_bold(bold)
    return font


def num(value):
    """A short label for a grid number: 2, 2.5, -1."""
    return "{:g}".format(round(value, 6) + 0.0)


# ---------------------------------------------------------------------------
# A world <-> screen mapping for any plot
# ---------------------------------------------------------------------------
class Viewport:
    """Maps the world box `bounds` = (x1 min, x1 max, x2 min, x2 max) onto a
    screen rectangle, with x2 pointing up.  Keep the box square and the rect
    square so directions survive the mapping."""

    def __init__(self, rect, bounds=FLOOR_BOUNDS):
        self.rect = pygame.Rect(rect)
        self.bounds = bounds

    @property
    def ppu(self):
        """Pixels per world unit."""
        return self.rect.width / (self.bounds[1] - self.bounds[0])

    def to_screen(self, x1, x2):
        x_lo, x_hi, y_lo, y_hi = self.bounds
        return (self.rect.left + (x1 - x_lo) / (x_hi - x_lo) * self.rect.width,
                self.rect.bottom - (x2 - y_lo) / (y_hi - y_lo) * self.rect.height)

    def to_world(self, px, py):
        x_lo, x_hi, y_lo, y_hi = self.bounds
        return (x_lo + (px - self.rect.left) / self.rect.width * (x_hi - x_lo),
                y_lo + (self.rect.bottom - py) / self.rect.height * (y_hi - y_lo))

    def contains(self, px, py, pad=0):
        return self.rect.inflate(pad * 2, pad * 2).collidepoint(px, py)


_zone_layers = {}


def draw_grid(surf, vp, gfx, step=1.0, major_every=5, fill=FLOOR_FILL, labels=True, label_every=1,
              axis_names=("x₁", "x₂"), edge=True, axes=False, minor=GRID_MINOR, major=GRID_MAJOR):
    """Floor, grid lines, tick labels and axis names for a viewport."""
    pygame.draw.rect(surf, fill, vp.rect)
    x_lo, x_hi, y_lo, y_hi = vp.bounds
    for k in range(int(math.ceil(x_lo / step - 1e-9)), int(math.floor(x_hi / step + 1e-9)) + 1):
        x = k * step
        px = int(round(vp.to_screen(x, y_lo)[0]))
        color = major if k % major_every == 0 else minor
        if axes and abs(x) < 1e-9:
            color = mix(major, TEXT_DIM, 0.6)
        pygame.draw.line(surf, color, (px, vp.rect.top), (px, vp.rect.bottom - 1))
        if labels and k % label_every == 0:
            gfx.text(surf, gfx.tiny, num(x), (px, vp.rect.bottom + 9), TEXT_DIM, "midtop")
    for k in range(int(math.ceil(y_lo / step - 1e-9)), int(math.floor(y_hi / step + 1e-9)) + 1):
        y = k * step
        py = int(round(vp.to_screen(x_lo, y)[1]))
        color = major if k % major_every == 0 else minor
        if axes and abs(y) < 1e-9:
            color = mix(major, TEXT_DIM, 0.6)
        pygame.draw.line(surf, color, (vp.rect.left, py), (vp.rect.right - 1, py))
        if labels and k % label_every == 0:
            gfx.text(surf, gfx.tiny, num(y), (vp.rect.left - 9, py), TEXT_DIM, "midright")
    if edge:
        pygame.draw.rect(surf, FLOOR_EDGE, vp.rect.inflate(6, 6), 2, border_radius=4)
    if axis_names:
        gfx.text(surf, gfx.small, axis_names[0], (vp.rect.centerx, vp.rect.bottom + 24), TEXT_DIM, "midtop")
        gfx.text(surf, gfx.small, axis_names[1], (vp.rect.left - 44, vp.rect.centery - 14), TEXT_DIM, "center")


def draw_zones(surf, vp, w1, w2, b, alpha=30, safe=GREEN, alarm=RED):
    """Tint the two half-planes: where predict() says 1 (safe) and where it says 0
    (alarm).  Returns [(positive, screen polygon)] for the parts that exist."""
    size = vp.rect.size
    zone = _zone_layers.get(size)
    if zone is None:
        zone = pygame.Surface(size, pygame.SRCALPHA, 32)
        _zone_layers[size] = zone
    zone.fill((0, 0, 0, 0))
    out = []
    for positive, color in ((True, safe), (False, alarm)):
        world = clip_to_side(bounds_corners(vp.bounds), w1, w2, b, positive)
        if len(world) < 3:
            continue
        points = [vp.to_screen(x, y) for x, y in world]
        pygame.draw.polygon(zone, color + (alpha,), [(x - vp.rect.left, y - vp.rect.top) for x, y in points])
        out.append((positive, points))
    surf.blit(zone, vp.rect.topleft)
    return out


def laser_segment(vp, w1, w2, b):
    """Pixel end points of the boundary inside a viewport, or None."""
    ends = boundary_endpoints(w1, w2, b, vp.bounds)
    if ends is None:
        return None
    return vp.to_screen(*ends[0]), vp.to_screen(*ends[1])


def draw_laser(surf, fx, vp, w1, w2, b, color, power=1.0, time=0.0, layers=THIN_BEAM, pulses=True,
               emitters=True):
    """A self-contained laser for small plots (the game board composes its own)."""
    segment = laser_segment(vp, w1, w2, b)
    if segment is None:
        return None
    a, e = segment
    fx.set_clip(vp.rect)
    fx.fill(BLACK, vp.rect)
    beam(fx, a, e, color, power, layers=layers)
    if pulses:
        draw_pulses(fx, a, e, color, time, spacing=120.0, length=22.0, width=3)
    fx.set_clip(None)
    surf.blit(fx, vp.rect.topleft, vp.rect, special_flags=pygame.BLEND_RGB_ADD)
    if emitters:
        for x, y in (a, e):
            pygame.draw.circle(surf, INK, (x, y), 6)
            pygame.draw.circle(surf, color, (x, y), 6, 2)
    return segment


def draw_weight_arrow(surf, vp, gfx, w1, w2, b, color=ARROW_GREEN, length=56, label="w"):
    """The weight vector w = (w1, w2), drawn from the middle of the boundary.  It
    is perpendicular to the boundary and always points into the safe side."""
    norm = math.hypot(w1, w2)
    segment = laser_segment(vp, w1, w2, b)
    if segment is None or norm < 1e-9:
        return
    (ax, ay), (ex, ey) = segment
    nx, ny = w1 / norm, -w2 / norm                      # screen y runs downwards
    mx, my = (ax + ex) / 2.0, (ay + ey) / 2.0
    tip = (mx + nx * length, my + ny * length)
    surf.set_clip(vp.rect)
    thick_line(surf, color, (mx + nx * 10, my + ny * 10), (tip[0] - nx * 8, tip[1] - ny * 8), 2)
    pygame.draw.polygon(surf, color, (tip,
                                      (tip[0] - nx * 11 - ny * 5.5, tip[1] - ny * 11 + nx * 5.5),
                                      (tip[0] - nx * 11 + ny * 5.5, tip[1] - ny * 11 - nx * 5.5)))
    if label:
        gfx.text(surf, gfx.label, label, (tip[0] + nx * 12, tip[1] + ny * 12), color, "center")
    surf.set_clip(None)


def draw_margin_corridor(surf, vp, w1, w2, b, slack, color, time=0.0):
    """Dashed lines either side of the boundary at the distance of the closest unit."""
    norm = math.hypot(w1, w2)
    if norm < 1e-9 or not slack or slack <= 0:
        return
    surf.set_clip(vp.rect)
    for sign in (1.0, -1.0):
        ends = boundary_endpoints(w1, w2, b - sign * slack * norm, vp.bounds)
        if ends:
            dashed_line(surf, color, vp.to_screen(*ends[0]), vp.to_screen(*ends[1]), 1, 7.0, 6.0, time * 18.0)
    surf.set_clip(None)


# ---------------------------------------------------------------------------
# Sprites
# ---------------------------------------------------------------------------
def draw_bot(surf, x, y, t, ping=0.0, scale=1.0, body=GREEN):
    """Authorized bot (label 1): a green circle with a visor, an antenna and a scanner ring."""
    if scale <= 0.05:
        return
    s = scale
    w = max(1, int(round(2 * s)))
    pygame.draw.line(surf, (150, 240, 200), (x, y - 12 * s), (x + 2 * s, y - 17 * s), w)        # antenna
    blink = 0.5 + 0.5 * math.sin(t * 5.0)
    pygame.draw.circle(surf, mix((40, 120, 90), (220, 255, 235), blink), (x + 2 * s, y - 17 * s), max(1, 2.4 * s))
    pygame.draw.circle(surf, INK, (x, y), 15 * s)
    pygame.draw.circle(surf, mix(body, WHITE, 0.6 * ping), (x, y), 12 * s)
    pygame.draw.rect(surf, (10, 58, 42), (x - 8 * s, y - 4 * s, 16 * s, 7 * s), border_radius=max(1, int(3 * s)))
    pygame.draw.circle(surf, (214, 255, 232), (x + 4.5 * s * math.sin(t * 2.4), y - 0.5 * s), max(1, 2 * s))
    ring = mix(scale_color(body, 0.75), WHITE, ping)
    for k in range(3):
        start = t * 1.5 + k * math.tau / 3
        draw_arc(surf, ring, (x, y), 19 * s, start, start + 1.15, w)


def draw_drone(surf, x, y, t, ping=0.0, scale=1.0, body=RED):
    """Intruder drone (label 0): a red triangle with spinning rotors."""
    if scale <= 0.05:
        return
    s = scale
    tilt = math.radians(7.0) * math.sin(t * 2.1)

    def corner(radius, k):
        angle = math.pi / 2 + tilt + k * math.tau / 3
        return x + radius * math.cos(angle), y - radius * math.sin(angle)

    for k in (1, 2):                                    # rotors under the two bottom corners
        cx, cy = corner(19 * s, k)
        spin = abs(math.cos(t * 31.0 + k))
        pygame.draw.ellipse(surf, (255, 150, 165), (cx - 8 * s * spin - 1, cy - 1.5 * s, 16 * s * spin + 2, 3 * s + 1))
    pygame.draw.polygon(surf, INK, [corner(21 * s, k) for k in range(3)])
    shell = [corner(16 * s, k) for k in range(3)]
    pygame.draw.polygon(surf, mix(body, WHITE, 0.6 * ping), shell)
    pygame.draw.aalines(surf, (255, 176, 188), True, shell)
    blink = 0.5 + 0.5 * math.sin(t * 6.0)
    pygame.draw.circle(surf, mix((96, 10, 24), (255, 240, 214), blink), (x, y + 1 * s), max(1, 3 * s))


def draw_imposter(surf, x, y, t, rng, ping=0.0, scale=1.0, nervous=0.0):
    """A drone disguised as a bot.  As the reveal nears (`nervous` 0..1) it glitches."""
    draw_bot(surf, x, y, t, ping, scale)
    if nervous > 0.0 and rng.random() < 0.08 + 0.5 * nervous:
        offset = rng.uniform(-6, 6) * nervous
        draw_drone(surf, x + offset, y, t, 0.0, scale * rng.uniform(0.75, 1.0))


def draw_nyx(surf, cx, cy, size, t, talking=False, color=CYAN):
    """Nyx, the crew's hacker: a hooded figure with a glowing visor."""
    s = size
    pygame.draw.circle(surf, (20, 16, 38), (cx, cy + s * 0.1), s * 1.12)
    pygame.draw.circle(surf, scale_color(color, 0.35), (cx, cy + s * 0.1), s * 1.12, 2)
    shoulders = [(cx - s * 1.0, cy + s * 1.15), (cx - s * 0.62, cy + s * 0.62), (cx + s * 0.62, cy + s * 0.62),
                 (cx + s * 1.0, cy + s * 1.15)]
    pygame.draw.polygon(surf, (34, 26, 62), shoulders)
    hood = [(cx - s * 0.82, cy + s * 0.78), (cx - s * 0.7, cy - s * 0.42), (cx - s * 0.18, cy - s * 0.92),
            (cx + s * 0.18, cy - s * 0.92), (cx + s * 0.7, cy - s * 0.42), (cx + s * 0.82, cy + s * 0.78)]
    pygame.draw.polygon(surf, (46, 34, 86), hood)
    pygame.draw.ellipse(surf, (10, 12, 22), (cx - s * 0.5, cy - s * 0.52, s * 1.0, s * 1.18))
    glow = 0.72 + 0.28 * math.sin(t * 3.0)
    visor = pygame.Rect(0, 0, int(s * 0.78), max(3, int(s * 0.16)))
    visor.center = (int(cx), int(cy - s * 0.08))
    pygame.draw.rect(surf, scale_color(color, glow), visor, border_radius=max(1, int(s * 0.08)))
    eye = cx + s * 0.22 * math.sin(t * 0.9)
    pygame.draw.circle(surf, WHITE, (eye, cy - s * 0.08), max(1, s * 0.05))
    opening = abs(math.sin(t * 17.0)) * s * 0.09 if talking else 0.0
    pygame.draw.ellipse(surf, scale_color(color, 0.8),
                        (cx - s * 0.11, cy + s * 0.26 - opening / 2, s * 0.22, max(2, s * 0.035 + opening)))


def draw_vault_door(surf, cx, cy, t, unlocked, radius=112):
    """A round vault door: the bolts retract, the wheel spins, it lights up green."""
    steel = mix((92, 116, 142), GREEN, unlocked)
    if unlocked >= 1.0:                                 # rings of light once it is open
        for k in range(3):
            phase = ((t - 1.7) * 0.6 + k / 3.0) % 1.0
            pygame.draw.circle(surf, scale_color(GREEN, (1.0 - phase) * 0.55), (cx, cy),
                               int(radius + 12 + phase * 150), 2)
    pygame.draw.circle(surf, (10, 18, 24), (cx, cy), radius + 8)
    pygame.draw.circle(surf, steel, (cx, cy), radius + 8, 10)
    for k in range(8):                                  # locking bolts retract one after another
        angle = k * math.pi / 4 + math.pi / 8
        pulled = ease_out((t - 0.55 - k * 0.09) / 0.25)
        r = lerp(radius + 3, radius - 18, pulled)
        x, y = cx + math.cos(angle) * r, cy + math.sin(angle) * r
        pygame.draw.circle(surf, mix((166, 184, 202), GREEN, pulled), (x, y), 7)
        pygame.draw.circle(surf, (10, 18, 24), (x, y), 7, 2)
    pygame.draw.circle(surf, (18, 30, 40), (cx, cy), radius - 28)
    pygame.draw.circle(surf, mix((52, 72, 94), GREEN, unlocked * 0.6), (cx, cy), radius - 28, 2)
    spin = ease_out((t - 0.45) / 1.25) * math.pi * 2.5  # the handle wheel spins down
    for k in range(5):
        angle = spin + k * math.tau / 5
        x, y = cx + math.cos(angle) * 60, cy + math.sin(angle) * 60
        thick_line(surf, steel, (cx, cy), (x, y), 7)
        pygame.draw.circle(surf, steel, (x, y), 9)
        pygame.draw.circle(surf, (10, 18, 24), (x, y), 4)
    pygame.draw.circle(surf, steel, (cx, cy), 60, 4)
    pygame.draw.circle(surf, (10, 18, 24), (cx, cy), 22)
    pygame.draw.circle(surf, steel, (cx, cy), 22, 5)
    pygame.draw.circle(surf, mix(RED, GREEN, unlocked), (cx, cy), 8)


def panel(surf, rect, fill=PANEL_FILL, edge=PANEL_EDGE, radius=10, width=1):
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if edge is not None:
        pygame.draw.rect(surf, edge, rect, width, border_radius=radius)


# ---------------------------------------------------------------------------
# Fonts, text and cached surfaces
# ---------------------------------------------------------------------------
class Gfx:
    """Fonts, a text cache and a few shared surfaces."""

    def __init__(self):
        self.font_path = find_font_file()
        self._fonts = {}
        self.tiny = self.font(11)
        self.small = self.font(13)
        self.body = self.font(15)
        self.lead = self.font(17)
        self.label = self.font(12, True)
        self.mid = self.font(20, True)
        self.value = self.font(28, True)
        self.title = self.font(30, True)
        self.big = self.font(46, True)
        self.huge = self.font(76, True)
        self._text = {}
        self._plates = {}
        self._banners = {}
        self._glows = {}
        self.fx = pygame.Surface((SCREEN_W, SCREEN_H), 0, 32)               # additive glow layer
        self.shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA, 32)
        self.backdrop = make_backdrop()

    def font(self, size, bold=False):
        key = (size, bold)
        font = self._fonts.get(key)
        if font is None:
            font = load_font(self.font_path, size, bold)
            self._fonts[key] = font
        return font

    def render(self, font, string, color):
        key = (id(font), string, color)
        image = self._text.get(key)
        if image is None:
            if len(self._text) > 1600:
                self._text.clear()
            image = font.render(string, True, color)
            self._text[key] = image
        return image

    def text(self, surf, font, string, pos, color=TEXT, anchor="topleft", alpha=255):
        image = self.render(font, string, color)
        image.set_alpha(int(clamp(alpha, 0, 255)))
        rect = image.get_rect(**{anchor: (int(round(pos[0])), int(round(pos[1])))})
        surf.blit(image, rect)
        return rect

    def rich_width(self, font, segments):
        return sum(font.size(seg[0])[0] for seg in segments)

    def rich(self, surf, font, segments, pos, anchor="topleft", alpha=255):
        """Text in several colours on one line: segments = [(string, colour), ...]."""
        width = self.rich_width(font, segments)
        rect = pygame.Rect(0, 0, width, font.get_height())
        setattr(rect, anchor, (int(round(pos[0])), int(round(pos[1]))))
        x = rect.left
        for seg in segments:
            if seg[0]:
                image = self.render(font, seg[0], seg[1])
                image.set_alpha(int(clamp(alpha, 0, 255)))
                surf.blit(image, (x, rect.top))
                x += image.get_width()
        return rect

    def wrap(self, font, text, width):
        lines = []
        for paragraph in text.split("\n"):
            words = paragraph.split(" ")
            line = ""
            for word in words:
                trial = word if not line else line + " " + word
                if font.size(trial)[0] <= width or not line:
                    line = trial
                else:
                    lines.append(line)
                    line = word
            lines.append(line)
        return lines

    def paragraph(self, surf, font, text, x, y, width, color=TEXT, gap=5, alpha=255, anchor="topleft"):
        """Wrapped text; returns the y just below it."""
        height = font.get_height() + gap
        for line in self.wrap(font, text, width):
            if line:
                if anchor == "midtop":
                    self.text(surf, font, line, (x, y), color, "midtop", alpha)
                else:
                    self.text(surf, font, line, (x, y), color, "topleft", alpha)
            y += height
        return y

    def plate(self, size, color=(7, 10, 19, 224), radius=8):
        """A translucent rounded panel to put text on."""
        key = (tuple(size), color, radius)
        surf = self._plates.get(key)
        if surf is None:
            surf = pygame.Surface(size, pygame.SRCALPHA, 32)
            pygame.draw.rect(surf, color, surf.get_rect(), border_radius=radius)
            self._plates[key] = surf
        return surf

    def banner(self, string, ink, glow_color, font=None):
        font = font or self.huge
        key = (string, ink, glow_color, id(font))
        pair = self._banners.get(key)
        if pair is None:
            pair = (font.render(string, True, ink), make_text_glow(font, string, glow_color))
            self._banners[key] = pair
        return pair

    def draw_banner(self, surf, string, centre, ink, glow_color, font=None, alpha=255):
        image, glow = self.banner(string, ink, glow_color, font)
        rect = image.get_rect(center=(int(centre[0]), int(centre[1])))
        glow.set_alpha(int(alpha))
        surf.blit(glow, glow.get_rect(center=rect.center), special_flags=pygame.BLEND_RGB_ADD)
        image.set_alpha(int(alpha))
        surf.blit(image, rect)
        return rect

    def glow(self, radius, color, strength=0.5):
        key = (radius, color, strength)
        surf = self._glows.get(key)
        if surf is None:
            surf = make_glow(radius, color, strength)
            self._glows[key] = surf
        return surf

    def add_glow(self, surf, x, y, radius, color, strength=0.5):
        g = self.glow(radius, color, strength)
        surf.blit(g, (int(x) - radius, int(y) - radius), special_flags=pygame.BLEND_RGB_ADD)

    def dim(self, surf, alpha, color=(0, 0, 0)):
        if alpha >= 1:
            self.shade.fill(color + (int(clamp(alpha, 0, 255)),))
            surf.blit(self.shade, (0, 0))

    def keycap(self, surf, x, y, label=None, arrow=None, active=False):
        """Draw a keyboard key at (x, y); returns the x just past it."""
        width = 24 if arrow or len(label) == 1 else self.tiny.size(label)[0] + 14
        rect = pygame.Rect(int(x), int(y), width, 20)
        pygame.draw.rect(surf, (40, 96, 126) if active else (24, 33, 54), rect, border_radius=4)
        pygame.draw.rect(surf, CYAN if active else (64, 84, 124), rect, 1, border_radius=4)
        ink = WHITE if active else TEXT
        if arrow:
            cx, cy = rect.center
            dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[arrow]
            pygame.draw.polygon(surf, ink, ((cx + dx * 5, cy + dy * 5),
                                            (cx - dx * 4 + dy * 5, cy - dy * 4 + dx * 5),
                                            (cx - dx * 4 - dy * 5, cy - dy * 4 - dx * 5)))
        else:
            self.text(surf, self.tiny, label, rect.center, ink, "center")
        return rect.right + 4

    def key_hint(self, surf, x, y, keys, label, color=TEXT_DIM):
        """A row like  [ENTER] lock in : keys is a list of labels or ('arrow', dir)."""
        for k in keys:
            if isinstance(k, tuple):
                x = self.keycap(surf, x, y, arrow=k[1])
            else:
                x = self.keycap(surf, x, y, label=k)
        return self.text(surf, self.small, label, (x + 3, y + 3), color).right + 16


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------
class Particles:
    def __init__(self, rng=None, cap=800):
        self.rng = rng or random.Random()
        self.cap = cap
        self.items = []

    def spark(self, x, y, color, count=1, speed=120.0, life=0.6, size=2.5, gravity=0.0):
        rnd = self.rng
        for _ in range(count):
            if len(self.items) >= self.cap:
                return
            angle = rnd.uniform(0, math.tau)
            velocity = speed * rnd.uniform(0.25, 1.0)
            lifespan = life * rnd.uniform(0.6, 1.0)
            self.items.append([x, y, math.cos(angle) * velocity, math.sin(angle) * velocity,
                               lifespan, lifespan, size, color, gravity])

    def burst_along(self, segment, color, count, speed, life, size=2.5):
        if segment is None:
            return
        (ax, ay), (ex, ey) = segment
        for _ in range(count):
            k = self.rng.random()
            self.spark(lerp(ax, ex, k), lerp(ay, ey, k), color, speed=speed, life=life, size=size)

    def update(self, dt):
        alive = []
        drag = max(0.0, 1.0 - 1.6 * dt)
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0.0:
                continue
            p[2] *= drag
            p[3] = p[3] * drag + p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            alive.append(p)
        self.items = alive

    def draw(self, surf):
        for x, y, _, _, life, lifespan, size, color, _ in self.items:
            k = life / lifespan
            pygame.draw.circle(surf, scale_color(color, 0.25 + 0.75 * k), (int(x), int(y)),
                               max(1, int(size * k + 0.5)))

    def clear(self):
        self.items = []


class Popups:
    """Floating text that pops in, rises and fades."""

    def __init__(self):
        self.items = []

    def add(self, text, x, y, color=WHITE, size="mid", life=1.1, rise=42.0, delay=0.0):
        self.items.append({"text": text, "x": x, "y": y, "color": color, "size": size, "life": life,
                           "age": -delay, "rise": rise})

    def update(self, dt):
        for item in self.items:
            item["age"] += dt
        self.items = [i for i in self.items if i["age"] < i["life"]]

    def draw(self, surf, gfx):
        for item in self.items:
            age = item["age"]
            if age < 0:
                continue
            k = age / item["life"]
            font = getattr(gfx, item["size"])
            alpha = 255 if k < 0.6 else 255 * (1.0 - (k - 0.6) / 0.4)
            y = item["y"] - item["rise"] * ease_out(k)
            pop = min(1.0, age / 0.12)
            if pop < 1.0:
                image = gfx.render(font, item["text"], item["color"])
                w = max(1, int(image.get_width() * (0.5 + 0.5 * pop)))
                h = max(1, int(image.get_height() * (0.5 + 0.5 * pop)))
                scaled = pygame.transform.smoothscale(image, (w, h))
                surf.blit(scaled, scaled.get_rect(center=(int(item["x"]), int(y))))
            else:
                gfx.text(surf, font, item["text"], (item["x"], y), item["color"], "center", alpha)

    def clear(self):
        self.items = []
