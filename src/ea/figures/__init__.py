from ea.figures.service import (
    FigureLookupError,
    figure_footer,
    lookup_figure,
    register_figure,
    update_figure_report_ref,
)
from ea.figures.style import (
    DEFAULT_FIGURE_STYLE,
    NATURE_LIKE_COLORS,
    NATURE_LIKE_STYLE_PROFILE,
    FigureStyleProfile,
    save_styled_figure,
    style_axis,
    styled_subplots,
)

__all__ = [
    "DEFAULT_FIGURE_STYLE",
    "FigureLookupError",
    "FigureStyleProfile",
    "NATURE_LIKE_COLORS",
    "NATURE_LIKE_STYLE_PROFILE",
    "figure_footer",
    "lookup_figure",
    "register_figure",
    "save_styled_figure",
    "style_axis",
    "styled_subplots",
    "update_figure_report_ref",
]
