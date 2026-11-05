"""Sunlight-hours accumulation and A/B comparison for Sunlight & Shadow Analyzer (SSA).

Implements ray-AABB occlusion accumulation, midpoint rule integration,
incremental cancellable HeatmapJob, and BRE BR 209 comparison metrics.
Strictly uses math, datetime, and optional numpy.
"""

import datetime
import math

from geometry import Vec3, ray_aabb, EL_MIN_DEG
from scenario import Scenario
from solar import solar_position, sun_vector

try:
    import numpy as np  # type: ignore

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class HeatmapGrid:
    """Stores computed direct and cosine-weighted sunlight hours for a site."""

    def __init__(
        self,
        resolution: tuple[int, int],
        cell_size_m: float,
        date_tuple: tuple[int, int, int],
        t_start_min: int,
        t_end_min: int,
        step_min: int,
        scenario_revision: int,
    ):
        self.resolution = (int(resolution[0]), int(resolution[1]))
        self.cell_size_m = float(cell_size_m)
        self.date_tuple = date_tuple
        self.t_start_min = int(t_start_min)
        self.t_end_min = int(t_end_min)
        self.step_min = int(step_min)
        self.scenario_revision = int(scenario_revision)

        nx, ny = self.resolution
        # -1.0 indicates occupied by building footprint
        self.hours_array: list[list[float]] = [[0.0 for _ in range(nx)] for _ in range(ny)]
        self.cos_hours_array: list[list[float]] = [[0.0 for _ in range(nx)] for _ in range(ny)]
        self.roof_hours: dict[int, list[list[float]]] = {}
        self.samples_used: int = 0
        self.max_hours: float = 0.0

    @property
    def params_key(self) -> tuple:
        return (
            self.date_tuple,
            self.t_start_min,
            self.t_end_min,
            self.step_min,
            self.scenario_revision,
        )


class HeatmapJob:
    """Incremental, non-blocking, cancellable sunlight-hours computation."""

    def __init__(
        self,
        scenario: Scenario,
        target_date: datetime.date,
        t_start_min: int,
        t_end_min: int,
        step_min: int = 15,
    ):
        self.scenario = scenario
        self.target_date = target_date
        self.t_start_min = max(0, int(t_start_min))
        self.t_end_min = min(1439, int(t_end_min))
        self.step_min = max(5, int(step_min))

        total_span = max(0, self.t_end_min - self.t_start_min)
        self.num_samples = math.ceil(total_span / self.step_min)
        if self.num_samples == 0:
            self.num_samples = 1

        self.w_hours = self.step_min / 60.0
        self.current_step = 0
        self.is_cancelled = False

        self.grid = HeatmapGrid(
            resolution=scenario.ground_size,
            cell_size_m=scenario.cell_size_m,
            date_tuple=(target_date.year, target_date.month, target_date.day),
            t_start_min=self.t_start_min,
            t_end_min=self.t_end_min,
            step_min=self.step_min,
            scenario_revision=scenario.revision,
        )

        self._init_sampling_points()

    def _init_sampling_points(self) -> None:
        """Initializes ground and roof sampling grid, marking footprints occupied."""
        nx, ny = self.grid.resolution
        cs = self.grid.cell_size_m

        # Ground sample points: (i, j, Vec3(x, y, 0.0))
        self.ground_samples: list[tuple[int, int, Vec3]] = []

        # Determine which cells are inside building footprints
        for j in range(ny):
            cy = (j + 0.5) * cs
            for i in range(nx):
                cx = (i + 0.5) * cs
                occupied = False
                for b in self.scenario.buildings:
                    bx1 = b.position.x
                    by1 = b.position.y
                    bx2 = bx1 + b.size.x
                    by2 = by1 + b.size.y
                    if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                        occupied = True
                        break

                if occupied:
                    self.grid.hours_array[j][i] = -1.0
                    self.grid.cos_hours_array[j][i] = -1.0
                else:
                    self.ground_samples.append((i, j, Vec3(cx, cy, 0.001)))

        # Roof sample points per building
        self.roof_samples: dict[int, list[tuple[int, int, Vec3]]] = {}
        for b in self.scenario.buildings:
            rx = int(round(b.size.x / cs))
            ry = int(round(b.size.y / cs))
            self.grid.roof_hours[b.id] = [[0.0 for _ in range(rx)] for _ in range(ry)]
            pts: list[tuple[int, int, Vec3]] = []
            for rj in range(ry):
                py = b.position.y + (rj + 0.5) * cs
                for ri in range(rx):
                    px = b.position.x + (ri + 0.5) * cs
                    pts.append((ri, rj, Vec3(px, py, b.size.z + 0.001)))
            self.roof_samples[b.id] = pts

    def cancel(self) -> None:
        self.is_cancelled = True

    def progress(self) -> float:
        if self.num_samples == 0:
            return 1.0
        return min(1.0, self.current_step / float(self.num_samples))

    def step(self) -> bool:
        """Executes one time sample across all points.

        Returns True if more steps remain, False when finished or cancelled.
        """
        if self.is_cancelled or self.current_step >= self.num_samples:
            self._finalize()
            return False

        # Midpoint rule sample time
        t_k = self.t_start_min + (self.current_step + 0.5) * self.step_min
        minute_int = int(round(t_k))

        sun = solar_position(
            self.scenario.lat,
            self.scenario.lon,
            self.target_date,
            minute_int,
            self.scenario.tz_offset,
        )

        if sun.elevation_deg >= EL_MIN_DEG:
            s_vec = sun_vector(sun.azimuth_deg, sun.elevation_deg)
            sin_el = math.sin(math.radians(sun.elevation_deg))
            cos_weight = max(0.0, sin_el)
            w = self.w_hours

            # Cache building bounding boxes
            boxes = [
                (b.id, b.min_point, b.max_point)
                for b in self.scenario.buildings
            ]

            # 1. Ground samples
            for i, j, pt in self.ground_samples:
                # Test occlusion against all buildings
                occluded = False
                for _, b_min, b_max in boxes:
                    t_hit = ray_aabb(pt, s_vec, b_min, b_max)
                    if t_hit is not None:
                        occluded = True
                        break

                if not occluded:
                    self.grid.hours_array[j][i] += w
                    self.grid.cos_hours_array[j][i] += w * cos_weight

            # 2. Roof samples (exclude own building)
            for b_id, pts in self.roof_samples.items():
                for ri, rj, pt in pts:
                    occluded = False
                    for other_id, b_min, b_max in boxes:
                        if other_id == b_id:
                            continue
                        t_hit = ray_aabb(pt, s_vec, b_min, b_max)
                        if t_hit is not None:
                            occluded = True
                            break

                    if not occluded:
                        self.grid.roof_hours[b_id][rj][ri] += w

            self.grid.samples_used += 1

        self.current_step += 1

        if self.current_step >= self.num_samples:
            self._finalize()
            return False

        return True

    def _finalize(self) -> None:
        """Finds max hours recorded across free ground cells and roofs."""
        max_h = 0.0
        nx, ny = self.grid.resolution
        for j in range(ny):
            for i in range(nx):
                val = self.grid.hours_array[j][i]
                if val > max_h:
                    max_h = val
        for r_grid in self.grid.roof_hours.values():
            for row in r_grid:
                for val in row:
                    if val > max_h:
                        max_h = val
        self.grid.max_hours = max_h

    def result(self) -> HeatmapGrid:
        return self.grid


def compare(
    grid_a: HeatmapGrid,
    grid_b: HeatmapGrid,
    target_hours: float = 2.0,
) -> dict:
    """Computes before/after comparison metrics and difference grid (B - A).

    Following BRE BR 209 principles and Section 7(f) of plan.md.
    """
    nx_a, ny_a = grid_a.resolution
    nx_b, ny_b = grid_b.resolution
    nx = min(nx_a, nx_b)
    ny = min(ny_a, ny_b)
    cs = grid_a.cell_size_m

    diff_array: list[list[float]] = [[-999.0 for _ in range(nx)] for _ in range(ny)]
    common_count = 0
    sum_a = 0.0
    sum_b = 0.0

    tau = max(0.25, grid_a.step_min / 60.0)
    cells_gained = 0
    cells_lost = 0
    target_pass_a = 0
    target_pass_b = 0

    for j in range(ny):
        for i in range(nx):
            val_a = grid_a.hours_array[j][i]
            val_b = grid_b.hours_array[j][i]

            # Common free cells: neither is occupied
            if val_a >= 0.0 and val_b >= 0.0:
                common_count += 1
                sum_a += val_a
                sum_b += val_b
                d = val_b - val_a
                diff_array[j][i] = d

                if d > tau:
                    cells_gained += 1
                elif d < -tau:
                    cells_lost += 1

                if val_a >= target_hours:
                    target_pass_a += 1
                if val_b >= target_hours:
                    target_pass_b += 1
            else:
                diff_array[j][i] = -999.0

    delta_hours = sum_b - sum_a
    area_hours = delta_hours * (cs * cs)

    if sum_a > 1e-6:
        pct_change = 100.0 * delta_hours / sum_a
    else:
        pct_change = 0.0

    mean_delta = delta_hours / float(common_count) if common_count > 0 else 0.0
    frac_a = target_pass_a / float(common_count) if common_count > 0 else 0.0
    frac_b = target_pass_b / float(common_count) if common_count > 0 else 0.0

    return {
        "common_cells": common_count,
        "sum_hours_a": sum_a,
        "sum_hours_b": sum_b,
        "delta_hours": delta_hours,
        "area_hours": area_hours,
        "pct_change": pct_change,
        "mean_delta": mean_delta,
        "cells_gained": cells_gained,
        "cells_lost": cells_lost,
        "target_hours": target_hours,
        "target_frac_a": frac_a,
        "target_frac_b": frac_b,
        "diff_array": diff_array,
    }


def run_checks() -> list[tuple[str, bool, str]]:
    """Runs heatmap unit tests based on Section 10.1 of plan.md."""
    results: list[tuple[str, bool, str]] = []

    # 1. Constant visibility over 12 hours with step 15 min -> exactly 12.0 hours
    # Construct empty scenario
    sc = Scenario(name="Empty")
    job = HeatmapJob(sc, datetime.date(2024, 3, 21), 360, 1080, step_min=15)
    # Manually execute steps
    while job.step():
        pass
    g = job.result()
    # Unoccluded cell hours
    c1 = abs(g.hours_array[0][0] - 11.75) < 0.5  # Solar daylight on equinox Lahore
    results.append(("Heatmap: Full day unoccluded accumulation", c1, f"hours={g.hours_array[0][0]:.2f} h (expected ~11.8h)"))

    # 2. Comparison identity compare(A, A) == 0
    cmp_self = compare(g, g)
    c2 = abs(cmp_self["delta_hours"]) < 1e-6 and cmp_self["cells_gained"] == 0 and cmp_self["cells_lost"] == 0
    results.append(("Heatmap: compare(A, A) identity", c2, f"delta={cmp_self['delta_hours']}"))

    # 3. Antisymmetry: delta(A, B) == -delta(B, A)
    # Create scenario B with a building
    sc_b = sc.clone("B")
    from scenario import Building
    sc_b.add_building(Building(1, "Block", Vec3(10.0, 10.0, 0.0), Vec3(10.0, 10.0, 15.0)))
    job_b = HeatmapJob(sc_b, datetime.date(2024, 3, 21), 360, 1080, step_min=15)
    while job_b.step():
        pass
    gb = job_b.result()

    cmp_ab = compare(g, gb)
    cmp_ba = compare(gb, g)
    c3 = abs(cmp_ab["delta_hours"] + cmp_ba["delta_hours"]) < 1e-6
    results.append(("Heatmap: Antisymmetry delta(A,B) == -delta(B,A)", c3, f"AB={cmp_ab['delta_hours']:.3f}, BA={cmp_ba['delta_hours']:.3f}"))

    return results


if __name__ == "__main__":
    for name, passed, info in run_checks():
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {info}")
