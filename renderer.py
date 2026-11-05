"""Canvas rendering and color palettes for Sunlight & Shadow Analyzer (SSA).

Manages layered canvas drawing (ground -> heat -> gridlines -> shadow -> building -> overlay),
face shading, Viridis & diverging heatmaps, WCAG contrast calculation, and compass rose.
Strictly uses math and tkinter.
"""

import math

from geometry import (
    Vec3,
    ViewParams,
    project,
    depth_key,
    convex_hull_2d,
    point_in_convex_polygon,
    shadow_polygon,
)
from heatmap import HeatmapGrid
from scenario import Scenario, Building

try:
    import tkinter as tk
except ImportError:
    tk = None  # Handled gracefully in headless or CLI test environments

GROUND_COLOR = "#E8EDE3"
GRIDLINE_COLOR = "#C9D1C3"
SHADOW_COLOR = "#7F8CA0"
DAY_BG = "#F5F6F7"
NIGHT_BG = "#D5D9E3"
TEXT_COLOR = "#1B1F23"
OCCUPIED_COLOR = "#B0B0B0"

# 7-bin Viridis palette (2-hour increments)
HEAT_PALETTE = [
    (0.0, 2.0, "#440154", "0–2 h"),
    (2.0, 4.0, "#443983", "2–4 h"),
    (4.0, 6.0, "#31688E", "4–6 h"),
    (6.0, 8.0, "#21908C", "6–8 h"),
    (8.0, 10.0, "#35B779", "8–10 h"),
    (10.0, 12.0, "#8FD744", "10–12 h"),
    (12.0, 999.0, "#FDE725", "12+ h"),
]

# 7-bin Diverging palette for A/B comparison difference (B - A)
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
    """Maps direct sunlight hours to 7-bin Viridis hex color."""
    if hours < 0.0:
        return OCCUPIED_COLOR
    for lo, hi, hex_val, _ in HEAT_PALETTE:
        if lo <= hours < hi:
            return hex_val
    return HEAT_PALETTE[-1][2]


def diff_to_color(diff: float) -> str:
    """Maps difference hours (B - A) to 7-bin diverging hex color."""
    if diff <= -900.0:
        return OCCUPIED_COLOR
    for lo, hi, hex_val, _ in DIFF_PALETTE:
        if lo <= diff < hi:
            return hex_val
    return DIFF_PALETTE[-1][2]


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    clean = hex_str.lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    r_cl = max(0, min(255, int(round(r))))
    g_cl = max(0, min(255, int(round(g))))
    b_cl = max(0, min(255, int(round(b))))
    return f"#{r_cl:02x}{g_cl:02x}{b_cl:02x}"


def shade_color(hex_color: str, brightness: float) -> str:
    """Multiplies hex RGB by brightness factor in [0.0, 1.0]."""
    r, g, b = hex_to_rgb(hex_color)
    factor = max(0.1, min(1.0, float(brightness)))
    return rgb_to_hex(int(r * factor), int(g * factor), int(b * factor))


def relative_luminance(hex_str: str) -> float:
    """Computes relative luminance according to WCAG 2.2."""
    r, g, b = hex_to_rgb(hex_str)
    channels = []
    for c in (r, g, b):
        sc = c / 255.0
        if sc <= 0.04045:
            channels.append(sc / 12.92)
        else:
            channels.append(((sc + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculates WCAG 2.2 contrast ratio between two hex colors."""
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class SceneRenderer:
    """Renders axonometric scene on a Tkinter Canvas with strict layer ordering.

    Layers: ground -> heat -> gridlines -> shadow -> building -> overlay.
    """

    def __init__(self, canvas: any):
        self.canvas = canvas

    def draw_static(
        self,
        scenario: Scenario,
        view: ViewParams,
        heat_grid: HeatmapGrid | None = None,
        show_heat: bool = False,
        diff_grid: list[list[float]] | None = None,
        selected_id: int | None = None,
        sun_vec: Vec3 | None = None,
        shadows_active: bool = True,
    ) -> None:
        """Renders static scene layers: ground plane, heatmap cells, grid lines, and sorted buildings."""
        c = self.canvas
        if c is None:
            return

        c.delete("ground")
        c.delete("heat")
        c.delete("gridlines")
        c.delete("building")

        gw = scenario.ground_width_m
        gd = scenario.ground_depth_m
        cs = scenario.cell_size_m
        nx, ny = scenario.ground_size

        # 1. Ground polygon
        g_corners = [
            project(Vec3(0.0, 0.0, 0.0), view),
            project(Vec3(gw, 0.0, 0.0), view),
            project(Vec3(gw, gd, 0.0), view),
            project(Vec3(0.0, gd, 0.0), view),
        ]
        g_coords: list[float] = []
        for p in g_corners:
            g_coords.extend([p[0], p[1]])
        c.create_polygon(g_coords, fill=GROUND_COLOR, outline=GROUND_COLOR, tags="ground")

        # 2. Heat cells (if visible)
        if show_heat and (heat_grid is not None or diff_grid is not None):
            for j in range(ny):
                y0 = j * cs
                y1 = y0 + cs
                for i in range(nx):
                    x0 = i * cs
                    x1 = x0 + cs
                    if diff_grid is not None:
                        val = diff_grid[j][i]
                        cell_color = diff_to_color(val)
                    elif heat_grid is not None:
                        val = heat_grid.hours_array[j][i]
                        cell_color = hours_to_color(val)
                    else:
                        continue

                    if cell_color != OCCUPIED_COLOR:
                        cell_quad = [
                            project(Vec3(x0, y0, 0.0), view),
                            project(Vec3(x1, y0, 0.0), view),
                            project(Vec3(x1, y1, 0.0), view),
                            project(Vec3(x0, y1, 0.0), view),
                        ]
                        quad_coords: list[float] = []
                        for pt in cell_quad:
                            quad_coords.extend([pt[0], pt[1]])
                        c.create_polygon(quad_coords, fill=cell_color, outline=cell_color, tags="heat")

        # 3. Gridlines
        # Along X lines
        for j in range(ny + 1):
            y_pos = j * cs
            p_start = project(Vec3(0.0, y_pos, 0.0), view)
            p_end = project(Vec3(gw, y_pos, 0.0), view)
            c.create_line(p_start[0], p_start[1], p_end[0], p_end[1], fill=GRIDLINE_COLOR, width=1, tags="gridlines")

        # Along Y lines
        for i in range(nx + 1):
            x_pos = i * cs
            p_start = project(Vec3(x_pos, 0.0, 0.0), view)
            p_end = project(Vec3(x_pos, gd, 0.0), view)
            c.create_line(p_start[0], p_start[1], p_end[0], p_end[1], fill=GRIDLINE_COLOR, width=1, tags="gridlines")

        # 4. Buildings (Back-to-front depth ordering via Painter's algorithm)
        # Depth key: yr * cos_pitch - z * sin_pitch descending
        sorted_buildings = sorted(
            scenario.buildings,
            key=lambda b: depth_key(
                Vec3(b.position.x + b.size.x * 0.5, b.position.y + b.size.y * 0.5, b.size.z * 0.5),
                view,
            ),
            reverse=True,
        )

        # Camera horizontal direction vector
        cam_h = Vec3(-view.sin_yaw, -view.cos_yaw, 0.0)

        for b in sorted_buildings:
            self._draw_building_box(c, b, view, cam_h, sun_vec, shadows_active, is_selected=(b.id == selected_id))

    def _draw_building_box(
        self,
        c: any,
        b: Building,
        view: ViewParams,
        cam_h: Vec3,
        sun_vec: Vec3 | None,
        shadows_active: bool,
        is_selected: bool,
    ) -> None:
        """Renders the visible faces of an axis-aligned box with Lambertian shading."""
        x0 = b.position.x
        x1 = x0 + b.size.x
        y0 = b.position.y
        y1 = y0 + b.size.y
        z0 = 0.0
        z1 = b.size.z

        # 6 box faces with outward unit normals:
        # Top (+Z): (0, 0, 1) -> always visible in axonometric view with pitch > 0
        # Bottom (-Z): (0, 0, -1) -> never visible
        # South (-Y): (0, -1, 0)
        # North (+Y): (0, 1, 0)
        # West (-X): (-1, 0, 0)
        # East (+X): (1, 0, 0)
        faces = [
            ("South", Vec3(0.0, -1.0, 0.0), [
                Vec3(x0, y0, z0), Vec3(x1, y0, z0), Vec3(x1, y0, z1), Vec3(x0, y0, z1)
            ]),
            ("East", Vec3(1.0, 0.0, 0.0), [
                Vec3(x1, y0, z0), Vec3(x1, y1, z0), Vec3(x1, y1, z1), Vec3(x1, y0, z1)
            ]),
            ("North", Vec3(0.0, 1.0, 0.0), [
                Vec3(x1, y1, z0), Vec3(x0, y1, z0), Vec3(x0, y1, z1), Vec3(x1, y1, z1)
            ]),
            ("West", Vec3(-1.0, 0.0, 0.0), [
                Vec3(x0, y1, z0), Vec3(x0, y0, z0), Vec3(x0, y0, z1), Vec3(x0, y1, z1)
            ]),
            ("Top", Vec3(0.0, 0.0, 1.0), [
                Vec3(x0, y0, z1), Vec3(x1, y0, z1), Vec3(x1, y1, z1), Vec3(x0, y1, z1)
            ]),
        ]

        # Draw vertical faces where dot(n, cam_h) > 0, then top face
        visible_faces = []
        for name, normal, quad in faces:
            if name == "Top":
                visible_faces.append((name, normal, quad))
            else:
                dot_cam = normal.x * cam_h.x + normal.y * cam_h.y
                if dot_cam > 1e-4:
                    visible_faces.append((name, normal, quad))

        for name, normal, quad in visible_faces:
            # Face brightness calculation: 0.35 ambient + 0.65 * max(0, n · s)
            if shadows_active and sun_vec is not None:
                dot_sun = max(0.0, normal.x * sun_vec.x + normal.y * sun_vec.y + normal.z * sun_vec.z)
                brightness = 0.35 + 0.65 * dot_sun
            else:
                brightness = 0.35

            fill_hex = shade_color(b.color, brightness)
            outline_hex = "#1B1F23" if not is_selected else "#0052CC"
            width_val = 2 if is_selected else 1

            coords: list[float] = []
            for p in quad:
                sp = project(p, view)
                coords.extend([sp[0], sp[1]])

            c.create_polygon(coords, fill=fill_hex, outline=outline_hex, width=width_val, tags="building")

        # Label on top roof
        center_top = Vec3(x0 + b.size.x * 0.5, y0 + b.size.y * 0.5, z1)
        sp_label = project(center_top, view)
        lbl_color = "#1B1F23" if relative_luminance(b.color) > 0.4 else "#FFFFFF"
        c.create_text(
            sp_label[0],
            sp_label[1],
            text=f"{b.label}\n{int(b.size.z)}m",
            fill=lbl_color,
            font=("TkDefaultFont", 8, "bold"),
            justify="center",
            tags="building",
        )

    def draw_dynamic(
        self,
        scenario: Scenario,
        view: ViewParams,
        sun_state: any,
        show_heat: bool = False,
        canvas_w: float = 600.0,
        canvas_h: float = 480.0,
    ) -> None:
        """Deletes only dynamic tags ('shadow', 'overlay') and redraws shadows, compass, and night banner."""
        c = self.canvas
        if c is None:
            return

        c.delete("shadow")
        c.delete("overlay")

        # Update canvas background color for day/night
        if sun_state.is_daytime:
            c.configure(bg=DAY_BG)
        else:
            c.configure(bg=NIGHT_BG)

        # 1. Shadows
        if sun_state.shadows_active:
            from solar import sun_vector
            s_vec = sun_vector(sun_state.azimuth_deg, sun_state.elevation_deg)
            gw = scenario.ground_width_m
            gd = scenario.ground_depth_m

            for b in scenario.buildings:
                poly = shadow_polygon(b.min_point, b.max_point, s_vec, gw, gd)
                if len(poly) >= 3:
                    coords: list[float] = []
                    for pt in poly:
                        sp = project(Vec3(pt[0], pt[1], 0.0), view)
                        coords.extend([sp[0], sp[1]])

                    if show_heat:
                        # Dashed dark outline when heatmap is visible
                        c.create_polygon(
                            coords,
                            fill="",
                            outline="#2D3748",
                            width=2,
                            dash=(4, 3),
                            tags="shadow",
                        )
                    else:
                        # Solid shadow fill
                        c.create_polygon(
                            coords,
                            fill=SHADOW_COLOR,
                            outline=SHADOW_COLOR,
                            tags="shadow",
                        )

            # Re-raise building layer so shadows always sit underneath buildings
            c.tag_raise("building", "shadow")
        elif not sun_state.is_daytime:
            # Night banner
            c.create_rectangle(
                canvas_w * 0.5 - 130,
                30,
                canvas_w * 0.5 + 130,
                65,
                fill="#2D3748",
                outline="#1A202C",
                width=1,
                tags="overlay",
            )
            c.create_text(
                canvas_w * 0.5,
                47,
                text="Night: Sun below horizon (no shadows)",
                fill="#FFFFFF",
                font=("TkDefaultFont", 10, "bold"),
                tags="overlay",
            )

        # 2. Compass rose (top-right)
        self.draw_compass(c, view, sun_state, canvas_w)

    def draw_compass(
        self,
        c: any,
        view: ViewParams,
        sun_state: any,
        canvas_w: float,
    ) -> None:
        """Renders 90px diameter compass rose with North arrow and sun direction indicator."""
        cx = canvas_w - 60.0
        cy = 60.0
        r = 38.0

        # Compass background ring
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#FFFFFF", outline="#CBD5E0", width=1.5, tags="overlay")

        # North direction in axonometric screen space:
        # Screen direction of (0, 1, 0) North vector:
        # xr = -sin(yaw), yr = cos(yaw)
        # sx_dir = -sin(yaw), sy_dir = -cos(yaw)*sin(pitch)
        nx_dir = -view.sin_yaw
        ny_dir = -view.cos_yaw * view.sin_pitch
        mag = math.sqrt(nx_dir * nx_dir + ny_dir * ny_dir)
        if mag > 1e-6:
            nx_dir /= mag
            ny_dir /= mag

        # North pointer (red arrow)
        tip_x = cx + nx_dir * (r - 6)
        tip_y = cy + ny_dir * (r - 6)
        c.create_line(cx, cy, tip_x, tip_y, fill="#E53E3E", width=2.5, arrow=tk.LAST if tk else "last", tags="overlay")
        c.create_text(tip_x + nx_dir * 8, tip_y + ny_dir * 8, text="N", fill="#E53E3E", font=("TkDefaultFont", 9, "bold"), tags="overlay")

        # Sun azimuth marker on ring
        # Azimuth is clockwise from North (0° = North, 90° = East, 180° = South, 270° = West)
        # In screen coordinates relative to North angle
        north_angle = math.atan2(ny_dir, nx_dir)
        sun_angle = north_angle + math.radians(sun_state.azimuth_deg)

        s_dot_x = cx + math.cos(sun_angle) * (r - 1)
        s_dot_y = cy + math.sin(sun_angle) * (r - 1)

        dot_fill = "#ECC94B" if sun_state.is_daytime else ""
        dot_outline = "#D69E2E" if sun_state.is_daytime else "#718096"
        c.create_oval(s_dot_x - 5, s_dot_y - 5, s_dot_x + 5, s_dot_y + 5, fill=dot_fill, outline=dot_outline, width=1.5, tags="overlay")

    def hit_test_building(
        self,
        scenario: Scenario,
        view: ViewParams,
        sx: float,
        sy: float,
    ) -> Building | None:
        """Finds the topmost building whose projected 3D box contains screen point (sx, sy)."""
        sorted_buildings = sorted(
            scenario.buildings,
            key=lambda b: depth_key(
                Vec3(b.position.x + b.size.x * 0.5, b.position.y + b.size.y * 0.5, b.size.z * 0.5),
                view,
            ),
            reverse=False,  # Test front buildings first
        )

        for b in sorted_buildings:
            corners = [
                Vec3(b.position.x, b.position.y, 0.0),
                Vec3(b.position.x + b.size.x, b.position.y, 0.0),
                Vec3(b.position.x + b.size.x, b.position.y + b.size.y, 0.0),
                Vec3(b.position.x, b.position.y + b.size.y, 0.0),
                Vec3(b.position.x, b.position.y, b.size.z),
                Vec3(b.position.x + b.size.x, b.position.y, b.size.z),
                Vec3(b.position.x + b.size.x, b.position.y + b.size.y, b.size.z),
                Vec3(b.position.x, b.position.y + b.size.y, b.size.z),
            ]
            projs = [project(c, view) for c in corners]
            hull = convex_hull_2d(projs)
            if point_in_convex_polygon(sx, sy, hull):
                return b

        return None


def draw_legend(
    canvas: any,
    is_diff_mode: bool = False,
    is_stale: bool = False,
) -> None:
    """Draws legend swatches with values and optional STALE indicator."""
    if canvas is None:
        return
    canvas.delete("all")

    palette = DIFF_PALETTE if is_diff_mode else HEAT_PALETTE
    title = "Change in sun hours (B − A)" if is_diff_mode else "Direct sunlight (hours, clear-sky)"

    # Title
    canvas.create_text(10, 14, text=title, anchor="w", fill=TEXT_COLOR, font=("TkDefaultFont", 9, "bold"))

    if is_stale:
        canvas.create_text(260, 14, text="STALE: re-run", anchor="e", fill="#E53E3E", font=("TkDefaultFont", 9, "bold"))

    # Swatches
    y_start = 32
    swatch_h = 16
    swatch_w = 28
    gap = 4

    for idx, (_, _, hex_val, label) in enumerate(palette):
        y = y_start + idx * (swatch_h + gap)
        canvas.create_rectangle(12, y, 12 + swatch_w, y + swatch_h, fill=hex_val, outline="#718096", width=1)
        canvas.create_text(48, y + swatch_h * 0.5, text=label, anchor="w", fill=TEXT_COLOR, font=("TkDefaultFont", 8))

    # Occupied swatch
    y_occ = y_start + len(palette) * (swatch_h + gap)
    canvas.create_rectangle(12, y_occ, 12 + swatch_w, y_occ + swatch_h, fill=OCCUPIED_COLOR, outline="#718096", width=1)
    canvas.create_text(48, y_occ + swatch_h * 0.5, text="Occupied / Footprint", anchor="w", fill=TEXT_COLOR, font=("TkDefaultFont", 8))


def run_checks() -> list[tuple[str, bool, str]]:
    """Runs renderer unit tests based on Section 10.1 of plan.md."""
    results: list[tuple[str, bool, str]] = []

    # 1. hours_to_color boundary values: 1.999 -> bin0, 2.0 -> bin1, 12.0 -> last
    c_199 = hours_to_color(1.999)
    c_200 = hours_to_color(2.0)
    c_120 = hours_to_color(12.0)
    pass1 = (
        c_199 == HEAT_PALETTE[0][2]
        and c_200 == HEAT_PALETTE[1][2]
        and c_120 == HEAT_PALETTE[-1][2]
    )
    results.append(("Renderer: hours_to_color bin boundaries", pass1, f"1.999h={c_199}, 2.0h={c_200}, 12h={c_120}"))

    # 2. WCAG contrast ratio check >= 4.5:1 for UI text vs backgrounds
    cr_text_day = contrast_ratio(TEXT_COLOR, DAY_BG)
    cr_text_night = contrast_ratio(TEXT_COLOR, NIGHT_BG)
    cr_text_white = contrast_ratio("#FFFFFF", "#2D3748")  # Night banner
    pass2 = cr_text_day >= 4.5 and cr_text_night >= 4.5 and cr_text_white >= 4.5
    results.append(("Renderer: WCAG 2.2 text contrast ratio >= 4.5:1", pass2, f"day={cr_text_day:.2f}:1, night={cr_text_night:.2f}:1, banner={cr_text_white:.2f}:1"))

    # 3. Legend swatch consistency: swatch color == hours_to_color representative
    pass3 = True
    for lo, hi, swatch_hex, _ in HEAT_PALETTE:
        rep = lo if hi >= 999.0 else (lo + hi) * 0.5
        if hours_to_color(rep) != swatch_hex:
            pass3 = False
            break
    results.append(("Renderer: Legend swatch color consistency", pass3, f"all {len(HEAT_PALETTE)} swatches match"))

    return results


if __name__ == "__main__":
    for name, passed, info in run_checks():
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {info}")
