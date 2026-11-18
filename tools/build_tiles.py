import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

from districts import District, load_districts
from vector_text import VectorFont, bounds, glyph_triangles, rounded_rect

WORLD_LEFT, WORLD_TOP, WORLD_SIZE_PER_TILE = -4140.0, 8400.0, 4500.0
ROWS, COLS = 3, 2
SOURCE_TILE = 1024
TILE = 2048
SUPERSAMPLE = 2
CANVAS = TILE * SUPERSAMPLE
CULL_MARGIN = 96
LOW_TILE = 512
LOD_SIZE = 128

def dxt_exact(hex_colour: str) -> str:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    r5, g6, b5 = round(r * 31 / 255), round(g * 63 / 255), round(b * 31 / 255)
    return "#{:02X}{:02X}{:02X}".format((r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2))


INK = dxt_exact("#0A0A0A")
STOCK_SEA = "#384A50"
ARTWORK_BACKGROUND_TOLERANCE = 60
FLOOD_SENTINEL = (255, 0, 255)
PAPER = "#FAFAFA"
COBALT = "#5078D7"
SHORE = dxt_exact("#1C2A45")
LAND = dxt_exact("#171717")
BUILDING = dxt_exact("#212121")
ROAD_MINOR = dxt_exact("#313131")
ROAD_STREET = dxt_exact("#404040")
ROAD_FREEWAY = dxt_exact("#737373")
SHORE_MIN_LUM = 0xB0

LAYERS = ["shore", "land", "building", "minor", "street", "freeway"]
KNOCKOUT_LAYERS = {"building", "minor", "street", "freeway"}
LAYER_COLOURS = {
    "shore": SHORE, "land": LAND, "building": BUILDING,
    "minor": ROAD_MINOR, "street": ROAD_STREET, "freeway": ROAD_FREEWAY,
}


@dataclass(frozen=True)
class LabelStyle:
    size: int
    colour: str
    tracking: float
    upper: bool


LABEL_STYLES = {
    "water": LabelStyle(15, dxt_exact("#737373"), 0.2, True),
    "region": LabelStyle(19, dxt_exact("#525252"), 0.32, True),
    "district": LabelStyle(13, dxt_exact("#A3A3A3"), 0.14, True),
    "small": LabelStyle(10, dxt_exact("#737373"), 0.12, True),
}
POSTAL = LabelStyle(12, dxt_exact("#141414"), 0.0, False)
LABEL_ORDER = ["water", "district", "region", "small"]
LABEL_PADDING = 6
HALO = 1.5
OCEAN_LABELS = [("Pacific Ocean", -3650.0, -300.0)]

SIGN_LINE = dxt_exact("#2E2E2E")
SIGN_PLATE = dxt_exact("#A3A3A3")
SIGN_PADDING = (3.5, 2.5)
SIGN_RADIUS = 1.5
SIGN_KEYLINE = 1.0
SIGN_GAP = 2.0
SIGN_SPACING = 2.0
SIGN_DIRECTIONS = [(1, 0), (-1, 0), (0, -1), (0, 1), (1, -1), (-1, -1), (1, 1), (-1, 1)]
ROAD_LAYERS = ["minor", "street", "freeway"]
ROAD_SAMPLE = 4
OVERLAY_Z = {"plate": 13.0, "keyline": 13.5, "panel": 14.0, "text": 15.0}

BRAND_CENTRE = (-2958.0, 7218.0)
BRAND_MASCOT_HEIGHT = 640
BRAND_MARK_SIZE = 72
BRAND_TEXT_SIZE = 64
BRAND_GAP = 72

MARK_HEAD = [(14, 14), (44, 36), (60, 44), (76, 36), (106, 14), (101, 74)]


@dataclass(frozen=True)
class Label:
    text: str
    style: LabelStyle
    x: float
    y: float


def layer_of(argb: str) -> str:
    value = int(argb, 16)
    r, g, b = (value >> 16) & 255, (value >> 8) & 255, value & 255
    if not r == g == b:
        return "shore" if (r + g + b) / 3 >= SHORE_MIN_LUM else "deep"
    if r <= 0x1D:
        return "land"
    if r < 0x50:
        return "building"
    if r == 0xB4:
        return "street"
    if r == 0xDC:
        return "freeway"
    return "minor"


def game_colour(hex_colour: str) -> str:
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    return f"FF{b}{g}{r}".upper()


def vertex_colour(argb: str) -> str:
    layer = layer_of(argb)
    return game_colour(STOCK_SEA if layer == "deep" else LAYER_COLOURS[layer])


def world_to_global(x: float, y: float) -> tuple[float, float]:
    scale = CANVAS / WORLD_SIZE_PER_TILE
    return (x - WORLD_LEFT) * scale, (WORLD_TOP - y) * scale


def load_layers(mesh_path: Path) -> dict[str, list[list[tuple[float, float]]]]:
    layers: dict[str, list] = {name: [] for name in LAYERS}
    with mesh_path.open() as mesh:
        for line in mesh:
            cols = line.rstrip("\n").split("\t")
            layer = layer_of(cols[0])
            if layer in layers:
                corners = [float(v) for v in cols[1:7]]
                layers[layer].append([world_to_global(corners[i], corners[i + 1]) for i in (0, 2, 4)])
    return layers


def load_postals(lua_path: Path) -> list[tuple[str, float, float]]:
    pattern = re.compile(r"code = '(\w+)', x = (-?[\d.]+), y = (-?[\d.]+)")
    return [(m[1], float(m[2]), float(m[3])) for m in pattern.finditer(lua_path.read_text(encoding="utf-8"))]


def font(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    face = ImageFont.truetype(str(path), size)
    face.set_variation_by_axes([weight])
    return face


def label_box(label: Label, face: ImageFont.FreeTypeFont) -> tuple[float, float, float, float]:
    width, cap = text_metrics(label, face)
    pad = LABEL_PADDING * SUPERSAMPLE
    return label.x - width / 2 - pad, label.y - cap / 2 - pad, label.x + width / 2 + pad, label.y + cap / 2 + pad


def text_metrics(label: Label, face: ImageFont.FreeTypeFont) -> tuple[float, float]:
    tracking = label.style.tracking * face.size
    width = sum(face.getlength(ch) for ch in label.text) + tracking * (len(label.text) - 1)
    cap = -face.getbbox("H", anchor="ls")[1]
    return width, cap


def overlaps(box, placed) -> bool:
    return any(box[0] < p[2] and box[2] > p[0] and box[1] < p[3] and box[3] > p[1] for p in placed)


def digit_advance(face: ImageFont.FreeTypeFont) -> float:
    return max(face.getlength(d) for d in "0123456789")


def sign_box(x: float, y: float, text: str, face: ImageFont.FreeTypeFont) -> tuple[float, float, float, float]:
    cap = -face.getbbox("8", anchor="ls")[1]
    half_w = len(text) * digit_advance(face) / 2 + (SIGN_PADDING[0] + 2 * SIGN_KEYLINE) * SUPERSAMPLE
    half_h = cap / 2 + (SIGN_PADDING[1] + 2 * SIGN_KEYLINE) * SUPERSAMPLE
    return x - half_w, y - half_h, x + half_w, y + half_h


def road_coverage(layers) -> np.ndarray:
    scale = 1 / ROAD_SAMPLE
    mask = Image.new("L", (round(CANVAS * COLS * scale), round(CANVAS * ROWS * scale)), 0)
    draw = ImageDraw.Draw(mask)
    for layer in ROAD_LAYERS:
        for tri in layers[layer]:
            draw.polygon([(x * scale, y * scale) for x, y in tri], fill=1)
    return np.pad(np.asarray(mask, dtype=np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def road_cover(integral: np.ndarray, box) -> int:
    h, w = integral.shape[0] - 1, integral.shape[1] - 1
    x1, y1, x2, y2 = (round(v / ROAD_SAMPLE) for v in box)
    x1, x2 = min(max(x1, 0), w), min(max(x2, 0), w)
    y1, y2 = min(max(y1, 0), h), min(max(y2, 0), h)
    return int(integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1])


def place_postals(postals, face, roads: np.ndarray, placed_boxes: list) -> list[Label]:
    labels = []
    spacing = SIGN_SPACING * SUPERSAMPLE
    for code, x, y in postals:
        gx, gy = world_to_global(x, y)
        x1, y1, x2, y2 = sign_box(0, 0, code, face)
        reach_x, reach_y = (x2 - x1) / 2 + SIGN_GAP * SUPERSAMPLE, (y2 - y1) / 2 + SIGN_GAP * SUPERSAMPLE
        candidates = []
        for ring in (1.0, 2.0):
            for dx, dy in SIGN_DIRECTIONS:
                cx, cy = gx + dx * reach_x * ring, gy + dy * reach_y * ring
                box = sign_box(cx, cy, code, face)
                padded = (box[0] - spacing, box[1] - spacing, box[2] + spacing, box[3] + spacing)
                if not overlaps(padded, placed_boxes):
                    candidates.append((road_cover(roads, box), ring, cx, cy, padded))
            if candidates:
                break
        if not candidates:
            continue
        _, _, cx, cy, padded = min(candidates, key=lambda c: (c[0], c[1]))
        placed_boxes.append(padded)
        labels.append(Label(code, POSTAL, cx, cy))
    return labels


def place_labels(districts: list[District], postals, faces, roads: np.ndarray) -> list[Label]:
    placed_boxes = []
    labels = []

    def try_place(candidates: list[Label]) -> None:
        for candidate in candidates:
            box = label_box(candidate, faces[candidate.style])
            if not overlaps(box, placed_boxes):
                placed_boxes.append(box)
                labels.append(candidate)
                return

    for text, x, y in OCEAN_LABELS:
        try_place([Label(text.upper(), LABEL_STYLES["water"], *world_to_global(x, y))])

    for tier in LABEL_ORDER:
        style = LABEL_STYLES[tier]
        for district in sorted((d for d in districts if d.tier == tier), key=lambda d: -d.area):
            gx, gy = world_to_global(district.x, district.y)
            text = district.name.upper() if style.upper else district.name
            step = style.size * SUPERSAMPLE * 1.6
            try_place([Label(text, style, gx, gy + dy) for dy in (0, -step, step)])

    return labels + place_postals(postals, faces[POSTAL], roads, placed_boxes)


def visible(points, origin) -> bool:
    xs = [p[0] - origin[0] for p in points]
    ys = [p[1] - origin[1] for p in points]
    return max(xs) > -CULL_MARGIN and min(xs) < CANVAS + CULL_MARGIN and max(ys) > -CULL_MARGIN and min(ys) < CANVAS + CULL_MARGIN


def layer_mask(triangles, origin) -> Image.Image:
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    draw = ImageDraw.Draw(mask)
    for tri in triangles:
        if visible(tri, origin):
            draw.polygon([(x - origin[0], y - origin[1]) for x, y in tri], fill=255)
    return mask


def to_canvas(points, origin) -> list[tuple[float, float]]:
    return [(gx - origin[0], gy - origin[1]) for gx, gy in (world_to_global(x, y) for x, y in points)]


def knock_out(mask: Image.Image, knockouts, origin) -> None:
    draw = ImageDraw.Draw(mask)
    for x1, y1, x2, y2 in knockouts:
        (left, top), (right, bottom) = to_canvas([(x1, y2), (x2, y1)], origin)
        if right > 0 and bottom > 0 and left < CANVAS and top < CANVAS:
            draw.rectangle((left, top, right, bottom), fill=0)


def build_tile(row: int, col: int, layers, overlays: list["Overlay"], branding: Image.Image) -> Image.Image:
    origin = (col * CANVAS, row * CANVAS)
    base = Image.new("RGB", (CANVAS, CANVAS), STOCK_SEA)
    alpha = Image.new("L", (CANVAS, CANVAS), 0)
    knockouts = [box for overlay in overlays for box in overlay.knockouts]

    for layer in LAYERS:
        mask = layer_mask(layers[layer], origin)
        if layer in KNOCKOUT_LAYERS:
            knock_out(mask, knockouts, origin)
        base.paste(LAYER_COLOURS[layer], (0, 0, CANVAS, CANVAS), mask)
        alpha.paste(255, (0, 0, CANVAS, CANVAS), mask)

    bx, by = world_to_global(*BRAND_CENTRE)
    position = (round(bx - origin[0] - branding.width / 2), round(by - origin[1] - branding.height / 2))
    branding_alpha = branding.getchannel("A")
    base.paste(branding.convert("RGB"), position, branding_alpha)
    alpha.paste(255, (*position, position[0] + branding.width, position[1] + branding.height), branding_alpha)

    draw = ImageDraw.Draw(base)
    draw_alpha = ImageDraw.Draw(alpha)
    for shape in (shape for overlay in overlays for shape in overlay.shapes):
        for tri in shape.triangles:
            points = to_canvas(tri, origin)
            if visible(points, (0, 0)):
                draw.polygon(points, fill=shape.colour)
                draw_alpha.polygon(points, fill=255)

    base.putalpha(alpha)
    return base.resize((TILE, TILE), Image.LANCZOS)


def on_stock_sea(image: Image.Image) -> Image.Image:
    sea = Image.new("RGBA", image.size, STOCK_SEA)
    sea.alpha_composite(image)
    return sea.convert("RGB")


def arc_points(cx: float, cy: float, r: float, start: float, end: float, steps: int = 64) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in np.linspace(start, end, steps)]


def cubic(p0, p1, p2, p3, steps: int = 32) -> list[tuple[float, float]]:
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                  for a, b, c, d in zip(p0, p1, p2, p3)) for t in np.linspace(0, 1, steps)]


def render_mark(size: int) -> Image.Image:
    unit = size * 8 / 120
    image = Image.new("RGBA", (size * 8, size * 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = lambda pts: [(x * unit, y * unit) for x, y in pts]
    head = MARK_HEAD + cubic((101, 74), (100, 96), (84, 108), (60, 108)) + cubic((60, 108), (36, 108), (20, 96), (19, 74))
    draw.polygon(s(head), fill=PAPER)
    stroke = round(7 * unit)
    c_eye = s(arc_points(44.015, 62, 13, -45, -315))
    draw.line(c_eye, fill=INK, width=stroke, joint="curve")
    for x, y in (c_eye[0], c_eye[-1]):
        draw.ellipse((x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2), fill=INK)
    draw.ellipse(s([(64, 50), (88, 74)]), outline=INK, width=stroke)
    draw.ellipse(s([(71.5, 57.5), (80.5, 66.5)]), fill=COBALT)
    draw.polygon(s([(55.5, 79), (64.5, 79), (60, 87)]), fill=INK)
    return image.resize((size, size), Image.LANCZOS)


def trim_to_artwork(image: Image.Image) -> Image.Image:
    ink = Image.new("RGB", image.size, INK)
    return image.crop(ImageChops.difference(image, ink).convert("L").point(lambda v: 255 if v > 8 else 0).getbbox())


def render_branding(mascot_path: Path, font_path: Path) -> Image.Image:
    k = SUPERSAMPLE
    mascot = trim_to_artwork(Image.open(mascot_path).convert("RGB"))
    mascot = mascot.resize((round(mascot.width * BRAND_MASCOT_HEIGHT * k / mascot.height), BRAND_MASCOT_HEIGHT * k), Image.LANCZOS)
    for corner in ((0, 0), (mascot.width - 1, 0), (0, mascot.height - 1), (mascot.width - 1, mascot.height - 1)):
        ImageDraw.floodfill(mascot, corner, FLOOD_SENTINEL, thresh=ARTWORK_BACKGROUND_TOLERANCE)
    pixels = np.array(mascot)
    background = (pixels == FLOOD_SENTINEL).all(axis=2)
    pixels[background] = ImageColor.getrgb(STOCK_SEA)
    mascot = Image.fromarray(pixels)
    mascot.putalpha(Image.fromarray(np.where(background, 0, 255).astype(np.uint8)))
    mark = render_mark(BRAND_MARK_SIZE * k)
    text_font = font(font_path, BRAND_TEXT_SIZE * k, 600)
    text_box = text_font.getbbox("Project Cobalt", anchor="ls")
    cap_height = -text_font.getbbox("C", anchor="ls")[1]
    gap = mark.width // 3
    lockup_width = mark.width + gap + (text_box[2] - text_box[0])
    width = max(mascot.width, lockup_width)
    height = mascot.height + BRAND_GAP * k + mark.height
    block = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    block.alpha_composite(mascot, ((width - mascot.width) // 2, 0))
    lockup_x = (width - lockup_width) // 2
    lockup_y = mascot.height + BRAND_GAP * k
    block.alpha_composite(mark, (lockup_x, lockup_y))
    eye_y = lockup_y + mark.height * 62 / 120
    ImageDraw.Draw(block).text((lockup_x + mark.width + gap, eye_y + cap_height / 2), "Project Cobalt",
                               font=text_font, fill=PAPER, anchor="ls")
    return block


def global_to_world(x: float, y: float) -> tuple[float, float]:
    scale = CANVAS / WORLD_SIZE_PER_TILE
    return x / scale + WORLD_LEFT, WORLD_TOP - y / scale


@dataclass(frozen=True)
class Shape:
    colour: str
    z: float
    triangles: list


@dataclass(frozen=True)
class Overlay:
    shapes: list[Shape]
    knockouts: list[tuple[float, float, float, float]]


def build_overlay(label: Label, face: VectorFont) -> Overlay:
    world_px = WORLD_SIZE_PER_TILE / (CANVAS / SUPERSAMPLE)
    centre = global_to_world(label.x, label.y)
    em = label.style.size * world_px
    if label.style is not POSTAL:
        glyphs = glyph_triangles(face, label.text, centre, em, label.style.tracking)
        text = [tri for glyph in glyphs for tri in glyph]
        return Overlay([Shape(label.style.colour, OVERLAY_Z["text"], text)],
                       [bounds(glyph, HALO * world_px) for glyph in glyphs])

    advance = max(face.advance(d) for d in "0123456789")
    scale = em / face.units
    half_w = len(label.text) * advance * scale / 2 + SIGN_PADDING[0] * world_px
    half_h = face.height("8") * scale / 2 + SIGN_PADDING[1] * world_px
    radius = SIGN_RADIUS * world_px
    keyline = SIGN_KEYLINE * world_px
    plate = rounded_rect(centre, half_w + 2 * keyline, half_h + 2 * keyline, radius + 2 * keyline)
    digits = glyph_triangles(face, label.text, centre, em, fixed_advance=advance)
    return Overlay([
        Shape(SIGN_PLATE, OVERLAY_Z["plate"], plate),
        Shape(SIGN_LINE, OVERLAY_Z["keyline"], rounded_rect(centre, half_w + keyline, half_h + keyline, radius + keyline)),
        Shape(SIGN_PLATE, OVERLAY_Z["panel"], rounded_rect(centre, half_w, half_h, radius)),
        Shape(label.style.colour, OVERLAY_Z["text"], [tri for glyph in digits for tri in glyph]),
    ], [bounds(plate)])


def write_overlays(overlays: list[Overlay], out: Path) -> int:
    count = 0
    with (out / "overlay.tsv").open("w", newline="\n") as shapes, (out / "knockouts.tsv").open("w", newline="\n") as holes:
        for index, overlay in enumerate(overlays):
            for shape in overlay.shapes:
                for tri in shape.triangles:
                    coords = "\t".join(f"{v:.2f}" for point in tri for v in point)
                    shapes.write(f"{index}\t{game_colour(shape.colour)}\t{shape.z}\t{coords}\n")
                    count += 1
            for box in overlay.knockouts:
                holes.write("\t".join(f"{v:.2f}" for v in box) + "\n")
    return count


def save_dds(image: Image.Image, folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pixel_format = "DXT5" if image.mode == "RGBA" else "DXT1"
    image.save(folder / f"{name}.dds", "DDS", pixel_format=pixel_format)


def save_renders(full: Image.Image, orig: Path, renders: Path) -> None:
    renders.mkdir(parents=True, exist_ok=True)
    before = Image.new("RGBA", (SOURCE_TILE * COLS, SOURCE_TILE * ROWS), (64, 80, 80, 255))
    for row in range(ROWS):
        for col in range(COLS):
            name = f"minimap_sea_{row}_{col}"
            tile = Image.open(orig / name / f"{name}.dds").convert("RGBA")
            before.alpha_composite(tile, (col * SOURCE_TILE, row * SOURCE_TILE))
    before.convert("RGB").resize((1024, 1536), Image.LANCZOS).save(renders / "before.png")
    full.resize((1024, 1536), Image.LANCZOS).save(renders / "after.png")
    full.crop((1500, 3400, 2700, 4400)).save(renders / "after-los-santos.png")
    full.crop((1700, 1400, 2900, 2400)).save(renders / "after-county.png")
    bx, by = world_to_global(*BRAND_CENTRE)
    bx, by = bx / SUPERSAMPLE, by / SUPERSAMPLE
    left, top = max(0, round(bx - 600)), max(0, round(by - 600))
    full.crop((left, top, min(full.width, left + 1200), min(full.height, top + 1200))).save(renders / "after-branding.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orig", type=Path, required=True)
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--popzone", type=Path, required=True)
    parser.add_argument("--postals", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--mascot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--renders", type=Path, required=True)
    args = parser.parse_args()

    layers = load_layers(args.mesh)
    districts = load_districts(args.popzone)
    faces = {style: font(args.font, style.size * SUPERSAMPLE, 600) for style in [*LABEL_STYLES.values(), POSTAL]}
    labels = place_labels(districts, load_postals(args.postals), faces, road_coverage(layers))
    vector_font = VectorFont(args.font, 600)
    overlays = [build_overlay(label, vector_font) for label in labels]
    branding = render_branding(args.mascot, args.font)

    full = Image.new("RGB", (TILE * COLS, TILE * ROWS))
    for row in range(ROWS):
        for col in range(COLS):
            tile = build_tile(row, col, layers, overlays, branding)
            name = f"minimap_sea_{row}_{col}"
            save_dds(tile, args.out / name, name)
            low_name = f"minimap_{row}_{col}"
            save_dds(on_stock_sea(tile.resize((LOW_TILE, LOW_TILE), Image.LANCZOS)), args.out / low_name, low_name)
            full.paste(on_stock_sea(tile), (col * TILE, row * TILE))
            print(name)

    save_dds(full.resize((LOD_SIZE, LOD_SIZE), Image.LANCZOS), args.out / "minimap_lod_128", "minimap_lod_128")

    colours = sorted({line.split("\t")[0] for line in args.mesh.open()})
    (args.out / "vertex_colours.tsv").write_text("".join(f"{c}\t{vertex_colour(c)}\n" for c in colours))

    print(f"{write_overlays(overlays, args.out)} overlay triangles")

    save_renders(full, args.orig, args.renders)
    print(f"{sum(1 for l in labels if l.style is not POSTAL)} area labels, "
          f"{sum(1 for l in labels if l.style is POSTAL)} postal labels")


if __name__ == "__main__":
    main()
