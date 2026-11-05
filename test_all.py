"""Automated test runner aggregating all SSA module checks."""

import sys
import solar
import geometry
import scenario
import heatmap
import renderer


def run_all() -> bool:
    print("====================================================")
    print("RUNNING SUNLIGHT & SHADOW ANALYZER (SSA) TEST SUITE")
    print("====================================================")

    modules = [
        ("Solar Module (NOAA Astronomical Calculations)", solar.run_checks),
        ("Geometry Module (Projection, Ray-AABB, Clipping)", geometry.run_checks),
        ("Scenario Module (Placement, Revision, JSON)", scenario.run_checks),
        ("Heatmap Module (Accumulation, Midpoint, Comparison)", heatmap.run_checks),
        ("Renderer Module (Color scales, WCAG Contrast)", renderer.run_checks),
    ]

    total_passed = 0
    total_checks = 0
    all_passed = True

    for mod_name, check_fn in modules:
        print(f"\n--- {mod_name} ---")
        checks = check_fn()
        for name, ok, info in checks:
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
            print(f"         {info}")
            total_checks += 1
            if ok:
                total_passed += 1
            else:
                all_passed = False

    print("\n====================================================")
    print(f"TOTAL: {total_passed}/{total_checks} PASSED")
    print("====================================================")

    return all_passed


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
