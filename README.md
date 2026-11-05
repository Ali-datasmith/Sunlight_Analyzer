# Sunlight & Shadow Analyzer (SSA)

> **Interactive sun-path, shadow, and sunlight-hours tool for small-site planning**  
> Developed for urban planners, architecture students, and site designers. Works offline with **zero third-party dependencies** on Python 3.10+.

---

## 🚀 Quick Start in VS Code

1. Open the project folder in **Visual Studio Code**.
2. Open `main.py`.
3. Click the **Run Python File** button (▶) in the top-right corner of the editor, or press `F5`.
4. Alternatively, open your terminal and run:
   ```bash
   python main.py
   ```

*Note: Python 3.10 or newer is recommended. Standard library packages `tkinter`, `math`, `datetime`, and `json` are included with standard Python installations.*

---

## 🏛 File Architecture

This application consists of nine modular, strictly-decoupled files following clean dependency lines:

| File | Purpose |
|---|---|
| `main.py` | Minimal entry point. Creates Tk root, initializes `ui.App`, and calls `mainloop()`. |
| `solar.py` | NOAA General Solar Position algorithm, atmospheric refraction correction, sun vector, and sunrise/sunset scanner. |
| `geometry.py` | `Vec3`, axonometric projection matrix, Kay-Kajiya Ray-AABB slab intersection, Andrew's monotone chain convex hull, and Sutherland-Hodgman polygon clipping. |
| `scenario.py` | `Building` and `Scenario` models, 2m grid snapping, collision/overlap rejection, revision counter, and JSON save/load. |
| `heatmap.py` | Sunlight accumulation engine, non-blocking cancellable `HeatmapJob`, midpoint rule integration, and BRE BR 209 comparison metrics. |
| `renderer.py` | `SceneRenderer` with layered canvas tags, Lambertian diffuse face shading, Viridis & diverging color palettes, WCAG contrast verification, and compass rose. |
| `ui.py` | Complete Tkinter / ttk desktop interface, direct manipulation drag-and-drop, time scrubbing slider, daylight strip, and comparison view. |
| `requirements.txt` | Dependency declaration (pure Python standard library; optional numpy). |
| `README.md` | Complete documentation, user guide, and testing protocol. |

---

## ✨ Key Features

1. **Interactive Sun & Shadow Scrubbing:**
   - Scrub the time slider (00:00 to 24:00) to watch ground shadows sweep across the 60m × 60m site in real time.
   - Quick jump buttons for **Sunrise**, **Noon**, **Sunset**, **±15 minutes**, or automated **Play/Pause**.
   - Dynamic night mode automatically displays a night banner when the sun is below the horizon.

2. **Direct Manipulation:**
   - Click and drag any building across the ground plane; positions automatically snap to a 2m grid.
   - Overlaps and boundary violations are rejected automatically.
   - Adjust building height on the fly (3m to 45m).
   - Keyboard navigation: use arrow keys to nudge the selected building cell by cell, or press Delete/Backspace to remove it.

3. **Sunlight-Hours Heatmap:**
   - Computes direct sunlight hours for all unoccluded ground cells and building roofs.
   - Non-blocking and cancellable with an interactive progress bar.
   - Perceptually uniform 7-bin **Viridis** color scale with hover readout for exact hours per cell.
   - **STALE** indicator automatically signals when site geometry or date changes.

4. **A/B Comparison (Tufte Small Multiples):**
   - Compare "Before" (Scenario A) and "After" (Scenario B) side by side.
   - Switch between **Absolute Hours** and **Difference (B − A)** diverging heatmap (brown/orange for loss, blue for gain).
   - Quantified metrics: total sunlit cell-hours, net change percentage, cells gained/lost, and fraction meeting target hours (e.g., 2.0 h BRE BR 209 standard).

5. **Built-in Quality & Verification:**
   - **Help → Run Self-Tests**: Runs 20+ automated unit tests across solar mechanics, geometry, ray-box clipping, and color contrast.
   - **Help → Benchmark**: Measures 100-frame redraw performance to verify responsiveness (target: p95 ≤ 66 ms / ≥ 15 FPS).
   - **Help → Assumptions & Limits**: Full transparent disclosure of astronomical and geometric assumptions.
