"""Graphical User Interface for Sunlight & Shadow Analyzer (SSA).

Built with Tkinter and ttk. Implements direct manipulation, time scrubbing,
A/B layout comparison, non-blocking heatmap simulation, and self-testing.
Strictly uses math, datetime, json, and tkinter.
"""

import datetime
import json
import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from geometry import Vec3, ViewParams, fit_view
from heatmap import HeatmapGrid, HeatmapJob, compare
from renderer import (
    SceneRenderer,
    draw_legend,
    TEXT_COLOR,
    DAY_BG,
    NIGHT_BG,
)
from scenario import (
    Scenario,
    Building,
    create_demo_scenario,
    CITY_PRESETS,
    BUILDING_PALETTE,
    CELL_SIZE_M,
    MAX_BUILDINGS,
)
from solar import solar_position, sunrise_sunset, sun_vector

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

ASSUMPTIONS_TEXT = """Sunlight & Shadow Analyzer (SSA) — Assumptions & Limits

1. Clear-Sky Direct Radiation:
   Models clear-sky direct sunlight only. Weather, overcast skies, cloud cover, and atmospheric aerosol variability are not simulated.

2. Point Sun & Hard Shadows:
   The sun is modelled as a directional point source. Penumbral blur, soft shadows, and solar disc diameter (~0.53°) are omitted.

3. Flat Ground & Orthogonal Geometry:
   The ground plane is strictly horizontal (Z=0). All buildings are axis-aligned rectangular boxes (no sloped roofs, curves, or arbitrary rotations).

4. Solar Elevation Cut-off:
   A strict 2.0° elevation threshold is enforced. When apparent solar elevation < 2.0°, sunlight is excluded to account for horizon obstructions and extreme refraction.

5. Timezone & Astronomical Solar Model:
   Uses user-supplied UTC offset. Automatic DST adjustments and geocoding databases are omitted to ensure offline determinism. Solar position follows NOAA Meeus algorithms with standard atmospheric refraction.

6. Midpoint Discretisation Error:
   Sunlight hours are integrated using the midpoint Riemann rule with step Δt. Temporal edge uncertainty is bounded by ±(Δt / 2) minutes per transition (±0.125 h at 15-min step).

7. Facade Shading Approximation:
   Building facade shading applies Lambertian diffuse cos(theta) based on orientation. Inter-building facade occlusion and multi-bounce diffuse reflections are not calculated.
"""


class AppState:
    """Encapsulates all runtime application state."""

    def __init__(self):
        self.date = datetime.date(2024, 3, 21)
        self.minutes = 600  # 10:00 AM
        self.scenarios: dict[str, Scenario | None] = {
            "A": create_demo_scenario("A"),
            "B": None,
        }
        self.active = "A"
        self.compare_on = False
        self.views: dict[str, ViewParams] = {
            "A": ViewParams(45.0, 35.264, 10.0, (300.0, 240.0)),
            "B": ViewParams(45.0, 35.264, 10.0, (300.0, 240.0)),
        }
        self.selected_id: int | None = None
        self.heat: dict[str, HeatmapGrid | None] = {"A": None, "B": None}
        self.show_heat = False
        self.diff_mode = "abs"  # 'abs' or 'diff'
        self.step_min = 15
        self.target_hours = 2.0
        self.sun = solar_position(
            self.scenarios["A"].lat,
            self.scenarios["A"].lon,
            self.date,
            self.minutes,
            self.scenarios["A"].tz_offset,
        )
        self.sunrise_min: int | None = None
        self.sunset_min: int | None = None
        self.drag: dict | None = None
        self.is_playing = False


class App:
    """Main application window and controller."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Sunlight & Shadow Analyzer (SSA)")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 680)

        self.state = AppState()
        self._dirty = False
        self._heat_job: HeatmapJob | None = None
        self._heat_target_pane: str = "A"
        self._status_clear_timer: str | None = None

        self._recompute_sun_and_daylight()
        self._build_menu()
        self._build_ui()
        self._bind_keys()

        self.root.after(50, self._initial_fit_and_render)

    def _initial_fit_and_render(self) -> None:
        self._fit_views()
        self.draw_static_all()
        self._redraw_dynamic()

    def _recompute_sun_and_daylight(self) -> None:
        sc = self.state.scenarios[self.state.active] or self.state.scenarios["A"]
        self.state.sun = solar_position(
            sc.lat,
            sc.lon,
            self.state.date,
            self.state.minutes,
            sc.tz_offset,
        )
        sr, ss = sunrise_sunset(sc.lat, sc.lon, self.state.date, sc.tz_offset)
        self.state.sunrise_min = sr
        self.state.sunset_min = ss

    # -------------------------------------------------------------------------
    # UI Building
    # -------------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Scenario", command=self.on_new)
        file_menu.add_command(label="Open Scenario…", command=self.on_open)
        file_menu.add_command(label="Save Scenario…", command=self.on_save)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Assumptions & Limits", command=self.on_show_assumptions)
        help_menu.add_command(label="Run Self-Tests", command=self.on_run_selftest)
        help_menu.add_command(label="Benchmark (100 frames)", command=self.on_run_benchmark)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_ui(self) -> None:
        # Root layout: left_panel (column 0), center_frame (column 1)
        self.root.columnconfigure(0, weight=0, minsize=320)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)  # Status bar

        self._build_left_panel()
        self._build_center_panel()
        self._build_status_bar()

    def _build_left_panel(self) -> None:
        # Scrollable container for left panel to guarantee fits on 680h displays
        container = ttk.Frame(self.root)
        container.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, width=320)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.left_panel = ttk.Frame(canvas)

        self.left_panel.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.left_panel, anchor="nw")
        canvas.configure(yview_scroll=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # §8.3 Sections
        self._build_location_section()
        self._build_date_section()
        self._build_building_add_section()
        self._build_selected_building_section()
        self._build_heatmap_section()
        self._build_scenarios_section()
        self._build_assumptions_button()

    def _build_location_section(self) -> None:
        f = ttk.LabelFrame(self.left_panel, text="Location & Timezone", padding=6)
        f.pack(fill="x", padx=4, pady=3)

        # Preset Combobox
        r0 = ttk.Frame(f)
        r0.pack(fill="x", pady=2)
        ttk.Label(r0, text="Preset:").pack(side="left")
        self.preset_box = ttk.Combobox(r0, values=list(CITY_PRESETS.keys()), state="readonly", width=16)
        self.preset_box.set("Lahore")
        self.preset_box.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self.preset_box.bind("<<ComboboxSelected>>", self.on_preset_selected)

        # Lat / Lon
        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="Lat:").grid(row=0, column=0, sticky="w")
        self.lat_entry = ttk.Entry(r1, width=7)
        self.lat_entry.insert(0, "31.5204")
        self.lat_entry.grid(row=0, column=1, padx=2)

        ttk.Label(r1, text="Lon:").grid(row=0, column=2, sticky="w", padx=(6, 0))
        self.lon_entry = ttk.Entry(r1, width=7)
        self.lon_entry.insert(0, "74.3587")
        self.lon_entry.grid(row=0, column=3, padx=2)

        ttk.Label(r1, text="TZ:").grid(row=0, column=4, sticky="w", padx=(6, 0))
        self.tz_entry = ttk.Entry(r1, width=5)
        self.tz_entry.insert(0, "5.0")
        self.tz_entry.grid(row=0, column=5, padx=2)

        for ent in (self.lat_entry, self.lon_entry, self.tz_entry):
            ent.bind("<Return>", lambda e: self.on_location_commit())
            ent.bind("<FocusOut>", lambda e: self.on_location_commit())

    def _build_date_section(self) -> None:
        f = ttk.LabelFrame(self.left_panel, text="Simulation Date", padding=6)
        f.pack(fill="x", padx=4, pady=3)

        row = ttk.Frame(f)
        row.pack(fill="x")

        # Month
        self.month_box = ttk.Combobox(row, values=MONTH_NAMES, state="readonly", width=5)
        self.month_box.set("Mar")
        self.month_box.pack(side="left", padx=2)
        self.month_box.bind("<<ComboboxSelected>>", lambda e: self.on_date_change())

        # Day
        self.day_spin = ttk.Spinbox(row, from_=1, to=31, width=4)
        self.day_spin.set(21)
        self.day_spin.pack(side="left", padx=2)
        self.day_spin.bind("<Return>", lambda e: self.on_date_change())
        self.day_spin.bind("<FocusOut>", lambda e: self.on_date_change())

        # Year
        self.year_spin = ttk.Spinbox(row, from_=1900, to=2100, width=6)
        self.year_spin.set(2024)
        self.year_spin.pack(side="left", padx=2)
        self.year_spin.bind("<Return>", lambda e: self.on_date_change())
        self.year_spin.bind("<FocusOut>", lambda e: self.on_date_change())

    def _build_building_add_section(self) -> None:
        f = ttk.LabelFrame(self.left_panel, text="Add Building (Snapped 2m)", padding=6)
        f.pack(fill="x", padx=4, pady=3)

        # Label & Color
        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=1)
        ttk.Label(r1, text="Label:").pack(side="left")
        self.add_label_entry = ttk.Entry(r1, width=9)
        self.add_label_entry.insert(0, "Block")
        self.add_label_entry.pack(side="left", padx=4)

        ttk.Label(r1, text="Color:").pack(side="left", padx=(4, 0))
        self.add_color_box = ttk.Combobox(r1, values=BUILDING_PALETTE, width=8)
        self.add_color_box.set(BUILDING_PALETTE[0])
        self.add_color_box.pack(side="right", fill="x", expand=True)

        # Dimensions: W (dx), D (dy), H (dz)
        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="W:").grid(row=0, column=0)
        self.add_w_spin = ttk.Spinbox(r2, from_=2, to=20, increment=2, width=4)
        self.add_w_spin.set(8)
        self.add_w_spin.grid(row=0, column=1, padx=2)

        ttk.Label(r2, text="D:").grid(row=0, column=2, padx=(4, 0))
        self.add_d_spin = ttk.Spinbox(r2, from_=2, to=20, increment=2, width=4)
        self.add_d_spin.set(8)
        self.add_d_spin.grid(row=0, column=3, padx=2)

        ttk.Label(r2, text="H:").grid(row=0, column=4, padx=(4, 0))
        self.add_h_spin = ttk.Spinbox(r2, from_=3, to=45, increment=1, width=4)
        self.add_h_spin.set(12)
        self.add_h_spin.grid(row=0, column=5, padx=2)

        btn = ttk.Button(f, text="+ Add Building", command=self.on_add_building)
        btn.pack(fill="x", pady=(4, 0))

    def _build_selected_building_section(self) -> None:
        self.sel_frame = ttk.LabelFrame(self.left_panel, text="Selected Building", padding=6)
        self.sel_frame.pack(fill="x", padx=4, pady=3)

        self.sel_name_label = ttk.Label(self.sel_frame, text="None selected (Click in 3D canvas)", foreground="#718096")
        self.sel_name_label.pack(fill="x", pady=2)

        r = ttk.Frame(self.sel_frame)
        r.pack(fill="x", pady=2)
        ttk.Label(r, text="Height:").pack(side="left")
        self.sel_height_spin = ttk.Spinbox(r, from_=3, to=45, increment=1, width=5, command=self.on_height_commit)
        self.sel_height_spin.set(12)
        self.sel_height_spin.pack(side="left", padx=4)
        self.sel_height_spin.bind("<Return>", lambda e: self.on_height_commit())
        self.sel_height_spin.bind("<FocusOut>", lambda e: self.on_height_commit())

        self.sel_del_btn = ttk.Button(r, text="Delete", command=self.on_delete_selected)
        self.sel_del_btn.pack(side="right")

        self._update_selected_ui()

    def _build_heatmap_section(self) -> None:
        f = ttk.LabelFrame(self.left_panel, text="Sunlight Heatmap", padding=6)
        f.pack(fill="x", padx=4, pady=3)

        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=1)
        ttk.Label(r1, text="Step:").pack(side="left")
        self.step_box = ttk.Combobox(r1, values=["5 min", "10 min", "15 min", "30 min"], state="readonly", width=7)
        self.step_box.set("15 min")
        self.step_box.pack(side="left", padx=4)
        self.step_box.bind("<<ComboboxSelected>>", self._on_step_change)

        ttk.Label(r1, text="Target:").pack(side="left", padx=(4, 0))
        self.target_spin = ttk.Spinbox(r1, from_=0.5, to=12.0, increment=0.5, width=4, command=self.on_target_change)
        self.target_spin.set(2.0)
        self.target_spin.pack(side="right")
        self.target_spin.bind("<Return>", lambda e: self.on_target_change())

        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=3)
        self.run_heat_btn = ttk.Button(r2, text="▶ Run Heatmap", command=self.on_run_heatmap)
        self.run_heat_btn.pack(side="left", fill="x", expand=True)

        self.show_heat_var = tk.BooleanVar(value=False)
        self.show_heat_check = ttk.Checkbutton(
            f, text="Show Heatmap Overlay", variable=self.show_heat_var, command=self.on_toggle_heat
        )
        self.show_heat_check.pack(anchor="w", pady=1)

        self.heat_progress = ttk.Progressbar(f, orient="horizontal", mode="determinate")
        self.heat_progress.pack(fill="x", pady=2)

        # Legend canvas
        self.legend_canvas = tk.Canvas(f, width=280, height=210, bg="#FFFFFF", highlightthickness=1, highlightbackground="#CBD5E0")
        self.legend_canvas.pack(fill="x", pady=3)
        draw_legend(self.legend_canvas, is_diff_mode=False, is_stale=False)

    def _build_scenarios_section(self) -> None:
        f = ttk.LabelFrame(self.left_panel, text="A/B Comparison (Tufte Small Multiples)", padding=6)
        f.pack(fill="x", padx=4, pady=3)

        self.compare_var = tk.BooleanVar(value=False)
        self.compare_check = ttk.Checkbutton(
            f, text="Enable A/B Comparison", variable=self.compare_var, command=self.on_toggle_compare
        )
        self.compare_check.pack(anchor="w", pady=1)

        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=2)
        self.copy_btn = ttk.Button(r1, text="Copy A → B", command=self.on_copy_a_to_b, state="disabled")
        self.copy_btn.pack(side="left", fill="x", expand=True)

        # Radio buttons: Absolute vs Difference (B - A)
        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=2)
        self.view_mode_var = tk.StringVar(value="abs")
        self.rb_abs = ttk.Radiobutton(
            r2, text="Absolute Hours", variable=self.view_mode_var, value="abs", command=self.on_view_mode_change, state="disabled"
        )
        self.rb_abs.pack(side="left")
        self.rb_diff = ttk.Radiobutton(
            r2, text="Difference (B − A)", variable=self.view_mode_var, value="diff", command=self.on_view_mode_change, state="disabled"
        )
        self.rb_diff.pack(side="left", padx=8)

        # Summary Metrics Box
        self.summary_text = tk.StringVar(value="Toggle compare and run heatmaps to view before/after metric summary.")
        self.summary_label = ttk.Label(
            f, textvariable=self.summary_text, justify="left", font=("TkDefaultFont", 8), wraplength=280
        )
        self.summary_label.pack(fill="x", pady=4)

    def _build_assumptions_button(self) -> None:
        btn = ttk.Button(self.left_panel, text="ℹ Assumptions & Model Limits", command=self.on_show_assumptions)
        btn.pack(fill="x", padx=4, pady=6)

    def _build_center_panel(self) -> None:
        self.center = ttk.Frame(self.root)
        self.center.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self.center.rowconfigure(0, weight=1)  # Canvases
        self.center.rowconfigure(1, weight=0)  # Time panel
        self.center.columnconfigure(0, weight=1)

        # Canvases container
        self.canvas_frame = ttk.Frame(self.center)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew")
        self.canvas_frame.rowconfigure(1, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.columnconfigure(1, weight=1)

        # Pane A
        self.pane_title_A = ttk.Label(self.canvas_frame, text="A: Before (Active)", font=("TkDefaultFont", 10, "bold"))
        self.pane_title_A.grid(row=0, column=0, sticky="w", padx=6, pady=2)

        self.canvas_A = tk.Canvas(self.canvas_frame, bg=DAY_BG, highlightthickness=2, highlightbackground="#3182CE")
        self.canvas_A.grid(row=1, column=0, sticky="nsew", padx=3, pady=3)
        self.renderer_A = SceneRenderer(self.canvas_A)

        # Pane B (initially hidden)
        self.pane_title_B = ttk.Label(self.canvas_frame, text="B: After", font=("TkDefaultFont", 10))
        self.canvas_B = tk.Canvas(self.canvas_frame, bg=DAY_BG, highlightthickness=2, highlightbackground="#CBD5E0")
        self.renderer_B = SceneRenderer(self.canvas_B)

        # Bind events
        self._bind_canvas_events(self.canvas_A, "A")
        self._bind_canvas_events(self.canvas_B, "B")

        self.canvas_A.bind("<Configure>", lambda e: self._on_canvas_resize())
        self.canvas_B.bind("<Configure>", lambda e: self._on_canvas_resize())

        # Time panel (§8.2)
        self._build_time_panel()

    def _bind_canvas_events(self, canvas: tk.Canvas, pane_name: str) -> None:
        canvas.bind("<ButtonPress-1>", lambda e: self.on_canvas_press(e, pane_name))
        canvas.bind("<B1-Motion>", lambda e: self.on_canvas_drag(e, pane_name))
        canvas.bind("<ButtonRelease-1>", lambda e: self.on_canvas_release(e, pane_name))
        canvas.bind("<Motion>", lambda e: self.on_canvas_motion(e, pane_name))
        canvas.bind("<KeyPress-Left>", lambda e: self.on_canvas_key(e, -1, 0))
        canvas.bind("<KeyPress-Right>", lambda e: self.on_canvas_key(e, 1, 0))
        canvas.bind("<KeyPress-Up>", lambda e: self.on_canvas_key(e, 0, 1))
        canvas.bind("<KeyPress-Down>", lambda e: self.on_canvas_key(e, 0, -1))
        canvas.bind("<Delete>", lambda e: self.on_delete_selected())
        canvas.bind("<BackSpace>", lambda e: self.on_delete_selected())

    def _build_time_panel(self) -> None:
        f = ttk.Frame(self.center, padding=6)
        f.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        f.columnconfigure(1, weight=1)

        # Row 1: Time display and quick buttons
        top_row = ttk.Frame(f)
        top_row.pack(fill="x", pady=2)

        self.time_label = ttk.Label(top_row, text="10:00 (UTC+5.0)", font=("TkDefaultFont", 14, "bold"), foreground="#1A202C")
        self.time_label.pack(side="left", padx=4)

        # Quick jumps & animation controls
        btn_frame = ttk.Frame(top_row)
        btn_frame.pack(side="right")

        ttk.Button(btn_frame, text="◀ -15m", width=6, command=lambda: self._step_time(-15)).pack(side="left", padx=2)
        self.play_btn = ttk.Button(btn_frame, text="▶ Play", width=6, command=self._toggle_play)
        self.play_btn.pack(side="left", padx=2)
        ttk.Button(btn_frame, text="+15m ▶", width=6, command=lambda: self._step_time(15)).pack(side="left", padx=2)

        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(btn_frame, text="Sunrise", width=7, command=self._jump_sunrise).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Noon", width=6, command=lambda: self._set_time(720)).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Sunset", width=7, command=self._jump_sunset).pack(side="left", padx=2)

        # Row 2: Daylight strip Canvas (§8.2 U7)
        self.daylight_canvas = tk.Canvas(f, height=14, bg="#CBD5E0", highlightthickness=0)
        self.daylight_canvas.pack(fill="x", pady=2)

        # Row 3: Main Time Slider (Scale 0..1439)
        self.time_scale = ttk.Scale(f, from_=0, to=1439, orient="horizontal", command=self.on_time_change)
        self.time_scale.set(600)
        self.time_scale.pack(fill="x", pady=1)

        # Row 4: Ticks (00, 06, 12, 18, 24)
        ticks = ttk.Frame(f)
        ticks.pack(fill="x")
        for lbl in ("00:00", "06:00", "12:00", "18:00", "24:00"):
            ttk.Label(ticks, text=lbl, font=("TkDefaultFont", 8), foreground="#718096").pack(side="left", expand=True)

    def _build_status_bar(self) -> None:
        sb = ttk.Frame(self.root, padding=(6, 2))
        sb.grid(row=1, column=0, columnspan=2, sticky="ew")
        sb.columnconfigure(0, weight=1)
        sb.columnconfigure(1, weight=1)
        sb.columnconfigure(2, weight=1)

        self.status_msg_label = ttk.Label(sb, text="Ready. Drag slider to scrub sunlight and shadows.", anchor="w")
        self.status_msg_label.grid(row=0, column=0, sticky="w")

        self.sun_readout_label = ttk.Label(sb, text="Az 129.1° | El 46.4° | Day", anchor="center", font=("TkDefaultFont", 9, "bold"))
        self.sun_readout_label.grid(row=0, column=1, sticky="ew")

        self.hover_readout_label = ttk.Label(sb, text="", anchor="e", foreground="#4A5568")
        self.hover_readout_label.grid(row=0, column=2, sticky="e")

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda e: self._toggle_play())

    # -------------------------------------------------------------------------
    # View & Render Lifecycle
    # -------------------------------------------------------------------------
    def _fit_views(self) -> None:
        """Fits both scenarios into their respective canvas dimensions."""
        for pane in ("A", "B"):
            sc = self.state.scenarios[pane]
            if sc is None:
                continue
            c = self.canvas_A if pane == "A" else self.canvas_B
            cw = max(200, c.winfo_width())
            ch = max(200, c.winfo_height())
            max_h = max([b.size.z for b in sc.buildings], default=18.0)
            self.state.views[pane] = fit_view(
                cw, ch, sc.ground_width_m, sc.ground_depth_m, max_h
            )

    def draw_static_all(self) -> None:
        """Redraws static layers for both visible panes."""
        # Pane A
        sc_a = self.state.scenarios["A"]
        if sc_a:
            diff_a = None
            self.renderer_A.draw_static(
                scenario=sc_a,
                view=self.state.views["A"],
                heat_grid=self.state.heat["A"],
                show_heat=self.state.show_heat,
                diff_grid=diff_a,
                selected_id=self.state.selected_id if self.state.active == "A" else None,
                sun_vec=sun_vector(self.state.sun.azimuth_deg, self.state.sun.elevation_deg),
                shadows_active=self.state.sun.shadows_active,
            )

        # Pane B
        if self.state.compare_on and self.state.scenarios["B"]:
            sc_b = self.state.scenarios["B"]
            diff_b = None
            if self.state.diff_mode == "diff" and self.state.heat["A"] and self.state.heat["B"]:
                cmp_res = compare(self.state.heat["A"], self.state.heat["B"], self.state.target_hours)
                diff_b = cmp_res["diff_array"]

            self.renderer_B.draw_static(
                scenario=sc_b,
                view=self.state.views["B"],
                heat_grid=self.state.heat["B"],
                show_heat=self.state.show_heat,
                diff_grid=diff_b,
                selected_id=self.state.selected_id if self.state.active == "B" else None,
                sun_vec=sun_vector(self.state.sun.azimuth_deg, self.state.sun.elevation_deg),
                shadows_active=self.state.sun.shadows_active,
            )

    def _request_redraw(self) -> None:
        """Coalesced dynamic redraw request."""
        if not self._dirty:
            self._dirty = True
            self.root.after(10, self._redraw_dynamic)

    def _redraw_dynamic(self) -> None:
        """Draws shadows, compass, night banner, and updates time widgets."""
        self._dirty = False

        # Pane A dynamic
        sc_a = self.state.scenarios["A"]
        if sc_a:
            cw_a = max(200, self.canvas_A.winfo_width())
            ch_a = max(200, self.canvas_A.winfo_height())
            self.renderer_A.draw_dynamic(
                scenario=sc_a,
                view=self.state.views["A"],
                sun_state=self.state.sun,
                show_heat=self.state.show_heat,
                canvas_w=cw_a,
                canvas_h=ch_a,
            )

        # Pane B dynamic
        if self.state.compare_on and self.state.scenarios["B"]:
            sc_b = self.state.scenarios["B"]
            cw_b = max(200, self.canvas_B.winfo_width())
            ch_b = max(200, self.canvas_B.winfo_height())
            self.renderer_B.draw_dynamic(
                scenario=sc_b,
                view=self.state.views["B"],
                sun_state=self.state.sun,
                show_heat=self.state.show_heat,
                canvas_w=cw_b,
                canvas_h=ch_b,
            )

        self._update_time_widgets()
        self._update_status()

    def _update_time_widgets(self) -> None:
        hh = self.state.minutes // 60
        mm = self.state.minutes % 60
        sc = self.state.scenarios[self.state.active] or self.state.scenarios["A"]
        tz_sign = "+" if sc.tz_offset >= 0 else ""
        self.time_label.config(text=f"{hh:02d}:{mm:02d} (UTC{tz_sign}{sc.tz_offset:.1f})")

        # Daylight strip Canvas
        dc = self.daylight_canvas
        dc.delete("all")
        dw = dc.winfo_width()
        if dw > 10:
            sr = self.state.sunrise_min
            ss = self.state.sunset_min
            if sr is not None and ss is not None and ss > sr:
                x_sr = (sr / 1440.0) * dw
                x_ss = (ss / 1440.0) * dw
                dc.create_rectangle(x_sr, 0, x_ss, 14, fill="#ECC94B", outline="")

            # Current tick
            cur_x = (self.state.minutes / 1440.0) * dw
            dc.create_line(cur_x, 0, cur_x, 14, fill="#E53E3E", width=2)

    def _update_status(self) -> None:
        sun = self.state.sun
        status_text = "Day" if sun.is_daytime else "Night"
        self.sun_readout_label.config(
            text=f"Az {sun.azimuth_deg:.1f}° | El {sun.elevation_deg:.1f}° | {status_text}"
        )

    def set_status_message(self, msg: str) -> None:
        self.status_msg_label.config(text=msg)
        if self._status_clear_timer:
            self.root.after_cancel(self._status_clear_timer)
        self._status_clear_timer = self.root.after(6000, lambda: self.status_msg_label.config(text=""))

    def _on_canvas_resize(self) -> None:
        self._fit_views()
        self.draw_static_all()
        self._redraw_dynamic()

    # -------------------------------------------------------------------------
    # Direct Manipulation (Dragging, Selection, Keyboard)
    # -------------------------------------------------------------------------
    def on_canvas_press(self, event: any, pane_name: str) -> None:
        c = self.canvas_A if pane_name == "A" else self.canvas_B
        c.focus_set()
        self._set_active_pane(pane_name)

        sc = self.state.scenarios[pane_name]
        view = self.state.views[pane_name]
        if sc is None:
            return

        hit = self.renderer_A.hit_test_building(sc, view, event.x, event.y)
        if hit:
            self.state.selected_id = hit.id
            self.state.drag = {
                "id": hit.id,
                "start_pos": Vec3(hit.position.x, hit.position.y, hit.position.z),
                "mouse_down": (event.x, event.y),
                "pane": pane_name,
            }
        else:
            self.state.selected_id = None
            self.state.drag = None

        self._update_selected_ui()
        self.draw_static_all()
        self._request_redraw()

    def on_canvas_drag(self, event: any, pane_name: str) -> None:
        if not self.state.drag or self.state.drag["pane"] != pane_name:
            return

        sc = self.state.scenarios[pane_name]
        view = self.state.views[pane_name]
        b_id = self.state.drag["id"]
        b = sc.get_building(b_id)
        if b is None:
            return

        # Inverse project current mouse to ground z=0
        gx, gy = self.renderer_A.canvas.__class__ and (
            (event.x - view.origin_px[0]) / view.scale_px_per_m,
            -(event.y - view.origin_px[1]) / (view.scale_px_per_m * view.sin_pitch),
        )
        # Unproject with rotation
        xr = gx
        yr = gy
        world_x = xr * view.cos_yaw + yr * view.sin_yaw
        world_y = -xr * view.sin_yaw + yr * view.cos_yaw

        # Snap to cell size
        snapped_x = round(world_x / sc.cell_size_m) * sc.cell_size_m
        snapped_y = round(world_y / sc.cell_size_m) * sc.cell_size_m
        target_pos = Vec3(snapped_x, snapped_y, 0.0)

        if sc.can_place(target_pos, b.size, exclude_id=b_id):
            b.position = target_pos
            sc.touch()
            self._mark_stale(pane_name)
            self.draw_static_all()
            self._request_redraw()
            self.set_status_message(f"Moved {b.label} to ({int(snapped_x)}m, {int(snapped_y)}m)")

    def on_canvas_release(self, event: any, pane_name: str) -> None:
        self.state.drag = None

    def on_canvas_motion(self, event: any, pane_name: str) -> None:
        sc = self.state.scenarios[pane_name]
        view = self.state.views[pane_name]
        if sc is None:
            return

        # Check building hit
        hit = self.renderer_A.hit_test_building(sc, view, event.x, event.y)
        if hit:
            self.hover_readout_label.config(text=f"Building '{hit.label}' ({int(hit.size.z)}m tall)")
            return

        # Check ground cell
        gx = (event.x - view.origin_px[0]) / view.scale_px_per_m
        gy = -(event.y - view.origin_px[1]) / (view.scale_px_per_m * view.sin_pitch)
        wx = gx * view.cos_yaw + gy * view.sin_yaw
        wy = -gx * view.sin_yaw + gy * view.cos_yaw

        if 0.0 <= wx < sc.ground_width_m and 0.0 <= wy < sc.ground_depth_m:
            ci = int(wx / sc.cell_size_m)
            cj = int(wy / sc.cell_size_m)
            heat = self.state.heat[pane_name]
            hours_str = ""
            if heat and 0 <= cj < len(heat.hours_array) and 0 <= ci < len(heat.hours_array[0]):
                val = heat.hours_array[cj][ci]
                if val >= 0.0:
                    hours_str = f" | {val:.2f} hrs"
                else:
                    hours_str = " | Occupied"
            self.hover_readout_label.config(text=f"X={wx:.1f}m, Y={wy:.1f}m (Cell [{ci},{cj}]{hours_str})")
        else:
            self.hover_readout_label.config(text="")

    def on_canvas_key(self, event: any, dx_cells: int, dy_cells: int) -> None:
        sc = self.state.scenarios[self.state.active]
        if sc is None or self.state.selected_id is None:
            return
        b = sc.get_building(self.state.selected_id)
        if b is None:
            return

        step = sc.cell_size_m
        new_pos = Vec3(b.position.x + dx_cells * step, b.position.y + dy_cells * step, 0.0)
        if sc.can_place(new_pos, b.size, exclude_id=b.id):
            b.position = new_pos
            sc.touch()
            self._mark_stale(self.state.active)
            self.draw_static_all()
            self._request_redraw()
            self.set_status_message(f"Nudged {b.label} to ({int(new_pos.x)}m, {int(new_pos.y)}m)")

    def on_delete_selected(self) -> None:
        sc = self.state.scenarios[self.state.active]
        if sc is None or self.state.selected_id is None:
            return
        b = sc.get_building(self.state.selected_id)
        name = b.label if b else "building"
        if sc.remove_building(self.state.selected_id):
            self.state.selected_id = None
            self._update_selected_ui()
            self._mark_stale(self.state.active)
            self.draw_static_all()
            self._request_redraw()
            self.set_status_message(f"Deleted {name}")

    def _set_active_pane(self, pane_name: str) -> None:
        self.state.active = pane_name
        if pane_name == "A":
            self.pane_title_A.config(text="A: Before (Active)", font=("TkDefaultFont", 10, "bold"))
            self.canvas_A.config(highlightbackground="#3182CE")
            self.pane_title_B.config(text="B: After", font=("TkDefaultFont", 10))
            self.canvas_B.config(highlightbackground="#CBD5E0")
        else:
            self.pane_title_A.config(text="A: Before", font=("TkDefaultFont", 10))
            self.canvas_A.config(highlightbackground="#CBD5E0")
            self.pane_title_B.config(text="B: After (Active)", font=("TkDefaultFont", 10, "bold"))
            self.canvas_B.config(highlightbackground="#3182CE")

    def _update_selected_ui(self) -> None:
        sc = self.state.scenarios[self.state.active]
        b = sc.get_building(self.state.selected_id) if sc and self.state.selected_id else None
        if b:
            self.sel_name_label.config(
                text=f"{b.label} (ID {b.id}) at ({int(b.position.x)}, {int(b.position.y)})",
                foreground="#1A202C",
            )
            self.sel_height_spin.config(state="normal")
            self.sel_height_spin.set(int(b.size.z))
            self.sel_del_btn.config(state="normal")
        else:
            self.sel_name_label.config(text="None selected (Click in 3D canvas)", foreground="#718096")
            self.sel_height_spin.config(state="disabled")
            self.sel_del_btn.config(state="disabled")

    # -------------------------------------------------------------------------
    # Form Commits & Actions
    # -------------------------------------------------------------------------
    def on_time_change(self, value: any) -> None:
        self.state.minutes = int(float(value))
        self._recompute_sun_and_daylight()
        self._request_redraw()

    def _step_time(self, delta_m: int) -> None:
        new_val = max(0, min(1439, self.state.minutes + delta_m))
        self.time_scale.set(new_val)
        self.on_time_change(new_val)

    def _set_time(self, minute: int) -> None:
        self.time_scale.set(minute)
        self.on_time_change(minute)

    def _jump_sunrise(self) -> None:
        if self.state.sunrise_min is not None:
            self._set_time(self.state.sunrise_min)
            self.set_status_message(f"Jumped to Sunrise ({self.state.sunrise_min // 60:02d}:{self.state.sunrise_min % 60:02d})")
        else:
            self.set_status_message("No sunrise today (Polar Night / Day)")

    def _jump_sunset(self) -> None:
        if self.state.sunset_min is not None:
            self._set_time(self.state.sunset_min)
            self.set_status_message(f"Jumped to Sunset ({self.state.sunset_min // 60:02d}:{self.state.sunset_min % 60:02d})")
        else:
            self.set_status_message("No sunset today (Polar Night / Day)")

    def _toggle_play(self) -> None:
        self.state.is_playing = not self.state.is_playing
        if self.state.is_playing:
            self.play_btn.config(text="⏸ Pause")
            self._animation_loop()
        else:
            self.play_btn.config(text="▶ Play")

    def _animation_loop(self) -> None:
        if not self.state.is_playing:
            return
        next_m = (self.state.minutes + 5) % 1440
        self.time_scale.set(next_m)
        self.on_time_change(next_m)
        self.root.after(40, self._animation_loop)

    def on_preset_selected(self, event: any = None) -> None:
        city = self.preset_box.get()
        if city in CITY_PRESETS:
            lat, lon, tz = CITY_PRESETS[city]
            self.lat_entry.delete(0, tk.END)
            self.lat_entry.insert(0, str(lat))
            self.lon_entry.delete(0, tk.END)
            self.lon_entry.insert(0, str(lon))
            self.tz_entry.delete(0, tk.END)
            self.tz_entry.insert(0, str(tz))
            self.on_location_commit()

    def on_location_commit(self) -> None:
        try:
            lat = float(self.lat_entry.get())
            lon = float(self.lon_entry.get())
            tz = float(self.tz_entry.get())

            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0) or not (-12.0 <= tz <= 14.0):
                raise ValueError("Out of range")

            for sc in (self.state.scenarios["A"], self.state.scenarios["B"]):
                if sc:
                    sc.lat = lat
                    sc.lon = lon
                    sc.tz_offset = tz
                    sc.touch()

            self._mark_stale("A")
            self._mark_stale("B")
            self._recompute_sun_and_daylight()
            self._request_redraw()
            self.set_status_message(f"Updated location: Lat {lat}°, Lon {lon}°, TZ {tz}")
        except Exception:
            self.set_status_message("Invalid coordinates. Lat [-90,90], Lon [-180,180], TZ [-12,14]")

    def on_date_change(self) -> None:
        try:
            m_name = self.month_box.get()
            m = MONTH_NAMES.index(m_name) + 1 if m_name in MONTH_NAMES else 3
            y = int(self.year_spin.get())
            d = int(self.day_spin.get())

            # Validate / clamp day
            days_in_m = 31
            if m in (4, 6, 9, 11):
                days_in_m = 30
            elif m == 2:
                days_in_m = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
            d = max(1, min(days_in_m, d))
            self.day_spin.set(d)

            self.state.date = datetime.date(y, m, d)
            self._mark_stale("A")
            self._mark_stale("B")
            self._recompute_sun_and_daylight()
            self._request_redraw()
            self.set_status_message(f"Date set to {self.state.date.isoformat()}")
        except Exception:
            pass

    def on_add_building(self) -> None:
        sc = self.state.scenarios[self.state.active]
        if sc is None:
            return
        if len(sc.buildings) >= MAX_BUILDINGS:
            self.set_status_message(f"Maximum of {MAX_BUILDINGS} buildings reached.")
            return

        try:
            label = self.add_label_entry.get().strip() or "Building"
            w = float(self.add_w_spin.get())
            d = float(self.add_d_spin.get())
            h = float(self.add_h_spin.get())
            color = self.add_color_box.get() or BUILDING_PALETTE[0]

            size = Vec3(w, d, h)
            pos = sc.find_free_spot(size)
            if pos is None:
                self.set_status_message("No free spot found on grid for this footprint size.")
                return

            new_b = Building(sc.next_id, label, pos, size, color)
            if sc.add_building(new_b):
                self.state.selected_id = new_b.id
                self._update_selected_ui()
                self._mark_stale(self.state.active)
                self.draw_static_all()
                self._request_redraw()
                self.set_status_message(f"Added '{label}' ({int(w)}x{int(d)}x{int(h)}m) at ({int(pos.x)},{int(pos.y)})")
        except Exception as e:
            self.set_status_message(f"Error adding building: {e}")

    def on_height_commit(self) -> None:
        sc = self.state.scenarios[self.state.active]
        if sc is None or self.state.selected_id is None:
            return
        try:
            val = float(self.sel_height_spin.get())
            if sc.set_building_height(self.state.selected_id, val):
                self._mark_stale(self.state.active)
                self.draw_static_all()
                self._request_redraw()
                self.set_status_message(f"Height updated to {int(val)}m")
        except Exception:
            pass

    def _on_step_change(self, event: any = None) -> None:
        txt = self.step_box.get()
        mins = int(txt.split()[0])
        self.state.step_min = mins
        self._mark_stale("A")
        self._mark_stale("B")

    def on_target_change(self) -> None:
        try:
            self.state.target_hours = float(self.target_spin.get())
            self._update_compare_summary()
        except Exception:
            pass

    def on_toggle_heat(self) -> None:
        self.state.show_heat = self.show_heat_var.get()
        self.draw_static_all()
        self._request_redraw()

    # -------------------------------------------------------------------------
    # Heatmap Engine (Incremental & Cancellable)
    # -------------------------------------------------------------------------
    def on_run_heatmap(self) -> None:
        if self._heat_job is not None:
            self._heat_job.cancel()
            self._heat_job = None
            self.run_heat_btn.config(text="▶ Run Heatmap")
            self.heat_progress["value"] = 0
            self.set_status_message("Heatmap calculation cancelled.")
            return

        sc = self.state.scenarios[self.state.active]
        if sc is None:
            return

        sr = self.state.sunrise_min or 360
        ss = self.state.sunset_min or 1080
        if ss <= sr:
            messagebox.showinfo("No Daylight", "No daylight hours on this date at this location.")
            return

        self._heat_target_pane = self.state.active
        self._heat_job = HeatmapJob(
            scenario=sc,
            target_date=self.state.date,
            t_start_min=sr,
            t_end_min=ss,
            step_min=self.state.step_min,
        )

        self.run_heat_btn.config(text="⏹ Cancel")
        self.heat_progress["value"] = 0
        self.set_status_message(f"Computing sunlight hours for Scenario {self._heat_target_pane}...")
        self.root.after(1, self._heat_tick)

    def _heat_tick(self) -> None:
        if self._heat_job is None:
            return

        # Execute 2 steps per tick to maintain 60 FPS while speeding up calculation
        for _ in range(2):
            more = self._heat_job.step()
            if not more:
                break

        prog = self._heat_job.progress()
        self.heat_progress["value"] = int(prog * 100)

        if not self._heat_job.is_cancelled and self._heat_job.current_step < self._heat_job.num_samples:
            self.root.after(1, self._heat_tick)
        else:
            # Finished
            grid = self._heat_job.result()
            self.state.heat[self._heat_target_pane] = grid
            self._heat_job = None
            self.run_heat_btn.config(text="▶ Run Heatmap")
            self.heat_progress["value"] = 100

            self.show_heat_var.set(True)
            self.state.show_heat = True

            draw_legend(self.legend_canvas, is_diff_mode=(self.state.diff_mode == "diff"), is_stale=False)
            self._update_compare_summary()
            self.draw_static_all()
            self._request_redraw()
            self.set_status_message(f"Heatmap ready for Scenario {self._heat_target_pane} (Max {grid.max_hours:.1f} hrs)")

    def _mark_stale(self, pane: str) -> None:
        heat = self.state.heat[pane]
        sc = self.state.scenarios[pane]
        if heat and sc and heat.scenario_revision != sc.revision:
            draw_legend(self.legend_canvas, is_diff_mode=(self.state.diff_mode == "diff"), is_stale=True)
            self._update_compare_summary()

    # -------------------------------------------------------------------------
    # A/B Comparison Logic (§7(f), §8.3 U16)
    # -------------------------------------------------------------------------
    def on_toggle_compare(self) -> None:
        self.state.compare_on = self.compare_var.get()
        if self.state.compare_on:
            if self.state.scenarios["B"] is None:
                self.state.scenarios["B"] = self.state.scenarios["A"].clone("B")
            self.pane_title_B.grid(row=0, column=1, sticky="w", padx=6, pady=2)
            self.canvas_B.grid(row=1, column=1, sticky="nsew", padx=3, pady=3)
            self.copy_btn.config(state="normal")
            self.rb_abs.config(state="normal")
            self.rb_diff.config(state="normal")
            self.set_status_message("Comparison mode ON: Side-by-side A (Before) and B (After).")
        else:
            self.pane_title_B.grid_remove()
            self.canvas_B.grid_remove()
            self.copy_btn.config(state="disabled")
            self.rb_abs.config(state="disabled")
            self.rb_diff.config(state="disabled")
            self._set_active_pane("A")
            self.set_status_message("Comparison mode OFF.")

        self._fit_views()
        self.draw_static_all()
        self._request_redraw()
        self._update_compare_summary()

    def on_copy_a_to_b(self) -> None:
        if self.state.scenarios["A"]:
            self.state.scenarios["B"] = self.state.scenarios["A"].clone("B")
            self.state.heat["B"] = None
            self._mark_stale("B")
            self.draw_static_all()
            self._request_redraw()
            self._update_compare_summary()
            self.set_status_message("Copied layout from A to B.")

    def on_view_mode_change(self) -> None:
        self.state.diff_mode = self.view_mode_var.get()
        draw_legend(self.legend_canvas, is_diff_mode=(self.state.diff_mode == "diff"), is_stale=False)
        self.draw_static_all()
        self._request_redraw()

    def _update_compare_summary(self) -> None:
        if not self.state.compare_on:
            self.summary_text.set("Toggle compare and run heatmaps to view before/after metric summary.")
            return

        ha = self.state.heat["A"]
        hb = self.state.heat["B"]

        if ha is None or hb is None:
            self.summary_text.set("Run heatmap on both A and B to calculate before/after difference.")
            return

        cmp_res = compare(ha, hb, self.state.target_hours)
        sign = "+" if cmp_res["delta_hours"] >= 0 else ""
        txt = (
            f"Common free cells: {cmp_res['common_cells']}\n"
            f"Sunlit cell-hours: A = {cmp_res['sum_hours_a']:.1f} h, B = {cmp_res['sum_hours_b']:.1f} h\n"
            f"Net Δ: {sign}{cmp_res['delta_hours']:.1f} cell-hrs ({sign}{cmp_res['pct_change']:.1f}%)\n"
            f"Cells gained (>0.25h): {cmp_res['cells_gained']} | Lost: {cmp_res['cells_lost']}\n"
            f"Fraction ≥ {self.state.target_hours}h: A = {cmp_res['target_frac_a']*100:.1f}%, B = {cmp_res['target_frac_b']*100:.1f}%"
        )
        self.summary_text.set(txt)

    # -------------------------------------------------------------------------
    # Dialogs & Testing (§10)
    # -------------------------------------------------------------------------
    def on_show_assumptions(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Assumptions & Mathematical Limits")
        win.geometry("620x520")
        win.minsize(500, 400)

        txt = tk.Text(win, wrap="word", padx=12, pady=12, font=("TkDefaultFont", 9))
        txt.insert("1.0", ASSUMPTIONS_TEXT)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

        btn = ttk.Button(win, text="Close", command=win.destroy)
        btn.pack(pady=8)

    def on_run_selftest(self) -> None:
        import solar
        import geometry
        import scenario
        import heatmap
        import renderer

        all_checks = []
        all_checks.extend(solar.run_checks())
        all_checks.extend(geometry.run_checks())
        all_checks.extend(scenario.run_checks())
        all_checks.extend(heatmap.run_checks())
        all_checks.extend(renderer.run_checks())

        passed = sum(1 for _, ok, _ in all_checks if ok)
        total = len(all_checks)

        win = tk.Toplevel(self.root)
        win.title(f"Self-Test Results ({passed}/{total} Passed)")
        win.geometry("680x480")

        f = ttk.Frame(win, padding=8)
        f.pack(fill="both", expand=True)

        txt = tk.Text(f, wrap="word", font=("TkFixedFont", 9))
        txt.pack(fill="both", expand=True)

        txt.insert("end", f"=== SUNLIGHT & SHADOW ANALYZER SELF-TESTS: {passed}/{total} PASSED ===\n\n")
        for name, ok, info in all_checks:
            tag = "PASS" if ok else "FAIL"
            txt.insert("end", f"[{tag}] {name}\n      {info}\n")

        txt.config(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)

    def on_run_benchmark(self) -> None:
        """Executes 100 dynamic redraw iterations sweeping minutes across the day."""
        start_time = datetime.datetime.now()
        durations_ms: list[float] = []

        sc = self.state.scenarios[self.state.active]
        view = self.state.views[self.state.active]
        canvas = self.canvas_A

        # Run 100 frames
        for step in range(100):
            m = int((step / 100.0) * 1440.0)
            sun = solar_position(sc.lat, sc.lon, self.state.date, m, sc.tz_offset)
            t0 = datetime.datetime.now()
            self.renderer_A.draw_dynamic(sc, view, sun, self.state.show_heat, canvas.winfo_width(), canvas.winfo_height())
            t1 = datetime.datetime.now()
            durations_ms.append((t1 - t0).total_seconds() * 1000.0)

        durations_ms.sort()
        mean_ms = sum(durations_ms) / len(durations_ms)
        p95_ms = durations_ms[int(len(durations_ms) * 0.95)]
        fps = 1000.0 / mean_ms if mean_ms > 0 else 999.0

        messagebox.showinfo(
            "Benchmark Results",
            f"100 Frame Dynamic Sweep Benchmark:\n\n"
            f"Mean Redraw Time: {mean_ms:.2f} ms ({fps:.1f} FPS)\n"
            f"p95 Redraw Time:  {p95_ms:.2f} ms\n"
            f"Target (SC3):      p95 ≤ 66.0 ms (≥15 FPS)\n"
            f"Result:            {'PASS' if p95_ms <= 66.0 else 'FAIL'}",
        )

    def _on_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Sunlight & Shadow Analyzer (SSA)\n"
            "Interactive sun-path, shadow, and sunlight-hours tool for small-site planning.\n"
            "Strictly Python Standard Library (Tkinter, math, datetime, json).\n"
            "Compatible with VS Code single-click run.",
        )

    def on_new(self) -> None:
        self.state = AppState()
        self._recompute_sun_and_daylight()
        self._fit_views()
        self.draw_static_all()
        self._redraw_dynamic()
        self._update_selected_ui()
        self._update_compare_summary()
        self.set_status_message("Initialized new scenario.")

    def on_open(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            sc_a = Scenario.from_dict(data["scenario_A"])
            self.state.scenarios["A"] = sc_a
            if "scenario_B" in data and data["scenario_B"] is not None:
                self.state.scenarios["B"] = Scenario.from_dict(data["scenario_B"])
            else:
                self.state.scenarios["B"] = None

            if "date" in data:
                self.state.date = datetime.date(*data["date"])
            if "minutes" in data:
                self.state.minutes = data["minutes"]

            self._recompute_sun_and_daylight()
            self._fit_views()
            self.draw_static_all()
            self._redraw_dynamic()
            self.set_status_message(f"Opened scenario from {path}")
        except Exception as e:
            messagebox.showerror("Open Failed", f"Failed to open scenario file: {e}")

    def on_save(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            data = {
                "scenario_A": self.state.scenarios["A"].to_dict(),
                "scenario_B": self.state.scenarios["B"].to_dict() if self.state.scenarios["B"] else None,
                "date": [self.state.date.year, self.state.date.month, self.state.date.day],
                "minutes": self.state.minutes,
            }
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
            self.set_status_message(f"Saved scenario to {path}")
        except Exception as e:
            messagebox.showerror("Save Failed", f"Failed to save scenario: {e}")
