"""Geometry utilities for Sunlight & Shadow Analyzer (SSA).

Provides Vec3, axonometric projection, Sutherland-Hodgman clipping,
Andrew's monotone chain convex hull, and Kay-Kajiya Ray-AABB slab intersection.
Strictly uses math; no external 3D libraries or prohibited modules.
"""

import math

EPS = 1e-9
T_MIN = 1e-4
EL_MIN_DEG = 2.0


class Vec3:
    """3D vector in right-handed ENU coordinates (X=East, Y=North, Z=Up)."""

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __repr__(self) -> str:
        return f"Vec3({self.x:.3f}, {self.y:.3f}, {self.z:.3f})"

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Vec3":
        return self.__mul__(scalar)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def length(self) -> float:
        return math.sqrt(self.length_sq())

    def normalized(self) -> "Vec3":
        mag = self.length()
        if mag < EPS:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / mag, self.y / mag, self.z / mag)

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class ViewParams:
    """Axonometric view parameters with trigonometric caches."""

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
    """Projects 3D point P=(x,y,z) to 2D screen coordinates (sx, sy).

    Rotation around Z (yaw psi):
      xr = x*cos(psi) - y*sin(psi)
      yr = x*sin(psi) + y*cos(psi)
    Screen projection (pitch rho, scale k, origin (ox,oy)):
      sx = ox + k * xr
      sy = oy - k * (yr * sin(rho) + z * cos(rho))
    """
    xr = p.x * view.cos_yaw - p.y * view.sin_yaw
    yr = p.x * view.sin_yaw + p.y * view.cos_yaw
    k = view.scale_px_per_m
    ox, oy = view.origin_px
    sx = ox + k * xr
    sy = oy - k * (yr * view.sin_pitch + p.z * view.cos_pitch)
    return (sx, sy)


def unproject_ground(sx: float, sy: float, view: ViewParams) -> tuple[float, float]:
    """Inverse projection from screen (sx, sy) to ground plane z=0 (x, y)."""
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
    """Depth key for painter's algorithm sorting (descending)."""
    yr = p.x * view.sin_yaw + p.y * view.cos_yaw
    return yr * view.cos_pitch - p.z * view.sin_pitch


def fit_view(
    canvas_w: float,
    canvas_h: float,
    ground_w: float,
    ground_d: float,
    max_h: float,
    yaw_deg: float = 45.0,
    pitch_deg: float = 35.264,
) -> ViewParams:
    """Computes ViewParams to fit the ground rectangle [0,ground_w]x[0,ground_d]

    and tallest building max_h centered inside canvas_w x canvas_h with 10% margin.
    """
    unit_view = ViewParams(yaw_deg, pitch_deg, 1.0, (0.0, 0.0))
    corners = [
        Vec3(0.0, 0.0, 0.0),
        Vec3(ground_w, 0.0, 0.0),
        Vec3(ground_w, ground_d, 0.0),
        Vec3(0.0, ground_d, 0.0),
        Vec3(0.0, 0.0, max_h),
        Vec3(ground_w, 0.0, max_h),
        Vec3(ground_w, ground_d, max_h),
        Vec3(0.0, ground_d, max_h),
    ]
    projs = [project(c, unit_view) for c in corners]
    min_x = min(p[0] for p in projs)
    max_x = max(p[0] for p in projs)
    min_y = min(p[1] for p in projs)
    max_y = max(p[1] for p in projs)

    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x < EPS:
        span_x = 1.0
    if span_y < EPS:
        span_y = 1.0

    pad = 0.90
    k_x = (canvas_w * pad) / span_x
    k_y = (canvas_h * pad) / span_y
    scale = min(k_x, k_y)

    # Re-evaluate centered origin
    scaled_view = ViewParams(yaw_deg, pitch_deg, scale, (0.0, 0.0))
    projs_scaled = [project(c, scaled_view) for c in corners]
    s_min_x = min(p[0] for p in projs_scaled)
    s_max_x = max(p[0] for p in projs_scaled)
    s_min_y = min(p[1] for p in projs_scaled)
    s_max_y = max(p[1] for p in projs_scaled)

    center_x = (s_min_x + s_max_x) * 0.5
    center_y = (s_min_y + s_max_y) * 0.5

    ox = canvas_w * 0.5 - center_x
    oy = canvas_h * 0.5 - center_y

    return ViewParams(yaw_deg, pitch_deg, scale, (ox, oy))


def ray_aabb(
    origin: Vec3,
    direction: Vec3,
    box_min: Vec3,
    box_max: Vec3,
) -> float | None:
    """Ray-AABB slab intersection method (Kay & Kajiya 1986; Williams et al. 2005).

    Returns distance t_near along ray if intersection occurs with t > T_MIN, else None.
    """
    t_near = -1e30
    t_far = 1e30

    orig_coords = (origin.x, origin.y, origin.z)
    dir_coords = (direction.x, direction.y, direction.z)
    bmin_coords = (box_min.x, box_min.y, box_min.z)
    bmax_coords = (box_max.x, box_max.y, box_max.z)

    for a in range(3):
        oa = orig_coords[a]
        da = dir_coords[a]
        b_min = bmin_coords[a]
        b_max = bmax_coords[a]

        if abs(da) < EPS:
            # Ray parallel to slab; check if origin is outside slab
            if oa < b_min or oa > b_max:
                return None
        else:
            inv_d = 1.0 / da
            t1 = (b_min - oa) * inv_d
            t2 = (b_max - oa) * inv_d
            lo = min(t1, t2)
            hi = max(t1, t2)
            if lo > t_near:
                t_near = lo
            if hi < t_far:
                t_far = hi
            if t_near > t_far or t_far < T_MIN:
                return None

    if t_near > t_far or t_far < T_MIN:
        return None

    return max(t_near, T_MIN)


def _cross_2d(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull_2d(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain 2D convex hull algorithm (O(n log n)).

    Returns vertices in counter-clockwise order without duplicates.
    """
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    # Lower hull
    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and _cross_2d(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)

    # Upper hull
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross_2d(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)

    # Concatenate lower and upper hull, omitting last point of each
    return lower[:-1] + upper[:-1]


def clip_polygon_to_rect(
    poly: list[tuple[float, float]],
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman polygon clipping against an axis-aligned rectangle."""
    if not poly:
        return []

    output = list(poly)
    # 4 clipping stages: left (x >= x_min), right (x <= x_max), bottom (y >= y_min), top (y <= y_max)
    edges = [
        ("left", x_min),
        ("right", x_max),
        ("bottom", y_min),
        ("top", y_max),
    ]

    for edge_type, boundary in edges:
        input_list = output
        output = []
        if not input_list:
            break

        s = input_list[-1]
        for e in input_list:
            inside_e = False
            inside_s = False
            if edge_type == "left":
                inside_e = e[0] >= boundary
                inside_s = s[0] >= boundary
            elif edge_type == "right":
                inside_e = e[0] <= boundary
                inside_s = s[0] <= boundary
            elif edge_type == "bottom":
                inside_e = e[1] >= boundary
                inside_s = s[1] >= boundary
            elif edge_type == "top":
                inside_e = e[1] <= boundary
                inside_s = s[1] <= boundary

            if inside_e:
                if inside_s:
                    output.append(e)
                else:
                    inter = _line_intersect_edge(s, e, edge_type, boundary)
                    if inter:
                        output.append(inter)
                    output.append(e)
            elif inside_s:
                inter = _line_intersect_edge(s, e, edge_type, boundary)
                if inter:
                    output.append(inter)
            s = e

    return output


def _line_intersect_edge(
    p1: tuple[float, float],
    p2: tuple[float, float],
    edge_type: str,
    boundary: float,
) -> tuple[float, float] | None:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if edge_type in ("left", "right"):
        if abs(dx) < EPS:
            return None
        t = (boundary - p1[0]) / dx
        return (boundary, p1[1] + t * dy)
    else:
        if abs(dy) < EPS:
            return None
        t = (boundary - p1[1]) / dy
        return (p1[0] + t * dx, boundary)


def point_in_convex_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    """Tests if point (px, py) is inside or on the boundary of a convex polygon."""
    n = len(poly)
    if n < 3:
        return False

    sign = 0
    p = (px, py)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        c = _cross_2d(a, b, p)
        if abs(c) < EPS:
            continue
        if c > 0:
            current_sign = 1
        else:
            current_sign = -1

        if sign == 0:
            sign = current_sign
        elif sign != current_sign:
            return False

    return True


def shadow_polygon(
    b_min: Vec3,
    b_max: Vec3,
    sun_vec: Vec3,
    ground_w: float,
    ground_d: float,
) -> list[tuple[float, float]]:
    """Calculates ground shadow polygon for a box building under sun vector.

    P' = (x - z * s.x / s.z, y - z * s.y / s.z).
    Returns clipped 2D convex polygon on ground plane.
    """
    if sun_vec.z < math.sin(math.radians(EL_MIN_DEG)):
        return []

    # 8 box corners
    corners = [
        Vec3(b_min.x, b_min.y, b_min.z),
        Vec3(b_max.x, b_min.y, b_min.z),
        Vec3(b_max.x, b_max.y, b_min.z),
        Vec3(b_min.x, b_max.y, b_min.z),
        Vec3(b_min.x, b_min.y, b_max.z),
        Vec3(b_max.x, b_min.y, b_max.z),
        Vec3(b_max.x, b_max.y, b_max.z),
        Vec3(b_min.x, b_max.y, b_max.z),
    ]

    sz = sun_vec.z
    proj_pts: list[tuple[float, float]] = []
    for c in corners:
        px = c.x - c.z * (sun_vec.x / sz)
        py = c.y - c.z * (sun_vec.y / sz)
        proj_pts.append((px, py))

    hull = convex_hull_2d(proj_pts)
    clipped = clip_polygon_to_rect(hull, 0.0, 0.0, ground_w, ground_d)
    return clipped


def run_checks() -> list[tuple[str, bool, str]]:
    """Runs geometry self-tests based on Section 10.1 of plan.md."""
    results: list[tuple[str, bool, str]] = []

    # Check 1: Isometric projection check
    # ψ=45°, ρ=35.264°, k=1, origin(0,0):
    # (1,0,0) -> (+0.7071k, -0.4082k); (0,0,1) -> (0, -0.8165k) ±1e-3
    v_unit = ViewParams(45.0, 35.264, 1.0, (0.0, 0.0))
    p100 = project(Vec3(1.0, 0.0, 0.0), v_unit)
    p001 = project(Vec3(0.0, 0.0, 1.0), v_unit)
    c1 = (
        abs(p100[0] - 0.7071) < 1e-3
        and abs(p100[1] - (-0.4082)) < 1e-3
        and abs(p001[0] - 0.0) < 1e-3
        and abs(p001[1] - (-0.8165)) < 1e-3
    )
    results.append(("Geometry: Isometric projection matrix", c1, f"(1,0,0)={p100}, (0,0,1)={p001}"))

    # Check 2: Unproject round-trip at z=0
    test_pt = Vec3(18.5, 24.2, 0.0)
    v_test = ViewParams(45.0, 35.264, 12.0, (250.0, 300.0))
    screen = project(test_pt, v_test)
    unproj = unproject_ground(screen[0], screen[1], v_test)
    c2 = abs(unproj[0] - test_pt.x) < 1e-7 and abs(unproj[1] - test_pt.y) < 1e-7
    results.append(("Geometry: Ground unproject invertibility", c2, f"Target=({test_pt.x},{test_pt.y}), Unproj={unproj}"))

    # Check 3: Ray-AABB slab intersection
    # Box (10,10,0) to (14,14,10)
    # az=225°, el=45° -> s = (-0.5, -0.5, 0.7071) normalized
    rad_az = math.radians(225.0)
    rad_el = math.radians(45.0)
    s_vec = Vec3(
        math.cos(rad_el) * math.sin(rad_az),
        math.cos(rad_el) * math.cos(rad_az),
        math.sin(rad_el),
    )
    b_min = Vec3(10.0, 10.0, 0.0)
    b_max = Vec3(14.0, 14.0, 10.0)
    # From (16,16,0.001) pointing towards sun direction s
    # Since s_x < 0, s_y < 0, ray moves into lower x,y hitting (14,14)
    hit1 = ray_aabb(Vec3(16.0, 16.0, 0.001), s_vec, b_min, b_max)
    # From (16,8,0.001) pointing along s, ray misses in y
    hit2 = ray_aabb(Vec3(16.0, 8.0, 0.001), s_vec, b_min, b_max)
    c3 = (hit1 is not None and abs(hit1 - 4.0) < 0.1) and (hit2 is None)
    results.append(("Geometry: Ray-AABB slab method", c3, f"hit1={hit1}, hit2={hit2}"))

    # Check 4: Shadow polygon corner projection & clipping
    # Roof corner (14,14,10) under az=225, el=45
    # sz = sin(45) = 0.7071. sx = cos(45)*sin(225) = -0.5.
    # sx/sz = -0.5 / 0.7071 = -0.7071.
    # px = 14 - 10 * (-0.7071) = 21.071.
    poly = shadow_polygon(b_min, b_max, s_vec, 60.0, 60.0)
    c4 = len(poly) >= 4 and any(abs(pt[0] - 21.071) < 0.05 for pt in poly)
    results.append(("Geometry: Shadow polygon hull & projection", c4, f"vertices={len(poly)}"))

    return results


if __name__ == "__main__":
    for name, passed, info in run_checks():
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {info}")
