from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

NAMES = {
    "AIRP": "LSIA", "ALAMO": "Alamo Sea", "ALTA": "Alta", "ARMYB": "Fort Zancudo", "BANNING": "Banning",
    "BAYTRE": "Baytree Canyon", "BEACH": "Vespucci Beach", "BHAMCA": "Banham Canyon", "BRADP": "Braddock Pass",
    "BURTON": "Burton", "CANNY": "Raton Canyon", "CCREAK": "Cassidy Creek", "CHAMH": "Chamberlain Hills",
    "CHIL": "Vinewood Hills", "CHU": "Chumash", "CMSW": "Chiliad Wilderness", "CYPRE": "Cypress Flats", "DAVIS": "Davis",
    "DELBE": "Del Perro Beach", "DELPE": "Del Perro", "DELSOL": "Puerta Del Sol", "DESRT": "Grand Senora Desert",
    "DOWNT": "Downtown", "DTVINE": "Downtown Vinewood", "EAST_V": "East Vinewood", "EBURO": "El Burro Heights",
    "ELGORL": "El Gordo Lighthouse", "ELYSIAN": "Elysian Island", "GALFISH": "Galilee", "GALLI": "Galileo Park",
    "GOLF": "Golf Club", "GRAPES": "Grapeseed", "GREATC": "Great Chaparral", "HARMO": "Harmony", "HAWICK": "Hawick",
    "HORS": "Vinewood Racetrack", "HUMLAB": "Humane Labs", "JAIL": "Bolingbroke", "KOREAT": "Little Seoul",
    "LACT": "Land Act Reservoir", "LAGO": "Lago Zancudo", "LEGSQU": "Legion Square", "LMESA": "La Mesa",
    "LOSPUER": "La Puerta", "MIRR": "Mirror Park", "MORN": "Morningwood", "MOVIE": "Richards Majestic",
    "MTCHIL": "Mount Chiliad", "MTGORDO": "Mount Gordo", "MTJOSE": "Mount Josiah", "MURRI": "Murrieta Heights",
    "NCHU": "North Chumash", "NOOSE": "NOOSE", "OBSERV": "Galileo Observatory", "PALCOV": "Paleto Cove",
    "PALETO": "Paleto Bay", "PALFOR": "Paleto Forest", "PALHIGH": "Palomino Highlands",
    "PALMPOW": "Palmer-Taylor Power Station", "PBLUFF": "Pacific Bluffs", "PBOX": "Pillbox Hill",
    "PROCOB": "Procopio Beach", "RANCHO": "Rancho", "RGLEN": "Richman Glen", "RICHM": "Richman",
    "ROCKF": "Rockford Hills", "RTRAK": "Redwood Lights", "SANCHIA": "San Chianski Mountains",
    "SANDY": "Sandy Shores", "SKID": "Mission Row", "SLAB": "Stab City", "STAD": "Maze Bank Arena",
    "STRAW": "Strawberry", "TATAMO": "Tataviam Mountains", "TERMINA": "Terminal", "TEXTI": "Textile City",
    "TONGVAH": "Tongva Hills", "TONGVAV": "Tongva Valley", "VCANA": "Vespucci Canals", "VESP": "Vespucci",
    "VINE": "Vinewood", "WINDF": "Wind Farm", "WVINE": "West Vinewood", "ZANCUDO": "Zancudo River",
    "ZQ_UAR": "Davis Quartz",
}

REGIONS = {"CHIL", "MTCHIL", "MTGORDO", "MTJOSE", "DESRT", "TATAMO", "PALHIGH", "SANCHIA", "CMSW", "GREATC",
           "TONGVAH", "CANNY", "BHAMCA", "PALFOR"}
WATER = {"ALAMO", "LAGO", "LACT", "ZANCUDO"}
SMALL_AREA = 50_000.0


@dataclass(frozen=True)
class District:
    code: str
    name: str
    x: float
    y: float
    area: float
    tier: str
    boxes: tuple[tuple[float, float, float, float], ...]


def load_boxes(popzone: Path) -> dict[str, list[tuple[float, float, float, float]]]:
    boxes = defaultdict(list)
    for line in popzone.read_text(encoding="utf-8", errors="ignore").splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 9:
            continue
        x1, y1, _, x2, y2, _ = map(float, cols[1:7])
        boxes[cols[7].upper()].append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    return boxes


def anchor(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float]:
    areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
    total = sum(areas)
    cx = sum((b[0] + b[2]) / 2 * a for b, a in zip(boxes, areas)) / total
    cy = sum((b[1] + b[3]) / 2 * a for b, a in zip(boxes, areas)) / total
    if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes):
        return cx, cy
    largest = boxes[areas.index(max(areas))]
    return (largest[0] + largest[2]) / 2, (largest[1] + largest[3]) / 2


def tier(code: str, area: float) -> str:
    if code in WATER:
        return "water"
    if code in REGIONS:
        return "region"
    return "small" if area < SMALL_AREA else "district"


def load_districts(popzone: Path) -> list[District]:
    districts = []
    for code, boxes in load_boxes(popzone).items():
        if code not in NAMES:
            continue
        area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes)
        x, y = anchor(boxes)
        districts.append(District(code, NAMES[code], x, y, area, tier(code, area), tuple(boxes)))
    return districts
