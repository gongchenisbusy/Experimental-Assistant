from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ea.electrochemistry import default_electrochemistry_processing_parameters
from ea.ftir import default_ftir_processing_parameters
from ea.pl import default_pl_processing_parameters
from ea.raman import default_processing_parameters
from ea.storage.files import write_yaml
from ea.thermal import default_thermal_processing_parameters
from ea.uv_vis import default_uv_vis_processing_parameters
from ea.xps import default_xps_processing_parameters
from ea.xrd import default_xrd_processing_parameters


SUPPORTED_TEMPLATE_METHODS = ("raman", "pl", "xrd", "ftir", "uv_vis", "xps", "electrochemistry", "thermal_analysis")


def _normalise_method(method: str) -> str:
    normalized = method.lower().strip().replace("-", "_")
    if normalized == "thermal":
        normalized = "thermal_analysis"
    if normalized not in SUPPORTED_TEMPLATE_METHODS:
        supported = ", ".join(SUPPORTED_TEMPLATE_METHODS)
        raise ValueError(f"Unsupported template method: {method}. Supported methods: {supported}")
    return normalized


def processing_parameters_template(method: str) -> dict[str, Any]:
    normalized = _normalise_method(method)
    if normalized == "raman":
        return deepcopy(default_processing_parameters())
    if normalized == "pl":
        return deepcopy(default_pl_processing_parameters())
    if normalized == "xrd":
        return deepcopy(default_xrd_processing_parameters())
    if normalized == "ftir":
        return deepcopy(default_ftir_processing_parameters())
    if normalized == "uv_vis":
        return deepcopy(default_uv_vis_processing_parameters())
    if normalized == "xps":
        return deepcopy(default_xps_processing_parameters())
    if normalized == "electrochemistry":
        return deepcopy(default_electrochemistry_processing_parameters())
    return deepcopy(default_thermal_processing_parameters())


def write_processing_parameters_template(path: Path, method: str) -> Path:
    return write_yaml(path, processing_parameters_template(method))


def _item_defaults(method: str, index: int, *, sample_ref: str, experiment_ref: str) -> dict[str, Any]:
    if method == "xrd":
        metadata = "raw/xrd/char-YYYYMMDD-001/metadata.yml"
        x_column = "two_theta"
        y_column = "intensity"
        x_unit = "2theta_deg"
    elif method == "pl":
        metadata = "raw/pl/char-YYYYMMDD-001/metadata.yml"
        x_column = "col_0"
        y_column = "col_1"
        x_unit = "eV"
    elif method == "ftir":
        metadata = "raw/ftir/char-YYYYMMDD-001/metadata.yml"
        x_column = "wavenumber"
        y_column = "absorbance"
        x_unit = "cm^-1"
    elif method == "uv_vis":
        metadata = "raw/uv_vis/char-YYYYMMDD-001/metadata.yml"
        x_column = "wavelength_nm"
        y_column = "absorbance"
        x_unit = "nm"
    elif method == "xps":
        metadata = "raw/xps/char-YYYYMMDD-001/metadata.yml"
        x_column = "binding_energy_eV"
        y_column = "intensity"
        x_unit = "eV"
    elif method == "electrochemistry":
        metadata = "raw/electrochemistry/char-YYYYMMDD-001/metadata.yml"
        x_column = "potential_V"
        y_column = "current_mA"
        x_unit = "V"
    elif method == "thermal_analysis":
        metadata = "raw/thermal_analysis/char-YYYYMMDD-001/metadata.yml"
        x_column = "temperature_C"
        y_column = "mass_percent"
        x_unit = "C"
    else:
        metadata = "raw/raman/char-YYYYMMDD-001/metadata.yml"
        x_column = "col_0"
        y_column = "col_1"
        x_unit = "cm^-1"
    item = {
        "item_id": f"{method}-{index:03d}",
        "method": method,
        "metadata": metadata,
        "sample_refs": [sample_ref],
        "experiment_refs": [experiment_ref],
        "x_column": x_column,
        "y_column": y_column,
        "x_unit": x_unit,
        "column_review_ref": "review-YYYYMMDD-001",
        "parameter_review_ref": "review-YYYYMMDD-002",
        "processing_parameters": {},
    }
    if method == "ftir":
        item["signal_mode"] = "absorbance"
    if method == "uv_vis":
        item["signal_mode"] = "absorbance"
    if method == "xps":
        item["energy_shift_eV"] = 0.0
        item["calibration_reference"] = "user-confirmed calibration reference or not applicable"
        item["calibration_review_ref"] = "review-YYYYMMDD-003"
    if method == "electrochemistry":
        item["current_unit"] = "mA"
        item["measurement_mode"] = "cv"
        item["context_summary"] = "user-confirmed electrode/electrolyte/reference-electrode context"
        item["electrode_area_cm2"] = None
        item["context_review_ref"] = "review-YYYYMMDD-003"
    if method == "thermal_analysis":
        item["temperature_column"] = item.pop("x_column")
        item["signal_column"] = item.pop("y_column")
        item["temperature_unit"] = item.pop("x_unit")
        item["signal_unit"] = "%"
        item["measurement_mode"] = "tga"
        item["context_summary"] = "user-confirmed temperature program, atmosphere, sample mass, and baseline context"
        item["context_review_ref"] = "review-YYYYMMDD-003"
    return item


def batch_manifest_template(
    *,
    project_id: str,
    methods: list[str] | tuple[str, ...] | None = None,
    sample_ref: str = "sample-001",
    experiment_ref: str = "exp-001",
    create_reports: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    selected_methods = tuple(_normalise_method(method) for method in (methods or SUPPORTED_TEMPLATE_METHODS))
    return {
        "schema_version": "0.2",
        "batch": {
            "project_id": project_id,
            "create_reports": create_reports,
            "continue_on_error": continue_on_error,
            "items": [
                _item_defaults(method, index, sample_ref=sample_ref, experiment_ref=experiment_ref)
                for index, method in enumerate(selected_methods, start=1)
            ],
        },
    }


def write_batch_manifest_template(
    path: Path,
    *,
    project_id: str,
    methods: list[str] | tuple[str, ...] | None = None,
    sample_ref: str = "sample-001",
    experiment_ref: str = "exp-001",
    create_reports: bool = True,
    continue_on_error: bool = True,
) -> Path:
    return write_yaml(
        path,
        batch_manifest_template(
            project_id=project_id,
            methods=methods,
            sample_ref=sample_ref,
            experiment_ref=experiment_ref,
            create_reports=create_reports,
            continue_on_error=continue_on_error,
        ),
    )
