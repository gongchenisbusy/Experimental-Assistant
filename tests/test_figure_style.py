from __future__ import annotations

import matplotlib as mpl

from ea.figures import (
    NATURE_LIKE_COLORS,
    NATURE_LIKE_STYLE_PROFILE,
    save_styled_figure,
    style_axis,
    styled_subplots,
)


def test_nature_like_style_helper_exports_traceable_png(tmp_path) -> None:
    figure_path = tmp_path / "styled-figure.png"
    fig, ax = styled_subplots(figsize=(3.0, 2.0))
    ax.plot([0, 1, 2], [0, 1, 0], color=NATURE_LIKE_COLORS["blue"], label="signal")
    style_axis(ax, title="Style check", xlabel="x", ylabel="y")

    save_styled_figure(
        fig,
        figure_path,
        footer=f"FigID: fig-test | Report: pending | Style: {NATURE_LIKE_STYLE_PROFILE}",
    )

    assert figure_path.exists()
    assert figure_path.stat().st_size > 0
    assert mpl.rcParams["svg.fonttype"] == "none"
    assert mpl.rcParams["pdf.fonttype"] == 42
    assert mpl.rcParams["axes.spines.top"] is False
    assert mpl.rcParams["axes.spines.right"] is False
