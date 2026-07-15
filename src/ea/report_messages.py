from __future__ import annotations

from typing import Any


MESSAGE_CONTRACT_VERSION = "1.0"


FIGURE_CAPTION_CATALOG = {
    "zh": {
        "raman_analysis_report": "Raman 光谱：已处理强度与候选峰。",
        "pl_analysis_report": "PL 光谱：已处理强度与候选发光峰。",
        "xrd_analysis_report": "XRD 图谱：候选峰与可追溯处理参数。",
        "ftir_analysis_report": "FTIR 光谱：已处理信号、候选谱带与谱带族筛查提示。",
        "uv_vis_analysis_report": "UV-Vis 光谱：已处理信号、候选光学特征与可追溯处理参数。",
        "xps_analysis_report": "XPS 光谱：已处理强度、候选筛查峰与经复核的处理记录。",
        "electrochemistry_analysis_report": "电化学曲线：已处理信号、候选特征、经复核背景与可追溯处理参数。",
        "thermal_analysis_report": "热分析曲线：已处理信号、候选事件、经复核背景与可追溯处理参数。",
        "cross-paper reviewed property comparison": "跨论文已复核数据对比图。",
    },
    "en": {},
}


SOURCE_DATA_PURPOSE_CATALOG = {
    "zh": {
        "primary_plotting_dataset": "用于绘制该图的已处理数据。",
        "peak_table": "图中峰位或拟合标注的数据表。",
        "reviewed_dataset_manifest": "已复核记录及其证据关系。",
        "legacy_unspecified": "该图登记的历史处理数据。",
    },
    "en": {
        "primary_plotting_dataset": "Processed data plotted in this figure.",
        "peak_table": "Peak-position or fit-annotation table used in this figure.",
        "reviewed_dataset_manifest": "Reviewed records and their evidence relationships.",
        "legacy_unspecified": "Legacy processed data registered for this figure.",
    },
}


def localized_figure_caption(figure: dict[str, Any], language: str) -> str:
    caption = str(figure.get("caption") or figure.get("figure_id") or "")
    if language != "zh":
        return caption
    key = str(figure.get("caption_key") or figure.get("purpose") or "")
    return FIGURE_CAPTION_CATALOG["zh"].get(key, caption)


def localized_source_data_purpose(item: dict[str, Any], language: str) -> str:
    normalized = language if language in SOURCE_DATA_PURPOSE_CATALOG else "en"
    role = str(item.get("role") or "")
    catalog = SOURCE_DATA_PURPOSE_CATALOG[normalized]
    if role in catalog:
        return catalog[role]
    if normalized == "zh":
        return "该图的可追溯处理数据。"
    return str(item.get("purpose") or "Traceable processed data for this figure.")


def interpretation_message_key(item: dict[str, Any], method: str) -> str:
    explicit = str(item.get("message_key") or "")
    if explicit:
        return explicit
    text = str(item.get("text") or "")
    lowered = text.lower()
    if method == "raman":
        if item.get("mode_separation_cm-1") is not None and (
            "e2g" in lowered or "a1g" in lowered or "mos2" in lowered
        ):
            return "raman.mos2_pair_thin_layer"
        if "no stable raman peak" in lowered or "未检测到稳定 raman 峰" in lowered:
            return "raman.no_stable_peaks"
        if "no material-specific assignment rule" in lowered or "未匹配到材料特异性" in text:
            return "raman.no_material_rule"
    if "no stable" in lowered or "未检测到稳定" in text:
        return "analysis.no_interpretation"
    return "analysis.review_candidate"


def ensure_interpretation_message_contract(
    analysis: dict[str, Any], method: str
) -> dict[str, Any]:
    analysis["message_contract_version"] = MESSAGE_CONTRACT_VERSION
    for item in analysis.get("possible_interpretations") or []:
        if not isinstance(item, dict):
            continue
        item.setdefault("message_key", interpretation_message_key(item, method))
        args = item.setdefault("message_args", {})
        if not isinstance(args, dict):
            item["message_args"] = {}
            args = item["message_args"]
        if item.get("mode_separation_cm-1") is not None:
            args.setdefault("separation", float(item["mode_separation_cm-1"]))
    return analysis
