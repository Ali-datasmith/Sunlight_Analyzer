"""Scenario and Building data model for Sunlight & Shadow Analyzer (SSA).

Manages buildings, 2m snapping, placement validation, revision tracking,
and JSON serialization. Strictly uses math and json; no prohibited imports.
"""

import json

from geometry import Vec3

CELL_SIZE_M = 2.0
GROUND_CELLS = (30, 30)  # 60m x 60m
MAX_BUILDINGS = 15
DEFAULT_LAT = 31.5204
DEFAULT_LON = 74.3587
DEFAULT_TZ = 5.0

BUILDING_PALETTE = [
    "#D98E73",  # Terracotta / Coral
    "#8FB8DE",  # Soft Blue
    "#E6C65C",  # Ochre / Gold
    "#9CC59A",  # Sage Green
    "#B7A1D1",  # Lavender
    "#C9C9C9",  # Slate Gray
]

CITY_PRESETS: dict[str, tuple[float, float, float]] = {
    "Lahore": (31.5204, 74.3587, 5.0),
    "Karachi": (24.8607, 67.0011, 5.0),
    "Islamabad": (33.6844, 73.0479, 5.0),
    "London": (51.5074, -0.1278, 0.0),
    "New York": (40.7128, -74.0060, -5.0),
    "Sydney": (-33.8688, 151.2093, 10.0),
}


class Building:
    """Axis-aligned box building on a 2m ground grid."""

    def __init__(
        self,
        id: int,
        label: str,
        position: Vec3,
        size: Vec3,
        color: str = "#D98E73",
    ):
        self.id = int(id)
        self.label = str(label)[:12]
        self.position = Vec3(float(position.x), float(position.y), 0.0)
        self.size = Vec3(float(size.x), float(size.y), float(size.z))
        self.color = str(color)

    @property
    def min_point(self) -> Vec3:
        return self.position

    @property
    def max_point(self) -> Vec3:
        return Vec3(
            self.position.x + self.size.x,
            self.position.y + self.size.y,
            self.position.z + self.size.z,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "position": [self.position.x, self.position.y, self.position.z],
            "size": [self.size.x, self.size.y, self.size.z],
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Building":
        pos = Vec3(data["position"][0], data["position"][1], data["position"][2])
        size = Vec3(data["size"][0], data["size"][1], data["size"][2])
        return cls(
            id=data["id"],
            label=data["label"],
            position=pos,
            size=size,
            color=data.get("color", "#D98E73"),
        )


class Scenario:
    """Site planning scenario holding buildings, geographic coordinates, and grid size."""

    def __init__(
        self,
        name: str = "A",
        ground_size: tuple[int, int] = GROUND_CELLS,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        tz_offset: float = DEFAULT_TZ,
        cell_size_m: float = CELL_SIZE_M,
    ):
        self.name = str(name)
        self.ground_size = (int(ground_size[0]), int(ground_size[1]))
        self.lat = float(lat)
        self.lon = float(lon)
        self.tz_offset = float(tz_offset)
        self.cell_size_m = float(cell_size_m)
        self.buildings: list[Building] = []
        self.next_id: int = 1
        self.revision: int = 0

    @property
    def ground_width_m(self) -> float:
        return self.ground_size[0] * self.cell_size_m

    @property
    def ground_depth_m(self) -> float:
        return self.ground_size[1] * self.cell_size_m

    def touch(self) -> None:
        """Increments revision to notify renderers and heatmap caches."""
        self.revision += 1

    def can_place(
        self,
        pos: Vec3,
        size: Vec3,
        exclude_id: int | None = None,
    ) -> bool:
        """Validates that a box building fits within site bounds and does not overlap existing buildings."""
        # 1. Bounds check
        if pos.x < -1e-6 or pos.y < -1e-6:
            return False
        if pos.x + size.x > self.ground_width_m + 1e-6:
            return False
        if pos.y + size.y > self.ground_depth_m + 1e-6:
            return False

        # 2. Overlap check with other buildings (open interval intersection)
        bx1 = pos.x
        by1 = pos.y
        bx2 = pos.x + size.x
        by2 = pos.y + size.y

        for b in self.buildings:
            if exclude_id is not None and b.id == exclude_id:
                continue
            ox1 = b.position.x
            oy1 = b.position.y
            ox2 = b.position.x + b.size.x
            oy2 = b.position.y + b.size.y

            # Overlap in 2D if intervals intersect by more than epsilon
            overlap_x = min(bx2, ox2) - max(bx1, ox1)
            overlap_y = min(by2, oy2) - max(by1, oy1)
            if overlap_x > 1e-6 and overlap_y > 1e-6:
                return False

        return True

    def find_free_spot(self, size: Vec3) -> Vec3 | None:
        """Finds first free position snapped to 2m grid starting from center outward."""
        cs = self.cell_size_m
        gw = int(self.ground_size[0])
        gd = int(self.ground_size[1])
        req_w = int(round(size.x / cs))
        req_d = int(round(size.y / cs))

        # Search grid
        for y_idx in range(gd - req_d + 1):
            for x_idx in range(gw - req_w + 1):
                pos = Vec3(x_idx * cs, y_idx * cs, 0.0)
                if self.can_place(pos, size):
                    return pos
        return None

    def add_building(self, building: Building) -> bool:
        """Adds a building to scenario if limit not reached and placement is valid."""
        if len(self.buildings) >= MAX_BUILDINGS:
            return False
        if not self.can_place(building.position, building.size, exclude_id=building.id):
            return False

        self.buildings.append(building)
        if building.id >= self.next_id:
            self.next_id = building.id + 1
        self.touch()
        return True

    def remove_building(self, building_id: int) -> bool:
        """Removes building by ID."""
        orig_len = len(self.buildings)
        self.buildings = [b for b in self.buildings if b.id != building_id]
        if len(self.buildings) != orig_len:
            self.touch()
            return True
        return False

    def move_building(self, building_id: int, new_pos: Vec3) -> bool:
        """Moves building to a new snapped position if valid."""
        target = self.get_building(building_id)
        if target is None:
            return False

        # Snap position to cell size
        snapped_x = round(new_pos.x / self.cell_size_m) * self.cell_size_m
        snapped_y = round(new_pos.y / self.cell_size_m) * self.cell_size_m
        snapped_pos = Vec3(snapped_x, snapped_y, 0.0)

        if not self.can_place(snapped_pos, target.size, exclude_id=building_id):
            return False

        target.position = snapped_pos
        self.touch()
        return True

    def set_building_height(self, building_id: int, new_height: float) -> bool:
        """Adjusts building height (clamped 3..45m)."""
        target = self.get_building(building_id)
        if target is None:
            return False
        clamped = max(3.0, min(45.0, float(new_height)))
        target.size.z = clamped
        self.touch()
        return True

    def set_building_color(self, building_id: int, new_color: str) -> bool:
        """Updates building color."""
        target = self.get_building(building_id)
        if target is None:
            return False
        target.color = new_color
        self.touch()
        return True

    def get_building(self, building_id: int) -> Building | None:
        for b in self.buildings:
            if b.id == building_id:
                return b
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ground_size": list(self.ground_size),
            "lat": self.lat,
            "lon": self.lon,
            "tz_offset": self.tz_offset,
            "cell_size_m": self.cell_size_m,
            "next_id": self.next_id,
            "revision": self.revision,
            "buildings": [b.to_dict() for b in self.buildings],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scenario":
        sc = cls(
            name=data.get("name", "A"),
            ground_size=tuple(data.get("ground_size", GROUND_CELLS)),
            lat=data.get("lat", DEFAULT_LAT),
            lon=data.get("lon", DEFAULT_LON),
            tz_offset=data.get("tz_offset", DEFAULT_TZ),
            cell_size_m=data.get("cell_size_m", CELL_SIZE_M),
        )
        sc.next_id = data.get("next_id", 1)
        sc.revision = data.get("revision", 0)
        sc.buildings = [Building.from_dict(b) for b in data.get("buildings", [])]
        return sc

    def clone(self, new_name: str | None = None) -> "Scenario":
        """Clones scenario via JSON round-trip without importing copy module."""
        dumped = json.loads(json.dumps(self.to_dict()))
        cloned = Scenario.from_dict(dumped)
        if new_name is not None:
            cloned.name = new_name
        return cloned


def create_demo_scenario(name: str = "A") -> Scenario:
    """Creates the default 'Courtyard' demo scenario specified in Section 6.2 of plan.md:

    - B1 "Tower" at (8,8), 8x10x18 m
    - B2 "Block" at (30,12), 10x8x9 m
    - B3 "Annex" at (14,34), 12x8x6 m
    """
    sc = Scenario(name=name)
    b1 = Building(1, "Tower", Vec3(8.0, 8.0, 0.0), Vec3(8.0, 10.0, 18.0), BUILDING_PALETTE[0])
    b2 = Building(2, "Block", Vec3(30.0, 12.0, 0.0), Vec3(10.0, 8.0, 9.0), BUILDING_PALETTE[1])
    b3 = Building(3, "Annex", Vec3(14.0, 34.0, 0.0), Vec3(12.0, 8.0, 6.0), BUILDING_PALETTE[2])
    sc.add_building(b1)
    sc.add_building(b2)
    sc.add_building(b3)
    sc.next_id = 4
    sc.revision = 1
    return sc


def run_checks() -> list[tuple[str, bool, str]]:
    """Runs scenario self-tests based on Section 10.1 of plan.md."""
    results: list[tuple[str, bool, str]] = []

    # 1. Placement and overlap rejection
    sc = Scenario()
    b1 = Building(1, "Test1", Vec3(10.0, 10.0, 0.0), Vec3(10.0, 10.0, 10.0))
    sc.add_building(b1)

    # Overlap test
    overlap_pass = not sc.can_place(Vec3(15.0, 15.0, 0.0), Vec3(6.0, 6.0, 5.0))
    # Out of bounds test
    oob_pass = not sc.can_place(Vec3(55.0, 55.0, 0.0), Vec3(10.0, 10.0, 5.0))
    # Valid placement test
    valid_pass = sc.can_place(Vec3(30.0, 30.0, 0.0), Vec3(10.0, 10.0, 5.0))
    c1 = overlap_pass and oob_pass and valid_pass
    results.append(("Scenario: can_place overlap & boundary checks", c1, f"overlap={overlap_pass}, oob={oob_pass}, valid={valid_pass}"))

    # 2. JSON round-trip
    demo = create_demo_scenario("A")
    d_dict = demo.to_dict()
    restored = Scenario.from_dict(d_dict)
    c2 = (
        len(restored.buildings) == 3
        and restored.buildings[0].label == "Tower"
        and restored.buildings[0].size.z == 18.0
        and restored.revision == demo.revision
    )
    results.append(("Scenario: JSON serialization round-trip", c2, f"buildings={len(restored.buildings)}, rev={restored.revision}"))

    # 3. Revision counter increments on edit
    rev0 = demo.revision
    demo.set_building_height(1, 24.0)
    rev1 = demo.revision
    demo.move_building(1, Vec3(6.0, 6.0, 0.0))
    rev2 = demo.revision
    c3 = (rev1 > rev0) and (rev2 > rev1)
    results.append(("Scenario: Revision increments on mutation", c3, f"revs: {rev0} -> {rev1} -> {rev2}"))

    # 4. Max 15 buildings cap enforcement
    sc_full = Scenario()
    for i in range(15):
        added = sc_full.add_building(Building(i + 1, f"B{i+1}", Vec3((i % 5) * 4.0, (i // 5) * 4.0, 0.0), Vec3(2.0, 2.0, 5.0)))
        if not added:
            break
    add_16 = sc_full.add_building(Building(16, "B16", Vec3(20.0, 20.0, 0.0), Vec3(2.0, 2.0, 5.0)))
    c4 = len(sc_full.buildings) == 15 and (not add_16)
    results.append(("Scenario: Max 15 buildings limit enforcement", c4, f"count={len(sc_full.buildings)}, added_16={add_16}"))

    return results


if __name__ == "__main__":
    for name, passed, info in run_checks():
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {info}")
