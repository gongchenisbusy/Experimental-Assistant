from __future__ import annotations

from pathlib import Path

from ea.projects import initialize_project


def test_project_lifecycle_supports_windows_style_deep_paths(tmp_path: Path) -> None:
    deep = tmp_path
    while len(str(deep)) <= 280:
        deep /= "ea-long-path-regression-segment"

    result = initialize_project(
        deep,
        project_name="Windows long path regression",
        project_slug="windows-long-path-regression",
        research_direction="native filesystem portability",
        material_system="MoS2",
        experiment_type="Raman",
    )

    assert len(str(deep)) > 260
    assert result["project"].is_file()
    assert result["config"].is_file()
