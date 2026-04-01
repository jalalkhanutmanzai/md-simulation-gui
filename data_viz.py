"""Data parsing and visualization helpers for MD output files."""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


def parse_xvg(file_path: str) -> tuple[list[float], list[float], str]:
    """Parse a simple XVG file returning X, Y, and title."""
    x_vals: list[float] = []
    y_vals: list[float] = []
    title = Path(file_path).name

    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@"):
                if "title" in line.lower() and '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        title = parts[1]
                continue
            columns = line.split()
            if len(columns) < 2:
                continue
            try:
                x_vals.append(float(columns[0]))
                y_vals.append(float(columns[1]))
            except ValueError:
                continue

    return x_vals, y_vals, title


def render_xvg_plot(container, file_path: str):
    """Render an XVG plot on a Tk container and return the created canvas."""
    x_vals, y_vals, title = parse_xvg(file_path)
    figure = Figure(figsize=(6, 4), dpi=100)
    axis = figure.add_subplot(111)
    axis.plot(x_vals, y_vals, color="#4fa3ff", linewidth=1.8)
    axis.set_title(title)
    axis.set_xlabel("Time")
    axis.set_ylabel("Value")
    axis.grid(True, alpha=0.3)

    canvas = FigureCanvasTkAgg(figure, master=container)
    canvas.draw()
    widget = canvas.get_tk_widget()
    widget.pack(fill="both", expand=True)
    return canvas
