import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROAD_COLOURS = {"FF636363", "FF828282", "FF8C8C8C", "FF969696", "FFA0A0A0", "FFB4B4B4", "FFDCDCDC"}
ORIGIN_X, ORIGIN_Y = -4500.0, -4500.0
ROOT_SIZE = 1200.0
MIN_SIZE = 150.0
SPLIT_DENSITY = 0.0005
MIN_ROAD_TRIANGLES = 6
FIRST_CODE = 100
ROW_HEIGHT = 300.0


@dataclass(frozen=True)
class Postal:
    code: str
    x: float
    y: float


def road_centroids(mesh_path: Path) -> np.ndarray:
    rows = []
    with mesh_path.open() as mesh:
        for line in mesh:
            cols = line.rstrip("\n").split("\t")
            if cols[0] not in ROAD_COLOURS:
                continue
            xs = [float(cols[i]) for i in (1, 3, 5)]
            ys = [float(cols[i]) for i in (2, 4, 6)]
            rows.append((sum(xs) / 3, sum(ys) / 3))
    return np.array(rows)


def split_cells(points: np.ndarray, x: float, y: float, size: float) -> list[tuple[float, float, float, np.ndarray]]:
    inside = points[(points[:, 0] >= x) & (points[:, 0] < x + size) & (points[:, 1] >= y) & (points[:, 1] < y + size)]
    if len(inside) < MIN_ROAD_TRIANGLES:
        return []
    if size <= MIN_SIZE or len(inside) / (size * size) < SPLIT_DENSITY:
        return [(x, y, size, inside)]
    half = size / 2
    return [cell for dx in (0, half) for dy in (0, half) for cell in split_cells(inside, x + dx, y + dy, half)]


def snap_to_road(cell: tuple[float, float, float, np.ndarray]) -> tuple[float, float]:
    x, y, size, inside = cell
    centre = np.array([x + size / 2, y + size / 2])
    nearest = inside[np.argmin(np.sum((inside - centre) ** 2, axis=1))]
    return float(nearest[0]), float(nearest[1])


def build(points: np.ndarray) -> list[Postal]:
    cells = []
    for gx in np.arange(ORIGIN_X, 5000, ROOT_SIZE):
        for gy in np.arange(ORIGIN_Y, 8500, ROOT_SIZE):
            cells.extend(split_cells(points, gx, gy, ROOT_SIZE))
    snapped = sorted((snap_to_road(c) for c in cells), key=lambda p: (int((p[1] - ORIGIN_Y) // ROW_HEIGHT), p[0]))
    return [Postal(str(FIRST_CODE + i), round(px, 1), round(py, 1)) for i, (px, py) in enumerate(snapped)]


def write_lua(postals: list[Postal], out: Path) -> None:
    lines = ["---@type { code: string, x: number, y: number }[]", "return {"]
    lines += [f"    {{ code = '{p.code}', x = {p.x}, y = {p.y} }}," for p in postals]
    lines.append("}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    postals = build(road_centroids(args.mesh))
    write_lua(postals, args.out)
    print(f"{len(postals)} postals, {postals[0].code}..{postals[-1].code}")


if __name__ == "__main__":
    main()
