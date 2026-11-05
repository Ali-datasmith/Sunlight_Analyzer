"""Solar position calculation for Sunlight & Shadow Analyzer (SSA).

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
    """Converts spherical sun position (azimuth, elevation) to Cartesian unit vector in ENU coordinates.

    s = (cos(el)*sin(az), cos(el)*cos(az), sin(el)).
    """
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
    """Scans minutes 0..1439 at 1-minute resolution for sunrise and sunset.

    Returns (first_daylight_minute, last_daylight_minute).
    If polar night: (None, None).
    If midnight sun: (0, 1439).
    """
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
        # Check if actually all day above horizon
        return (0, 1439)

    return (first_min, last_min)


def run_checks() -> list[tuple[str, bool, str]]:
    """Runs solar self-tests based on Section 10.1 of plan.md for Lahore reference cases."""
    results: list[tuple[str, bool, str]] = []
    lat = 31.5204
    lon = 74.3587
    tz = 5.0

    # S1: 2024-03-21 12:00 -> Azimuth 175° ± 2°, Elevation 58.8° ± 1°
    d1 = datetime.date(2024, 3, 21)
    s1 = solar_position(lat, lon, d1, 720, tz)
    pass1 = abs(s1.azimuth_deg - 175.0) <= 2.0 and abs(s1.elevation_deg - 58.8) <= 1.0
    results.append(("Solar: S1 Equinox noon (Lahore 2024-03-21 12:00)", pass1, f"Az={s1.azimuth_deg:.2f}°, El={s1.elevation_deg:.2f}° (target 175±2, 58.8±1)"))

    # S2: 2024-06-21 12:00 -> Azimuth 173° ± 4°, Elevation 81.8° ± 1°
    d2 = datetime.date(2024, 6, 21)
    s2 = solar_position(lat, lon, d2, 720, tz)
    pass2 = abs(s2.azimuth_deg - 173.0) <= 4.0 and abs(s2.elevation_deg - 81.8) <= 1.0
    results.append(("Solar: S2 Summer solstice noon (Lahore 2024-06-21 12:00)", pass2, f"Az={s2.azimuth_deg:.2f}°, El={s2.elevation_deg:.2f}° (target 173±4, 81.8±1)"))

    # S3: 2024-12-21 12:00 -> Azimuth 180° ± 2°, Elevation 35.0° ± 1°
    d3 = datetime.date(2024, 12, 21)
    s3 = solar_position(lat, lon, d3, 720, tz)
    pass3 = abs(s3.azimuth_deg - 180.0) <= 2.0 and abs(s3.elevation_deg - 35.0) <= 1.0
    results.append(("Solar: S3 Winter solstice noon (Lahore 2024-12-21 12:00)", pass3, f"Az={s3.azimuth_deg:.2f}°, El={s3.elevation_deg:.2f}° (target 180±2, 35.0±1)"))

    # S4: 2024-03-21 02:00 -> El < 0°, is_daytime=False, shadows_active=False
    s4 = solar_position(lat, lon, d1, 120, tz)
    pass4 = s4.elevation_deg < 0.0 and (not s4.is_daytime) and (not s4.shadows_active)
    results.append(("Solar: S4 Night check (Lahore 2024-03-21 02:00)", pass4, f"El={s4.elevation_deg:.2f}°, Day={s4.is_daytime}"))

    # S5: 2024-03-21 10:00 -> Azimuth 129° ± 2°, Elevation 46.3° ± 1.5°
    s5 = solar_position(lat, lon, d1, 600, tz)
    pass5 = abs(s5.azimuth_deg - 129.0) <= 2.0 and abs(s5.elevation_deg - 46.3) <= 1.5
    results.append(("Solar: S5 Morning equinox (Lahore 2024-03-21 10:00)", pass5, f"Az={s5.azimuth_deg:.2f}°, El={s5.elevation_deg:.2f}° (target 129±2, 46.3±1.5)"))

    # Vector check: az=90, el=0 -> (1,0,0) East
    sv = sun_vector(90.0, 0.0)
    pass_v = abs(sv.x - 1.0) < 1e-7 and abs(sv.y) < 1e-7 and abs(sv.z) < 1e-7
    results.append(("Solar: Sun vector East check (Az=90, El=0)", pass_v, f"s={sv}"))

    return results


if __name__ == "__main__":
    for name, passed, info in run_checks():
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {info}")
