import math
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

Point = tuple[float, float]
Triangle = tuple[Point, Point, Point]

CURVE_STEPS = 2
CORNER_STEPS = 3


class FlattenPen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.contours: list[list[Point]] = []

    def _moveTo(self, pt):
        self.contours.append([pt])

    def _lineTo(self, pt):
        self.contours[-1].append(pt)

    def _qCurveToOne(self, pt1, pt2):
        start = self.contours[-1][-1]
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            self.contours[-1].append(tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t ** 2 * c for a, b, c in zip(start, pt1, pt2)))

    def _curveToOne(self, pt1, pt2, pt3):
        start = self.contours[-1][-1]
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            self.contours[-1].append(tuple(
                (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                for a, b, c, d in zip(start, pt1, pt2, pt3)))


def signed_area(poly: list[Point]) -> float:
    return sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly))) / -2


def clean(poly: list[Point]) -> list[Point]:
    points = [p for i, p in enumerate(poly) if p != poly[i - 1]]
    keep = []
    for i, p in enumerate(points):
        a, b = points[i - 1], points[(i + 1) % len(points)]
        if abs((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) > 1e-6:
            keep.append(p)
    return keep


def contains(poly: list[Point], point: Point) -> bool:
    inside = False
    x, y = point
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if a in (c, d) or b in (c, d):
        return False
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


def bridge(outer: list[Point], hole: list[Point]) -> list[Point]:
    j = max(range(len(hole)), key=lambda k: hole[k][0])
    m = hole[j]
    edges = [(outer[k - 1], outer[k]) for k in range(len(outer))] + [(hole[k - 1], hole[k]) for k in range(len(hole))]
    visible = [i for i in range(len(outer)) if not any(segments_cross(m, outer[i], e[0], e[1]) for e in edges)]
    i = min(visible or range(len(outer)), key=lambda k: math.dist(m, outer[k]))
    return outer[:i + 1] + hole[j:] + hole[:j + 1] + outer[i:]


def in_triangle(p: Point, a: Point, b: Point, c: Point) -> bool:
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def ear_clip(poly: list[Point]) -> list[Triangle]:
    points = list(poly)
    triangles = []
    guard = len(points) * len(points)
    while len(points) > 3 and guard > 0:
        guard -= 1
        for i in range(len(points)):
            a, b, c = points[i - 1], points[i], points[(i + 1) % len(points)]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 0:
                continue
            if any(in_triangle(p, a, b, c) for p in points if p not in (a, b, c)):
                continue
            triangles.append((a, b, c))
            del points[i]
            break
        else:
            break
    if len(points) == 3:
        triangles.append(tuple(points))
    return triangles


def triangulate(contours: list[list[Point]]) -> list[Triangle]:
    polys = [p for p in (clean(c) for c in contours) if len(p) >= 3]
    if not polys:
        return []
    outer_sign = math.copysign(1, signed_area(max(polys, key=lambda p: abs(signed_area(p)))))
    outers = [p for p in polys if math.copysign(1, signed_area(p)) == outer_sign]
    holes = [p for p in polys if math.copysign(1, signed_area(p)) != outer_sign]

    triangles = []
    for outer in outers:
        merged = outer if signed_area(outer) > 0 else outer[::-1]
        own = [h for h in holes if contains(outer, h[0]) and
               min((o for o in outers if contains(o, h[0])), key=lambda o: abs(signed_area(o))) is outer]
        for hole in sorted(own, key=lambda h: -max(x for x, _ in h)):
            merged = bridge(merged, hole if signed_area(hole) < 0 else hole[::-1])
        triangles += ear_clip(merged)
    return triangles


class VectorFont:
    def __init__(self, path: Path, weight: int):
        font = instantiateVariableFont(TTFont(str(path)), {"wght": weight})
        self.units = font["head"].unitsPerEm
        self.cmap = font.getBestCmap()
        self.glyphs = font.getGlyphSet()
        self.cache: dict[str, list[Triangle]] = {}

    def advance(self, ch: str) -> float:
        return self.glyphs[self.cmap[ord(ch)]].width

    def height(self, ch: str) -> float:
        return max(y for tri in self.triangles(ch) for _, y in tri)

    def triangles(self, ch: str) -> list[Triangle]:
        if ch not in self.cache:
            pen = FlattenPen(self.glyphs)
            self.glyphs[self.cmap[ord(ch)]].draw(pen)
            self.cache[ch] = triangulate(pen.contours) if pen.contours else []
        return self.cache[ch]


def glyph_triangles(face: VectorFont, text: str, centre: Point, em: float, tracking: float = 0.0,
                    fixed_advance: float | None = None) -> list[list[Triangle]]:
    scale = em / face.units
    advances = [fixed_advance or face.advance(ch) for ch in text]
    width = sum(advances) + tracking * face.units * (len(text) - 1)
    cap = face.height("H" if text[0].isalpha() else "8")
    x = -width / 2
    glyphs = []
    for ch, advance in zip(text, advances):
        offset = x + (advance - face.advance(ch)) / 2
        glyphs.append([tuple((centre[0] + (px + offset) * scale, centre[1] + (py - cap / 2) * scale) for px, py in tri)
                       for tri in face.triangles(ch)])
        x += advance + tracking * face.units
    return [glyph for glyph in glyphs if glyph]


def bounds(triangles: list[Triangle], margin: float = 0.0) -> tuple[float, float, float, float]:
    xs = [x for tri in triangles for x, _ in tri]
    ys = [y for tri in triangles for _, y in tri]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def rounded_rect(centre: Point, half_w: float, half_h: float, radius: float) -> list[Triangle]:
    radius = min(radius, half_w, half_h)
    corners = [(half_w - radius, half_h - radius, 0), (-half_w + radius, half_h - radius, 90),
               (-half_w + radius, -half_h + radius, 180), (half_w - radius, -half_h + radius, 270)]
    ring = [(centre[0] + cx + radius * math.cos(math.radians(start + 90 * i / CORNER_STEPS)),
             centre[1] + cy + radius * math.sin(math.radians(start + 90 * i / CORNER_STEPS)))
            for cx, cy, start in corners for i in range(CORNER_STEPS + 1)]
    return [(centre, ring[i - 1], ring[i]) for i in range(len(ring))]
