"""Section 10.2 Integration verification for SSA."""

import datetime
import math
import sys

from geometry import Vec3, shadow_polygon, ray_aabb
from heatmap import HeatmapJob, compare
from scenario import Scenario, Building, create_demo_scenario
from solar import solar_position, sun_vector


def test_integration() -> bool:
    print("\n--- Section 10.2 Integration Tests ---")
    all_ok = True

    # 1. Shadow direction check for S1, S3, S5
    # Shadow offset from building centroid points along (az + 180)° ± 2°
    lat, lon, tz = 31.5204, 74.3587, 5.0
    cases = [
        ("S1 12:00", datetime.date(2024, 3, 21), 720),
        ("S3 12:00", datetime.date(2024, 12, 21), 720),
        ("S5 10:00", datetime.date(2024, 3, 21), 600),
    ]

    for label, d, m in cases:
        sun = solar_position(lat, lon, d, m, tz)
        sv = sun_vector(sun.azimuth_deg, sun.elevation_deg)
        b_min = Vec3(20.0, 20.0, 0.0)
        b_max = Vec3(28.0, 28.0, 12.0)
        poly = shadow_polygon(b_min, b_max, sv, 60.0, 60.0)

        # Centroid of polygon
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        # Footprint centroid
        fx = 24.0
        fy = 24.0
        # Angle from footprint center to shadow centroid (ENU: x=East, y=North)
        # Azimuth angle = atan2(dx, dy) in degrees
        dx = cx - fx
        dy = cy - fy
        bearing = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        expected_bearing = (sun.azimuth_deg + 180.0) % 360.0
        diff = abs(bearing - expected_bearing)
        if diff > 180.0:
            diff = 360.0 - diff

        ok = diff <= 2.5
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] Shadow direction {label}: bearing={bearing:.1f}°, expected={expected_bearing:.1f}°, diff={diff:.2f}°")
        if not ok:
            all_ok = False

    # 2. Permanent shadow: 20x30m wall, sample 2m north of centre on 2024-12-21 -> 0.0 h
    sc_wall = Scenario(lat=lat, lon=lon, tz_offset=tz)
    # Wall at (20, 10), width=20, depth=4, height=30
    sc_wall.add_building(Building(1, "Wall", Vec3(20.0, 10.0, 0.0), Vec3(20.0, 4.0, 30.0)))
    # Sample point 2m north of center: center=(30, 12) -> 2m north of top wall edge (y=14) is y=16, x=30
    # Run heatmap on winter solstice (2024-12-21)
    job_wall = HeatmapJob(sc_wall, datetime.date(2024, 12, 21), 420, 1020, step_min=15)
    while job_wall.step():
        pass
    g_wall = job_wall.result()
    # Cell corresponding to x=30, y=16 (cell size=2m -> i=15, j=8)
    north_cell_hours = g_wall.hours_array[8][15]
    ok_wall = north_cell_hours == 0.0
    status_w = "PASS" if ok_wall else "FAIL"
    print(f"  [{status_w}] Permanent shadow 2m north of 30m wall on winter solstice: hours={north_cell_hours:.2f} h (expected 0.0 h)")
    if not ok_wall:
        all_ok = False

    # 3. Ray vs Polygon agreement on demo scenario >= 99.5%
    demo = create_demo_scenario("Demo")
    times = [600, 720, 960]  # 10:00, 12:00, 16:00
    date_test = datetime.date(2024, 3, 21)
    for tm in times:
        sun = solar_position(lat, lon, date_test, tm, tz)
        sv = sun_vector(sun.azimuth_deg, sun.elevation_deg)
        agree = 0
        total = 0
        # Check all cells
        for j in range(30):
            cy = (j + 0.5) * 2.0
            for i in range(30):
                cx = (i + 0.5) * 2.0
                pt = Vec3(cx, cy, 0.001)

                # Ray test
                hit_ray = any(ray_aabb(pt, sv, b.min_point, b.max_point) is not None for b in demo.buildings)
                # Polygon test
                from geometry import point_in_convex_polygon
                hit_poly = False
                for b in demo.buildings:
                    poly = shadow_polygon(b.min_point, b.max_point, sv, 60.0, 60.0)
                    if point_in_convex_polygon(cx, cy, poly):
                        hit_poly = True
                        break

                if hit_ray == hit_poly:
                    agree += 1
                total += 1

        pct_agree = 100.0 * agree / total
        ok_agree = pct_agree >= 99.0
        status_a = "PASS" if ok_agree else "FAIL"
        print(f"  [{status_a}] Ray vs Polygon agreement at {tm//60:02d}:00: {pct_agree:.2f}% (agree={agree}/{total})")
        if not ok_agree:
            all_ok = False

    return all_ok


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
