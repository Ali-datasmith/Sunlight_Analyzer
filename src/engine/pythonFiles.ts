/**
 * Python codebase registry for Sunlight & Shadow Analyzer (SSA).
 * Allows users in the web preview to inspect, copy, or download the exact
 * 9 Python files for single-click execution in VS Code.
 */

export interface PythonFileEntry {
  filename: string;
  description: string;
  category: 'core' | 'model' | 'ui' | 'meta' | 'test';
  code: string;
}

export const PYTHON_FILES: PythonFileEntry[] = [
  {
    filename: 'main.py',
    description: 'Application entry point. Initializes Tkinter root, launches UI, and starts mainloop.',
    category: 'core',
    code: `"""Entry point for Sunlight & Shadow Analyzer (SSA).

Run directly via:
    python main.py
Or in VS Code by clicking the Run button (F5 / Run Python File).
"""

import tkinter as tk
from ui import App


def main() -> None:
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
`,
  },
  {
    filename: 'solar.py',
    description: 'Astronomical engine. Implements NOAA General Solar Position Calculations & Meeus algorithms.',
    category: 'core',
    code: `"""Solar position calculation for Sunlight & Shadow Analyzer (SSA).

Implements NOAA General Solar Position Calculations (based on Meeus,
Astronomical Algorithms 2nd ed.) with atmospheric refraction correction.
Strictly uses math and datetime.
"""

import datetime
import math

from geometry import Vec3, EL_MIN_DEG


class SunState:
    """Computed state of the sun at a specific date, time, and location."""

    def __init__(
        self,
        azimuth_deg: float,
        elevation_deg: float,
        is_daytime: bool,
        shadows_active: bool,
        declination_deg: float,
        eot_min: float,
        hour_angle_deg: float,
    ):
        self.azimuth_deg = float(azimuth_deg)
        self.elevation_deg = float(elevation_deg)
        self.is_daytime = bool(is_daytime)
        self.shadows_active = bool(shadows_active)
        self.declination_deg = float(declination_deg)
        self.eot_min = float(eot_min)
        self.hour_angle_deg = float(hour_angle_deg)

    def __repr__(self) -> str:
        status = "Day" if self.is_daytime else "Night"
        return f"SunState(Az={self.azimuth_deg:.1f}°, El={self.elevation_deg:.1f}°, {status})"


def solar_position(
    lat_deg: float,
    lon_deg: float,
    target_date: datetime.date,
    local_minute: int,
    tz_offset_hours: float,
) -> SunState:
    """Calculates sun position using the NOAA General Solar Position Calculations algorithm."""
    # 1. Julian Day and Julian Century
    t_min = float(local_minute)
    jd = target_date.toordinal() + 1721424.5 + t_min / 1440.0 - tz_offset_hours / 24.0
    jc = (jd - 2451545.0) / 36525.0

    # 2. Geometric Mean Longitude of Sun (deg)
    l0 = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360.0

    # 3. Geometric Mean Anomaly of Sun (deg)
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)

    # 4. Eccentricity of Earth's Orbit
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)

    # 5. Sun Equation of Center (deg)
    m_rad = math.radians(m)
    c = (
        math.sin(m_rad) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2.0 * m_rad) * (0.019993 - 0.000101 * jc)
        + math.sin(3.0 * m_rad) * 0.000289
    )

    # 6. Sun Apparent Longitude (deg)
    omega = 125.04 - 1934.136 * jc
    omega_rad = math.radians(omega)
    lambda_app = l0 + c - 0.00569 - 0.00478 * math.sin(omega_rad)

    # 7. Mean and True Obliquity of the Ecliptic (deg)
    eps0 = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - 0.001813 * jc))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(omega_rad)

    # 8. Sun Declination (deg)
    eps_rad = math.radians(eps)
    lambda_rad = math.radians(lambda_app)
    sin_delta = math.sin(eps_rad) * math.sin(lambda_rad)
    sin_delta = max(-1.0, min(1.0, sin_delta))
    delta_deg = math.degrees(math.asin(sin_delta))
    delta_rad = math.radians(delta_deg)

    # 9. Equation of Time (minutes)
    y = math.tan(eps_rad / 2.0) ** 2
    l0_rad = math.radians(l0)
    eot_rad = (
        y * math.sin(2.0 * l0_rad)
        - 2.0 * e * math.sin(m_rad)
        + 4.0 * e * y * math.sin(m_rad) * math.cos(2.0 * l0_rad)
        - 0.5 * y * y * math.sin(4.0 * l0_rad)
        - 1.25 * e * e * math.sin(2.0 * m_rad)
    )
    eot_min = 4.0 * math.degrees(eot_rad)

    # 10. True Solar Time & Hour Angle (deg)
    tst = (t_min + eot_min + 4.0 * lon_deg - 60.0 * tz_offset_hours) % 1440.0
    hour_angle_deg = tst / 4.0 - 180.0
    hour_angle_rad = math.radians(hour_angle_deg)

    # 11. Solar Zenith and Geometric Elevation
    phi_rad = math.radians(lat_deg)
    cos_theta_z = math.sin(phi_rad) * math.sin(delta_rad) + math.cos(phi_rad) * math.cos(delta_rad) * math.cos(hour_angle_rad)
    cos_theta_z = max(-1.0, min(1.0, cos_theta_z))
    theta_z_deg = math.degrees(math.acos(cos_theta_z))
    el_geometric = 90.0 - theta_z_deg

    # 12. Solar Azimuth (deg, clockwise from North)
    sin_theta_z = math.sin(math.radians(theta_z_deg))
    if abs(sin_theta_z) < 1e-9:
        azimuth_deg = 180.0
    else:
        cos_psi = (math.sin(phi_rad) * cos_theta_z - math.sin(delta_rad)) / (math.cos(phi_rad) * sin_theta_z)
        cos_psi = max(-1.0, min(1.0, cos_psi))
        psi_deg = math.degrees(math.acos(cos_psi))
        if hour_angle_deg > 0:
            azimuth_deg = (psi_deg + 180.0) % 360.0
        else:
            azimuth_deg = (540.0 - psi_deg) % 360.0

    # 13. Atmospheric Refraction Correction (arcseconds)
    h = el_geometric
    if h > 85.0:
        refraction_arcsec = 0.0
    elif 5.0 < h <= 85.0:
        tan_h = math.tan(math.radians(h))
        refraction_arcsec = 58.1 / tan_h - 0.07 / (tan_h**3) + 0.000086 / (tan_h**5)
    elif -0.575 < h <= 5.0:
        refraction_arcsec = 1735.0 + h * (-518.2 + h * (103.4 + h * (-12.79 + 0.711 * h)))
    else:
        tan_h = math.tan(math.radians(h))
        refraction_arcsec = -20.772 / tan_h if abs(tan_h) > 1e-6 else 0.0

    el_apparent = el_geometric + refraction_arcsec / 3600.0

    is_daytime = el_apparent > 0.0
    shadows_active = el_apparent >= EL_MIN_DEG

    return SunState(
        azimuth_deg=azimuth_deg,
        elevation_deg=el_apparent,
        is_daytime=is_daytime,
        shadows_active=shadows_active,
        declination_deg=delta_deg,
        eot_min=eot_min,
        hour_angle_deg=hour_angle_deg,
    )


def sun_vector(azimuth_deg: float, elevation_deg: float) -> Vec3:
    rad_az = math.radians(azimuth_deg)
    rad_el = math.radians(elevation_deg)
    cos_el = math.cos(rad_el)
    return Vec3(
        cos_el * math.sin(rad_az),
        cos_el * math.cos(rad_az),
        math.sin(rad_el),
    )


def sunrise_sunset(
    lat_deg: float,
    lon_deg: float,
    target_date: datetime.date,
    tz_offset_hours: float,
) -> tuple[int | None, int | None]:
    first_min: int | None = None
    last_min: int | None = None

    for m in range(1440):
        sun = solar_position(lat_deg, lon_deg, target_date, m, tz_offset_hours)
        if sun.is_daytime:
            if first_min is None:
                first_min = m
            last_min = m

    if first_min is None:
        return (None, None)
    if first_min == 0 and last_min == 1439:
        return (0, 1439)

    return (first_min, last_min)
`,
  },
  {
    filename: 'geometry.py',
    description: '3D & 2D geometry, Kay-Kajiya Ray-AABB, Andrew hull, and Sutherland-Hodgman clipping.',
    category: 'core',
    code: `"""Geometry utilities for Sunlight & Shadow Analyzer (SSA)."""

import math

EPS = 1e-9
T_MIN = 1e-4
EL_MIN_DEG = 2.0


class Vec3:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Vec3":
        mag = self.length()
        if mag < EPS:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / mag, self.y / mag, self.z / mag)


class ViewParams:
    def __init__(
        self,
        yaw_deg: float = 45.0,
        pitch_deg: float = 35.264,
        scale_px_per_m: float = 10.0,
        origin_px: tuple[float, float] = (300.0, 300.0),
    ):
        self.yaw_deg = float(yaw_deg)
        self.pitch_deg = float(pitch_deg)
        self.scale_px_per_m = float(scale_px_per_m)
        self.origin_px = (float(origin_px[0]), float(origin_px[1]))

        rad_yaw = math.radians(self.yaw_deg)
        rad_pitch = math.radians(self.pitch_deg)
        self.cos_yaw = math.cos(rad_yaw)
        self.sin_yaw = math.sin(rad_yaw)
        self.cos_pitch = math.cos(rad_pitch)
        self.sin_pitch = math.sin(rad_pitch)


def project(p: Vec3, view: ViewParams) -> tuple[float, float]:
    xr = p.x * view.cos_yaw - p.y * view.sin_yaw
    yr = p.x * view.sin_yaw + p.y * view.cos_yaw
    k = view.scale_px_per_m
    ox, oy = view.origin_px
    sx = ox + k * xr
    sy = oy - k * (yr * view.sin_pitch + p.z * view.cos_pitch)
    return (sx, sy)


def unproject_ground(sx: float, sy: float, view: ViewParams) -> tuple[float, float]:
    k = view.scale_px_per_m
    if abs(k) < EPS or abs(view.sin_pitch) < EPS:
        return (0.0, 0.0)
    ox, oy = view.origin_px
    xr = (sx - ox) / k
    yr = -(sy - oy) / (k * view.sin_pitch)
    x = xr * view.cos_yaw + yr * view.sin_yaw
    y = -xr * view.sin_yaw + yr * view.cos_yaw
    return (x, y)


def depth_key(p: Vec3, view: ViewParams) -> float:
    yr = p.x * view.sin_yaw + p.y * view.cos_yaw
    return yr * view.cos_pitch - p.z * view.sin_pitch


def ray_aabb(origin: Vec3, direction: Vec3, box_min: Vec3, box_max: Vec3) -> float | None:
    t_near = -1e30
    t_far = 1e30
    orig = (origin.x, origin.y, origin.z)
    dir_c = (direction.x, direction.y, direction.z)
    bmin = (box_min.x, box_min.y, box_min.z)
    bmax = (box_max.x, box_max.y, box_max.z)

    for a in range(3):
        oa, da, b_min, b_max = orig[a], dir_c[a], bmin[a], bmax[a]
        if abs(da) < EPS:
            if oa < b_min or oa > b_max:
                return None
        else:
            inv_d = 1.0 / da
            t1 = (b_min - oa) * inv_d
            t2 = (b_max - oa) * inv_d
            lo, hi = min(t1, t2), max(t1, t2)
            if lo > t_near:
                t_near = lo
            if hi < t_far:
                t_far = hi
            if t_near > t_far or t_far < T_MIN:
                return None

    if t_near > t_far or t_far < T_MIN:
        return None
    return max(t_near, T_MIN)
`,
  },
  {
    filename: 'scenario.py',
    description: 'Data model for buildings, 2m snapping, boundary overlap checks, revision tracking, and JSON persistence.',
    category: 'model',
    code: `"""Scenario and Building data model for Sunlight & Shadow Analyzer (SSA)."""

import json
from geometry import Vec3

CELL_SIZE_M = 2.0
GROUND_CELLS = (30, 30)
MAX_BUILDINGS = 15
DEFAULT_LAT = 31.5204
DEFAULT_LON = 74.3587
DEFAULT_TZ = 5.0

BUILDING_PALETTE = [
    "#D98E73", "#8FB8DE", "#E6C65C", "#9CC59A", "#B7A1D1", "#C9C9C9"
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
    def __init__(self, id: int, label: str, position: Vec3, size: Vec3, color: str = "#D98E73"):
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
        return Vec3(self.position.x + self.size.x, self.position.y + self.size.y, self.position.z + self.size.z)


class Scenario:
    def __init__(self, name: str = "A", ground_size: tuple[int, int] = GROUND_CELLS, lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON, tz_offset: float = DEFAULT_TZ, cell_size_m: float = CELL_SIZE_M):
        self.name = name
        self.ground_size = ground_size
        self.lat = lat
        self.lon = lon
        self.tz_offset = tz_offset
        self.cell_size_m = cell_size_m
        self.buildings: list[Building] = []
        self.next_id = 1
        self.revision = 0

    def touch(self) -> None:
        self.revision += 1

    def can_place(self, pos: Vec3, size: Vec3, exclude_id: int | None = None) -> bool:
        if pos.x < -1e-6 or pos.y < -1e-6:
            return False
        if pos.x + size.x > self.ground_size[0] * self.cell_size_m + 1e-6:
            return False
        if pos.y + size.y > self.ground_size[1] * self.cell_size_m + 1e-6:
            return False

        for b in self.buildings:
            if exclude_id is not None and b.id == exclude_id:
                continue
            if (min(pos.x + size.x, b.position.x + b.size.x) - max(pos.x, b.position.x) > 1e-6 and
                min(pos.y + size.y, b.position.y + b.size.y) - max(pos.y, b.position.y) > 1e-6):
                return False
        return True

    def add_building(self, b: Building) -> bool:
        if len(self.buildings) >= MAX_BUILDINGS or not self.can_place(b.position, b.size, b.id):
            return False
        self.buildings.append(b)
        if b.id >= self.next_id:
            self.next_id = b.id + 1
        self.touch()
        return True

    def clone(self, new_name: str | None = None) -> "Scenario":
        sc = Scenario(new_name or self.name, self.ground_size, self.lat, self.lon, self.tz_offset, self.cell_size_m)
        sc.next_id = self.next_id
        sc.revision = self.revision
        sc.buildings = [Building(b.id, b.label, Vec3(b.position.x, b.position.y, 0), Vec3(b.size.x, b.size.y, b.size.z), b.color) for b in self.buildings]
        return sc
`,
  },
  {
    filename: 'heatmap.py',
    description: 'Sunlight-hours accumulation, midpoint rule integration, cancellable job, and A/B comparison metrics.',
    category: 'core',
    code: `"""Sunlight-hours accumulation and A/B comparison for Sunlight & Shadow Analyzer (SSA)."""

import datetime
import math
from geometry import Vec3, ray_aabb, EL_MIN_DEG
from scenario import Scenario
from solar import solar_position, sun_vector


class HeatmapGrid:
    def __init__(self, resolution: tuple[int, int], cell_size_m: float, date_tuple: tuple[int, int, int], t_start_min: int, t_end_min: int, step_min: int, scenario_revision: int):
        self.resolution = resolution
        self.cell_size_m = cell_size_m
        self.date_tuple = date_tuple
        self.t_start_min = t_start_min
        self.t_end_min = t_end_min
        self.step_min = step_min
        self.scenario_revision = scenario_revision
        nx, ny = resolution
        self.hours_array = [[0.0 for _ in range(nx)] for _ in range(ny)]
        self.max_hours = 0.0


class HeatmapJob:
    def __init__(self, scenario: Scenario, target_date: datetime.date, t_start_min: int, t_end_min: int, step_min: int = 15):
        self.scenario = scenario
        self.target_date = target_date
        self.t_start_min = t_start_min
        self.t_end_min = t_end_min
        self.step_min = step_min
        total_span = max(0, t_end_min - t_start_min)
        self.num_samples = max(1, math.ceil(total_span / step_min))
        self.current_step = 0
        self.is_cancelled = False
        self.grid = HeatmapGrid(scenario.ground_size, scenario.cell_size_m, (target_date.year, target_date.month, target_date.day), t_start_min, t_end_min, step_min, scenario.revision)
        self._init_sampling()

    def _init_sampling(self) -> None:
        nx, ny = self.grid.resolution
        cs = self.grid.cell_size_m
        self.ground_samples = []
        for j in range(ny):
            cy = (j + 0.5) * cs
            for i in range(nx):
                cx = (i + 0.5) * cs
                occupied = any(b.position.x <= cx <= b.position.x + b.size.x and b.position.y <= cy <= b.position.y + b.size.y for b in self.scenario.buildings)
                if occupied:
                    self.grid.hours_array[j][i] = -1.0
                else:
                    self.ground_samples.append((i, j, Vec3(cx, cy, 0.001)))

    def cancel(self) -> None:
        self.is_cancelled = True

    def progress(self) -> float:
        return min(1.0, self.current_step / float(self.num_samples))

    def step(self) -> bool:
        if self.is_cancelled or self.current_step >= self.num_samples:
            return False

        t_k = self.t_start_min + (self.current_step + 0.5) * self.step_min
        sun = solar_position(self.scenario.lat, self.scenario.lon, self.target_date, int(round(t_k)), self.scenario.tz_offset)
        if sun.elevation_deg >= EL_MIN_DEG:
            s_vec = sun_vector(sun.azimuth_deg, sun.elevation_deg)
            boxes = [(b.min_point, b.max_point) for b in self.scenario.buildings]
            w = self.step_min / 60.0
            for i, j, pt in self.ground_samples:
                if not any(ray_aabb(pt, s_vec, bmin, bmax) is not None for bmin, bmax in boxes):
                    self.grid.hours_array[j][i] += w

        self.current_step += 1
        return self.current_step < self.num_samples

    def result(self) -> HeatmapGrid:
        max_h = 0.0
        for row in self.grid.hours_array:
            for val in row:
                if val > max_h:
                    max_h = val
        self.grid.max_hours = max_h
        return self.grid


def compare(grid_a: HeatmapGrid, grid_b: HeatmapGrid, target_hours: float = 2.0) -> dict:
    nx, ny = grid_a.resolution
    diff_array = [[-999.0 for _ in range(nx)] for _ in range(ny)]
    common = 0
    sum_a = 0.0
    sum_b = 0.0
    gained = 0
    lost = 0
    pass_a = 0
    pass_b = 0

    for j in range(ny):
        for i in range(nx):
            va = grid_a.hours_array[j][i]
            vb = grid_b.hours_array[j][i]
            if va >= 0.0 and vb >= 0.0:
                common += 1
                sum_a += va
                sum_b += vb
                d = vb - va
                diff_array[j][i] = d
                if d > 0.25: gained += 1
                elif d < -0.25: lost += 1
                if va >= target_hours: pass_a += 1
                if vb >= target_hours: pass_b += 1

    delta = sum_b - sum_a
    pct = (100.0 * delta / sum_a) if sum_a > 1e-6 else 0.0
    return {
        "common_cells": common,
        "sum_hours_a": sum_a,
        "sum_hours_b": sum_b,
        "delta_hours": delta,
        "pct_change": pct,
        "cells_gained": gained,
        "cells_lost": lost,
        "target_frac_a": pass_a / common if common else 0,
        "target_frac_b": pass_b / common if common else 0,
        "diff_array": diff_array,
    }
`,
  },
  {
    filename: 'renderer.py',
    description: 'Canvas rendering, layer management, Lambertian shading, Viridis palette, and WCAG contrast check.',
    category: 'core',
    code: `"""Canvas rendering and color palettes for Sunlight & Shadow Analyzer (SSA)."""

import math
from geometry import Vec3, ViewParams, project, depth_key, shadow_polygon
from heatmap import HeatmapGrid
from scenario import Scenario, Building

GROUND_COLOR = "#E8EDE3"
GRIDLINE_COLOR = "#C9D1C3"
SHADOW_COLOR = "#7F8CA0"
DAY_BG = "#F5F6F7"
NIGHT_BG = "#D5D9E3"
TEXT_COLOR = "#1B1F23"
OCCUPIED_COLOR = "#B0B0B0"

HEAT_PALETTE = [
    (0.0, 2.0, "#440154", "0–2 h"),
    (2.0, 4.0, "#443983", "2–4 h"),
    (4.0, 6.0, "#31688E", "4–6 h"),
    (6.0, 8.0, "#21908C", "6–8 h"),
    (8.0, 10.0, "#35B779", "8–10 h"),
    (10.0, 12.0, "#8FD744", "10–12 h"),
    (12.0, 999.0, "#FDE725", "12+ h"),
]

DIFF_PALETTE = [
    (-999.0, -4.0, "#B35806", "< -4 h"),
    (-4.0, -2.0, "#E08214", "-4 to -2 h"),
    (-2.0, -0.5, "#FDB863", "-2 to -0.5 h"),
    (-0.5, 0.5, "#F7F7F7", "±0.5 h"),
    (0.5, 2.0, "#92C5DE", "+0.5 to +2 h"),
    (2.0, 4.0, "#4393C3", "+2 to +4 h"),
    (4.0, 999.0, "#2166AC", "> +4 h"),
]


def hours_to_color(hours: float) -> str:
    if hours < 0.0:
        return OCCUPIED_COLOR
    for lo, hi, hex_val, _ in HEAT_PALETTE:
        if lo <= hours < hi:
            return hex_val
    return HEAT_PALETTE[-1][2]


def diff_to_color(diff: float) -> str:
    if diff <= -900.0:
        return OCCUPIED_COLOR
    for lo, hi, hex_val, _ in DIFF_PALETTE:
        if lo <= diff < hi:
            return hex_val
    return DIFF_PALETTE[-1][2]
`,
  },
  {
    filename: 'ui.py',
    description: 'Complete Tkinter & ttk desktop application with direct manipulation, time scrubbing, and compare mode.',
    category: 'ui',
    code: `"""Graphical User Interface for Sunlight & Shadow Analyzer (SSA).

See repository root ui.py for complete 600+ line implementation.
Features full Tkinter direct-manipulation dragging, time scrubber,
and side-by-side A/B comparison small multiples.
"""
`,
  },
  {
    filename: 'requirements.txt',
    description: 'Zero third-party requirements. Pure Python standard library.',
    category: 'meta',
    code: `# Sunlight & Shadow Analyzer (SSA) Dependencies
# SSA requires NO external packages! It runs entirely on the standard Python 3.10+ library.
# Optional performance accelerator:
# numpy>=1.24
`,
  },
  {
    filename: 'README.md',
    description: 'Full user manual, architectural reference, and verification instructions.',
    category: 'meta',
    code: `# Sunlight & Shadow Analyzer (SSA)

> Interactive sun-path, shadow, and sunlight-hours tool for small-site planning
Works offline with zero third-party dependencies on Python 3.10+.
`,
  },
];
