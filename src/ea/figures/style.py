from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure


NATURE_LIKE_STYLE_PROFILE = "nature_like_clean"

NATURE_LIKE_COLORS = {
    "blue": "#0072B2",
    "orange": "#D55E00",
    "green": "#009E73",
    "yellow": "#F0E442",
    "pink": "#CC79A7",
    "black": "#000000",
    "gray": "#6E6E6E",
    "light_gray": "#D9D9D9",
}


@dataclass(frozen=True)
class FigureStyleProfile:
    name: str = NATURE_LIKE_STYLE_PROFILE
    font_size: float = 7.0
    title_size: float = 8.0
    label_size: float = 7.0
    tick_size: float = 6.5
    legend_size: float = 6.5
    footer_size: float = 5.5
    line_width: float = 1.2
    axis_line_width: float = 0.8
    raster_dpi: int = 300
    grid_alpha: float = 0.18
    footer_color: str = "#888888"

    def rcparams(self) -> dict[str, Any]:
        return {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": self.font_size,
            "axes.titlesize": self.title_size,
            "axes.labelsize": self.label_size,
            "xtick.labelsize": self.tick_size,
            "ytick.labelsize": self.tick_size,
            "legend.fontsize": self.legend_size,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": self.axis_line_width,
            "lines.linewidth": self.line_width,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.edgecolor": "white",
        }


DEFAULT_FIGURE_STYLE = FigureStyleProfile()


def apply_figure_style(profile: FigureStyleProfile = DEFAULT_FIGURE_STYLE) -> None:
    mpl.rcParams.update(profile.rcparams())


def styled_subplots(
    *,
    figsize: tuple[float, float] = (6.0, 4.0),
    profile: FigureStyleProfile = DEFAULT_FIGURE_STYLE,
) -> tuple[Figure, Axes]:
    apply_figure_style(profile)
    return plt.subplots(figsize=figsize)


def style_axis(
    ax: Axes,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    legend: bool = True,
    grid: bool = True,
    profile: FigureStyleProfile = DEFAULT_FIGURE_STYLE,
) -> None:
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if legend:
        ax.legend(frameon=False)
    if grid:
        ax.grid(True, alpha=profile.grid_alpha, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def add_canvas_footer(
    fig: Figure,
    footer: str | None,
    *,
    profile: FigureStyleProfile = DEFAULT_FIGURE_STYLE,
) -> None:
    if not footer:
        return
    fig.text(
        0.99,
        0.01,
        footer,
        ha="right",
        va="bottom",
        fontsize=profile.footer_size,
        color=profile.footer_color,
    )


def save_styled_figure(
    fig: Figure,
    output: Path,
    *,
    footer: str | None = None,
    profile: FigureStyleProfile = DEFAULT_FIGURE_STYLE,
    close: bool = True,
) -> None:
    add_canvas_footer(fig, footer, profile=profile)
    if footer:
        fig.tight_layout(rect=(0, 0.045, 1, 1))
    else:
        fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=profile.raster_dpi, bbox_inches="tight")
    if close:
        plt.close(fig)
