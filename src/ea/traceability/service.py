from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any

from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml


TRACE_SCHEMA_VERSION = "0.9.6"
TRACE_BOUNDARIES = [
    "Trace views read local EA artifacts and write traceability audit files only.",
    "They do not mutate reports, figures, source packets, suggestion records, review records, references, or memory.",
    "They do not create ReviewRecords, commit memory, register references, inject citations, generate suggestions/source packets, or prove scientific conclusions.",
]


def _project_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _project_path(root: Path, ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else root / path


def _safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:96] or "focus"


def _safe_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_yaml(path)
    except Exception:
        return {}


def _safe_markdown_frontmatter(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        frontmatter, _ = read_markdown_record(path)
        return frontmatter
    except Exception:
        return {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item).strip()]


def _mapping_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _clean_ref(value: Any) -> str:
    return str(value or "").strip()


def _id_ref(prefix: str, value: Any) -> str:
    value = _clean_ref(value)
    return f"{prefix}:{value}" if value else ""


def _reference_ref(value: Any) -> str:
    return _id_ref("reference", value)


def _source_library_ref(value: Any) -> str:
    return _id_ref("source_library", value)


def _looks_like_path(value: str) -> bool:
    return "/" in value or "." in Path(value).name


def _add_reference_node(
    builder: TraceBuilder,
    reference_id: Any,
    *,
    kind: str = "reference",
    status: str | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    reference_id = _clean_ref(reference_id)
    if not reference_id:
        return ""
    node_id = _reference_ref(reference_id)
    node_ref = builder.add_node(
        node_id,
        kind=kind,
        label=reference_id,
        path=path,
        status=status,
        metadata={"reference_id": reference_id, **(metadata or {})},
    )
    builder.add_alias(reference_id, node_ref)
    builder.add_alias(node_id, node_ref)
    return node_ref


def _add_source_library_node(builder: TraceBuilder, source_library_ref: Any) -> str:
    source_library_ref = _clean_ref(source_library_ref)
    if not source_library_ref:
        return ""
    node_id = _source_library_ref(source_library_ref)
    node_ref = builder.add_node(
        node_id,
        kind="source_library",
        label=source_library_ref,
        status="referenced",
        metadata={"source_library_ref": source_library_ref},
    )
    builder.add_alias(source_library_ref, node_ref)
    builder.add_alias(node_id, node_ref)
    return node_ref


class TraceBuilder:
    def __init__(self, root: Path):
        self.root = root
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.aliases: dict[str, str] = {}
        self._edge_keys: set[tuple[str, str, str]] = set()

    def add_node(
        self,
        node_id: str,
        *,
        kind: str,
        label: str | None = None,
        path: str | None = None,
        status: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not node_id:
            return ""
        record = self.nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "kind": kind,
                "label": label or node_id,
            },
        )
        if not record.get("kind") or record.get("kind") == "unresolved_ref":
            record["kind"] = kind
        if label and (record.get("label") == node_id or not record.get("label")):
            record["label"] = label
        if path:
            record["path"] = path
            record["exists"] = _project_path(self.root, path).exists()
            self.aliases[path] = node_id
        if status:
            record["status"] = status
        if source:
            record["source"] = source
        if metadata:
            current = record.setdefault("metadata", {})
            current.update({key: value for key, value in metadata.items() if value not in (None, "", [], {})})
        self.aliases[node_id] = node_id
        if ":" in node_id:
            prefix, bare_id = node_id.split(":", 1)
            typed_prefixes = {
                "experiment",
                "figure",
                "memory",
                "memory_candidate",
                "provenance",
                "raw",
                "reference",
                "report",
                "result",
                "sample",
                "source_library",
            }
            if prefix in typed_prefixes:
                self.aliases.setdefault(bare_id, node_id)
        return node_id

    def add_alias(self, alias: str, node_id: str) -> None:
        if alias and node_id:
            self.aliases[alias] = node_id

    def canonical(self, value: Any) -> str:
        ref = _clean_ref(value)
        if not ref:
            return ""
        if ref in self.aliases:
            return self.aliases[ref]
        if ref.startswith("prov-"):
            path = f"provenance/{ref}.yml"
            return self.aliases.get(path, path)
        if ref.startswith("review-"):
            path = f"reviews/{ref}.yml"
            return self.aliases.get(path, path)
        if ref.startswith("rpt-"):
            return self.aliases.get(ref, f"report:{ref}")
        if ref.startswith("fig-"):
            return self.aliases.get(ref, f"figure:{ref}")
        if ref.startswith("res-"):
            return self.aliases.get(ref, _id_ref("result", ref))
        if ref.startswith("char-") or ref.startswith("raw-"):
            return self.aliases.get(ref, _id_ref("raw", ref))
        if ref.startswith("sample-"):
            return self.aliases.get(ref, _id_ref("sample", ref))
        if ref.startswith("exp-"):
            return self.aliases.get(ref, _id_ref("experiment", ref))
        if ref.startswith("ref-"):
            return self.aliases.get(ref, _reference_ref(ref))
        if ref.startswith("memcand-"):
            return self.aliases.get(ref, f"memory_candidate:{ref}")
        if ref.startswith("mem-"):
            return self.aliases.get(ref, f"memory:{ref}")
        if _looks_like_path(ref):
            return self.aliases.get(ref, ref)
        return self.aliases.get(ref, f"external:{ref}")

    def add_edge(self, source: Any, target: Any, relation: str) -> None:
        source_id = self.canonical(source)
        target_id = self.canonical(target)
        if not source_id or not target_id or source_id == target_id:
            return
        if source_id not in self.nodes:
            self.add_node(source_id, kind="unresolved_ref", label=source_id)
        if target_id not in self.nodes:
            self.add_node(target_id, kind="unresolved_ref", label=target_id)
        key = (source_id, target_id, relation)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append({"from": source_id, "to": target_id, "relation": relation})


def _load_references(root: Path, builder: TraceBuilder) -> None:
    references = _safe_yaml(root / "literature" / "references" / "index.yml").get("references", {})
    if not isinstance(references, dict):
        return
    for reference_id, reference in references.items():
        if not isinstance(reference, dict):
            continue
        reference_ref = str(reference.get("path") or f"literature/references/{reference_id}.yml")
        detail = _safe_yaml(_project_path(root, reference_ref))
        metadata = {
            "citation": detail.get("citation") or reference.get("citation"),
            "title": detail.get("title") or reference.get("title"),
            "doi": detail.get("doi") or reference.get("doi"),
            "url": detail.get("url") or reference.get("url"),
            "source_type": detail.get("source_type") or reference.get("source_type"),
            "local_path": detail.get("local_path") or reference.get("local_path"),
        }
        node_id = _add_reference_node(builder, reference_id, status="registered", path=reference_ref, metadata=metadata)
        for source_ref in _string_list(detail.get("source_refs") or reference.get("source_refs")):
            builder.add_edge(node_id, source_ref, "has_source")
        for provenance_ref in _string_list(detail.get("provenance_refs") or reference.get("provenance_refs")):
            builder.add_edge(node_id, provenance_ref, "has_provenance")
        for review_ref in _string_list(detail.get("review_refs") or reference.get("review_refs")):
            builder.add_edge(node_id, review_ref, "has_review")


def _load_reports(root: Path, builder: TraceBuilder) -> None:
    reports = _safe_yaml(root / "reports" / "index.yml").get("reports", {})
    if not isinstance(reports, dict):
        return
    for report_id, report in reports.items():
        report_ref = str(report.get("path") or f"reports/{report_id}.md")
        frontmatter = _safe_markdown_frontmatter(_project_path(root, report_ref))
        node_id = builder.add_node(
            report_ref,
            kind="report",
            label=str(report_id),
            path=report_ref,
            status=str(frontmatter.get("status") or report.get("status") or ""),
            metadata={
                "report_id": report_id,
                "report_type": frontmatter.get("report_type"),
                "reference_ids": report.get("reference_ids") or frontmatter.get("reference_ids") or [],
            },
        )
        builder.add_alias(str(report_id), node_id)
        builder.add_alias(_id_ref("report", report_id), node_id)
        for result_id in _string_list(report.get("result_ids") or frontmatter.get("related_results")):
            builder.add_node(_id_ref("result", result_id), kind="processed_result", label=result_id)
            builder.add_edge(node_id, _id_ref("result", result_id), "uses_result")
        for figure_id in _string_list(report.get("figure_ids") or frontmatter.get("figure_ids")):
            builder.add_edge(node_id, figure_id, "includes_figure")
        for sample_id in _string_list(report.get("sample_ids") or frontmatter.get("related_samples")):
            builder.add_node(_id_ref("sample", sample_id), kind="sample", label=sample_id)
            builder.add_edge(node_id, _id_ref("sample", sample_id), "about_sample")
        for experiment_id in _string_list(report.get("experiment_ids") or frontmatter.get("related_experiments")):
            builder.add_node(_id_ref("experiment", experiment_id), kind="experiment", label=experiment_id)
            builder.add_edge(node_id, _id_ref("experiment", experiment_id), "about_experiment")
        for reference_id in _string_list(report.get("reference_ids") or frontmatter.get("reference_ids")):
            reference_ref = _add_reference_node(builder, reference_id)
            builder.add_edge(node_id, reference_ref, "cites_reference")
        for provenance_ref in _string_list(frontmatter.get("provenance_refs")):
            builder.add_edge(node_id, provenance_ref, "has_provenance")


def _load_figures(root: Path, builder: TraceBuilder) -> None:
    figures = _safe_yaml(root / "figures" / "index.yml").get("figures", {})
    if not isinstance(figures, dict):
        return
    for figure_id, figure in figures.items():
        figure_ref = str(figure.get("path") or f"figure:{figure_id}")
        node_id = builder.add_node(
            figure_ref,
            kind="figure",
            label=str(figure_id),
            path=figure_ref if _looks_like_path(figure_ref) else None,
            status="indexed",
            metadata={
                "figure_id": figure_id,
                "caption": figure.get("caption"),
                "style_profile": figure.get("style_profile"),
            },
        )
        builder.add_alias(str(figure_id), node_id)
        builder.add_alias(_id_ref("figure", figure_id), node_id)
        if figure.get("report_id"):
            builder.add_edge(node_id, str(figure["report_id"]), "rendered_in_report")
        if figure.get("result_id"):
            result_ref = _id_ref("result", figure["result_id"])
            builder.add_node(result_ref, kind="processed_result", label=str(figure["result_id"]))
            builder.add_edge(node_id, result_ref, "visualizes_result")
        for raw_id in _string_list(figure.get("raw_data_ids")):
            raw_ref = _id_ref("raw", raw_id)
            builder.add_node(raw_ref, kind="raw_data", label=raw_id)
            builder.add_edge(node_id, raw_ref, "derived_from_raw")
        for sample_id in _string_list(figure.get("sample_ids")):
            sample_ref = _id_ref("sample", sample_id)
            builder.add_node(sample_ref, kind="sample", label=sample_id)
            builder.add_edge(node_id, sample_ref, "about_sample")
        for experiment_id in _string_list(figure.get("experiment_ids")):
            experiment_ref = _id_ref("experiment", experiment_id)
            builder.add_node(experiment_ref, kind="experiment", label=experiment_id)
            builder.add_edge(node_id, experiment_ref, "about_experiment")
        for source_data_ref in _string_list(figure.get("source_data_refs")):
            builder.add_edge(node_id, source_data_ref, "uses_source_data")


def _load_reviews(root: Path, builder: TraceBuilder) -> None:
    for path in sorted((root / "reviews").glob("*.yml")):
        review = _safe_yaml(path)
        review_id = str(review.get("review_id") or path.stem)
        review_ref = _project_ref(root, path)
        node_id = builder.add_node(
            review_ref,
            kind="review",
            label=review_id,
            path=review_ref,
            status=str(review.get("review_status") or ""),
            metadata={"target_type": review.get("target_type"), "decision": review.get("decision")},
        )
        builder.add_alias(review_id, node_id)
        builder.add_alias(_id_ref("review", review_id), node_id)
        if review.get("target_ref"):
            builder.add_edge(node_id, str(review["target_ref"]), "reviews_target")


def _load_memory(root: Path, builder: TraceBuilder) -> None:
    candidates = _safe_yaml(root / "memory" / "candidates" / "index.yml").get("candidates", {})
    if isinstance(candidates, dict):
        for candidate_id, candidate in candidates.items():
            candidate_ref = str(candidate.get("path") or f"memory/candidates/{candidate_id}.md")
            frontmatter = _safe_markdown_frontmatter(_project_path(root, candidate_ref))
            node_id = builder.add_node(
                candidate_ref,
                kind="memory_candidate",
                label=str(candidate_id),
                path=candidate_ref,
                status=str(frontmatter.get("status") or candidate.get("status") or ""),
                metadata={
                    "category": frontmatter.get("category") or candidate.get("category"),
                    "confidence": frontmatter.get("confidence") or candidate.get("confidence"),
                    "committed_memory_id": frontmatter.get("committed_memory_id") or candidate.get("committed_memory_id"),
                },
            )
            builder.add_alias(str(candidate_id), node_id)
            builder.add_alias(_id_ref("memory_candidate", candidate_id), node_id)
            for source_ref in _string_list(frontmatter.get("source_refs") or candidate.get("source_refs")):
                builder.add_edge(node_id, source_ref, "has_source")
            for provenance_ref in _string_list(frontmatter.get("provenance_refs") or candidate.get("provenance_refs")):
                builder.add_edge(node_id, provenance_ref, "has_provenance")
            for review_ref in _string_list(frontmatter.get("review_refs") or candidate.get("review_refs")):
                builder.add_edge(node_id, review_ref, "has_review")
            committed_id = frontmatter.get("committed_memory_id") or candidate.get("committed_memory_id")
            if committed_id:
                builder.add_edge(node_id, _id_ref("memory", committed_id), "committed_as")

    memories = _safe_yaml(root / "memory" / "index.yml").get("memories", {})
    if isinstance(memories, dict):
        for memory_id, memory in memories.items():
            node_id = builder.add_node(
                _id_ref("memory", memory_id),
                kind="memory",
                label=str(memory_id),
                status="committed",
                metadata={"category": memory.get("category"), "confidence": memory.get("confidence"), "target_ref": memory.get("target_ref")},
            )
            builder.add_alias(str(memory_id), node_id)
            if memory.get("candidate_ref"):
                builder.add_edge(node_id, str(memory["candidate_ref"]), "from_candidate")
            if memory.get("target_ref"):
                builder.add_edge(node_id, str(memory["target_ref"]), "written_to")
            for source_ref in _string_list(memory.get("source_refs")):
                builder.add_edge(node_id, source_ref, "has_source")
            for provenance_ref in _string_list(memory.get("provenance_refs")):
                builder.add_edge(node_id, provenance_ref, "has_provenance")
            for review_ref in _string_list(memory.get("review_refs")):
                builder.add_edge(node_id, review_ref, "has_review")


def _suggestion_kind(source: str, path: Path) -> str:
    if "source_packet" in source:
        return "source_packet"
    if "suggestions" in source:
        return "suggestion_record"
    if "review_package" in source:
        return "review_package"
    if "source_candidates" in source:
        return "source_candidate_manifest"
    if path.name.endswith("_preflight.yml"):
        return "preflight_record"
    return "suggestion_artifact"


def _load_suggestion_artifacts(root: Path, builder: TraceBuilder) -> None:
    suggestions_root = root / "suggestions"
    if not suggestions_root.exists():
        return
    for path in sorted(suggestions_root.rglob("*.yml")):
        data = _safe_yaml(path)
        ref = _project_ref(root, path)
        source = str(data.get("source") or "")
        node_id = builder.add_node(
            ref,
            kind=_suggestion_kind(source, path),
            label=str(data.get("suggestion_id") or data.get("source_packet_id") or data.get("review_package_id") or path.stem),
            path=ref,
            status=str(data.get("status") or ""),
            source=source,
            metadata={
                "candidate_count": data.get("candidate_count"),
                "source_library_kind": data.get("source_library_kind"),
                "method": data.get("method"),
            },
        )
        for key in ["suggestion_id", "source_packet_id", "review_package_id"]:
            if data.get(key):
                builder.add_alias(str(data[key]), node_id)
        if data.get("source_library_ref"):
            _add_source_library_node(builder, data["source_library_ref"])
        link_fields = {
            "source_packet_ref": "from_source_packet",
            "source_manifest_ref": "from_source_manifest",
            "source_library_ref": "from_source_library",
            "suggestion_ref": "summarizes_suggestion",
            "table_ref": "has_table",
            "feature_table_ref": "uses_feature_table",
            "ftir_metadata_ref": "uses_result_metadata",
            "xps_metadata_ref": "uses_result_metadata",
            "review_target_ref": "review_target",
            "provenance_ref": "has_provenance",
        }
        for field, relation in link_fields.items():
            if data.get(field):
                builder.add_edge(node_id, str(data[field]), relation)
        for related_ref in _string_list(data.get("related_records")):
            builder.add_edge(node_id, related_ref, "related_record")
        reference_seed_data = data.get("reference_seeds") if isinstance(data.get("reference_seeds"), dict) else {}
        for reference_id, seed in reference_seed_data.items():
            seed_metadata = seed if isinstance(seed, dict) else {}
            reference_ref = _add_reference_node(builder, reference_id, kind="reference_seed", status="seed_or_registered", metadata=seed_metadata)
            builder.add_edge(node_id, reference_ref, "has_reference_seed")
        for reference_id in _string_list(data.get("reference_ids")):
            reference_ref = _add_reference_node(builder, reference_id)
            builder.add_edge(node_id, reference_ref, "uses_reference")
        for reference_id in _string_list(data.get("guidance_reference_ids")):
            reference_ref = _add_reference_node(builder, reference_id)
            builder.add_edge(node_id, reference_ref, "uses_guidance_reference")
        for unresolved_id in _string_list(data.get("unresolved_reference_ids")):
            reference_ref = _add_reference_node(builder, unresolved_id, status="unresolved")
            builder.add_edge(node_id, reference_ref, "has_unresolved_reference")
        for candidate in _mapping_records(data.get("candidates")) + _mapping_records(data.get("candidate_summaries")):
            for reference_id in _string_list(candidate.get("reference_ids")):
                reference_ref = _add_reference_node(builder, reference_id)
                builder.add_edge(node_id, reference_ref, "candidate_uses_reference")
            for unresolved_id in _string_list(candidate.get("unresolved_reference_ids")):
                reference_ref = _add_reference_node(builder, unresolved_id, status="unresolved")
                builder.add_edge(node_id, reference_ref, "candidate_unresolved_reference")


def _load_provenance(root: Path, builder: TraceBuilder) -> None:
    for path in sorted((root / "provenance").glob("*.yml")):
        provenance = _safe_yaml(path)
        provenance_id = str(provenance.get("provenance_id") or path.stem)
        provenance_ref = _project_ref(root, path)
        node_id = builder.add_node(
            provenance_ref,
            kind="provenance",
            label=provenance_id,
            path=provenance_ref,
            status=str(provenance.get("workflow") or ""),
            metadata={"workflow": provenance.get("workflow"), "created_at": provenance.get("created_at")},
        )
        builder.add_alias(provenance_id, node_id)
        builder.add_alias(_id_ref("provenance", provenance_id), node_id)
        inputs = provenance.get("inputs") if isinstance(provenance.get("inputs"), dict) else {}
        outputs = provenance.get("outputs") if isinstance(provenance.get("outputs"), dict) else {}
        for ref in _string_list(inputs.get("records")):
            builder.add_edge(node_id, ref, "input_record")
        for ref in _string_list(outputs.get("records")):
            builder.add_edge(node_id, ref, "output_record")
        for ref in _string_list(provenance.get("source_refs")):
            if _looks_like_path(ref):
                builder.add_edge(node_id, ref, "source_record")
            elif ref.startswith("builtin:"):
                source_library_ref = _add_source_library_node(builder, ref)
                builder.add_edge(node_id, source_library_ref, "source_library")
            else:
                reference_ref = _add_reference_node(builder, ref)
                builder.add_edge(node_id, reference_ref, "source_reference")
        for ref in _string_list(provenance.get("review_refs")):
            builder.add_edge(node_id, ref, "review_ref")


def _normalize_aliases(builder: TraceBuilder) -> None:
    normalized_edges: list[dict[str, str]] = []
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in builder.edges:
        source_id = builder.aliases.get(edge["from"], edge["from"])
        target_id = builder.aliases.get(edge["to"], edge["to"])
        key = (source_id, target_id, edge["relation"])
        if source_id == target_id or key in edge_keys:
            continue
        edge_keys.add(key)
        normalized_edges.append({"from": source_id, "to": target_id, "relation": edge["relation"]})
    aliased_nodes = {alias for alias, target in builder.aliases.items() if alias != target and alias in builder.nodes}
    for node_id in aliased_nodes:
        if builder.nodes.get(node_id, {}).get("kind") == "unresolved_ref":
            builder.nodes.pop(node_id, None)
    builder.edges = normalized_edges


def _filter_focus(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]],
    focus: str | None,
    aliases: dict[str, str],
    *,
    max_depth: int | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], str | None]:
    if not focus:
        return nodes, edges, None
    focus_id = aliases.get(focus, focus)
    if focus_id not in nodes:
        return nodes, edges, focus_id
    graph: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in edges:
        graph.setdefault(edge["from"], set()).add(edge["to"])
        graph.setdefault(edge["to"], set()).add(edge["from"])
    selected = {focus_id}
    depths = {focus_id: 0}
    queue: deque[str] = deque([focus_id])
    while queue:
        current = queue.popleft()
        if max_depth is not None and depths[current] >= max_depth:
            continue
        for neighbor in graph.get(current, set()):
            if neighbor not in selected:
                selected.add(neighbor)
                depths[neighbor] = depths[current] + 1
                queue.append(neighbor)
    return (
        {node_id: record for node_id, record in nodes.items() if node_id in selected},
        [edge for edge in edges if edge["from"] in selected and edge["to"] in selected],
        focus_id,
    )


def _render_markdown(trace: dict[str, Any]) -> str:
    kind_counts = trace["summary"]["node_counts_by_kind"]
    lines = [
        "# EA Trace View",
        "",
        f"- trace_id: `{trace['trace_id']}`",
        f"- status: `{trace['status']}`",
        f"- focus_ref: `{trace.get('focus_ref') or 'all-project'}`",
        f"- node_count: `{trace['summary']['node_count']}`",
        f"- edge_count: `{trace['summary']['edge_count']}`",
        "",
        "## Node Counts",
        "",
        "| kind | count |",
        "|---|---:|",
    ]
    for kind, count in sorted(kind_counts.items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(["", "## Key Records", ""])
    priority_kinds = {
        "report",
        "figure",
        "reference",
        "reference_seed",
        "source_library",
        "source_packet",
        "suggestion_record",
        "review_package",
        "review",
        "memory_candidate",
        "memory",
        "provenance",
    }
    for node in trace["nodes"]:
        if node["kind"] not in priority_kinds:
            continue
        label = node.get("label") or node["id"]
        status = node.get("status") or "n/a"
        path = node.get("path") or node["id"]
        lines.append(f"- `{node['kind']}` `{label}` -> `{path}` (status: `{status}`)")
    lines.extend(["", "## Edges", ""])
    for edge in trace["edges"][:200]:
        lines.append(f"- `{edge['from']}` --{edge['relation']}--> `{edge['to']}`")
    if len(trace["edges"]) > 200:
        lines.append(f"- ... {len(trace['edges']) - 200} more edges omitted from Markdown view; see YAML for complete data.")
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {item}" for item in trace["boundaries"])
    return "\n".join(lines) + "\n"


def _build_trace_builder(root: Path) -> TraceBuilder:
    builder = TraceBuilder(root)
    _load_references(root, builder)
    _load_reports(root, builder)
    _load_figures(root, builder)
    _load_reviews(root, builder)
    _load_memory(root, builder)
    _load_suggestion_artifacts(root, builder)
    _load_provenance(root, builder)
    _normalize_aliases(builder)
    return builder


def _trace_payload(
    *,
    root: Path,
    builder: TraceBuilder,
    focus_ref: str | None,
    created_at: str,
    focus_depth: int | None = None,
) -> dict[str, Any]:
    trace_id = f"trace-{created_at[:10].replace('-', '')}-{created_at[11:19].replace(':', '')}"
    nodes, edges, canonical_focus = _filter_focus(
        builder.nodes,
        builder.edges,
        focus_ref,
        builder.aliases,
        max_depth=focus_depth,
    )
    node_list = sorted(nodes.values(), key=lambda item: (item.get("kind", ""), item.get("id", "")))
    edge_list = sorted(edges, key=lambda item: (item["from"], item["relation"], item["to"]))
    kind_counts = Counter(node["kind"] for node in node_list)
    relation_counts = Counter(edge["relation"] for edge in edge_list)
    missing_nodes = sorted(node["id"] for node in node_list if node.get("exists") is False)

    return {
        "schema_version": "0.2",
        "source": "ea.traceability.project_trace_view:v0.2",
        "trace_id": trace_id,
        "status": "complete" if not missing_nodes else "complete_with_missing_refs",
        "created_at": created_at,
        "root_ref": ".",
        "focus_ref": focus_ref,
        "canonical_focus_ref": canonical_focus,
        "focus_depth": focus_depth,
        "summary": {
            "node_count": len(node_list),
            "edge_count": len(edge_list),
            "node_counts_by_kind": dict(sorted(kind_counts.items())),
            "edge_counts_by_relation": dict(sorted(relation_counts.items())),
            "missing_node_count": len(missing_nodes),
        },
        "nodes": node_list,
        "edges": edge_list,
        "missing_nodes": missing_nodes,
        "boundaries": TRACE_BOUNDARIES,
    }


def _compact_node(node: dict[str, Any]) -> dict[str, Any]:
    keys = ["id", "kind", "label", "path", "status", "source", "exists"]
    return {key: node[key] for key in keys if key in node and node[key] not in (None, "", [], {})}


def _compact_trace_index_payload(trace: dict[str, Any], *, index_id: str) -> dict[str, Any]:
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "source": "ea.traceability.trace_index:v0.9.6",
        "index_id": index_id,
        "status": trace["status"],
        "created_at": trace["created_at"],
        "trace_id": trace["trace_id"],
        "root_ref": trace["root_ref"],
        "summary": trace["summary"],
        "nodes": [_compact_node(node) for node in trace["nodes"]],
        "edges": trace["edges"],
        "missing_nodes": trace["missing_nodes"],
        "boundaries": trace["boundaries"],
    }


def _normalize_trace_output_paths(
    root: Path,
    *,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
) -> tuple[Path, Path]:
    output_path = output_path or root / "traceability" / "project_trace.yml"
    markdown_output_path = markdown_output_path or output_path.with_suffix(".md")
    if not output_path.is_absolute():
        output_path = root / output_path
    if not markdown_output_path.is_absolute():
        markdown_output_path = root / markdown_output_path
    return output_path, markdown_output_path


def _write_trace_outputs(root: Path, trace: dict[str, Any], output_path: Path, markdown_output_path: Path) -> None:
    write_yaml(output_path, trace)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(_render_markdown(trace), encoding="utf-8")


def build_project_trace_view(
    root: Path,
    *,
    focus_ref: str | None = None,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
    created_at: str | None = None,
    focus_depth: int | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    created_at = created_at or EARecord.now_iso()
    output_path, markdown_output_path = _normalize_trace_output_paths(
        root,
        output_path=output_path,
        markdown_output_path=markdown_output_path,
    )

    builder = _build_trace_builder(root)
    trace = _trace_payload(root=root, builder=builder, focus_ref=focus_ref, created_at=created_at, focus_depth=focus_depth)
    _write_trace_outputs(root, trace, output_path, markdown_output_path)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "source": "ea.traceability.project_trace_view_summary:v0.9.6",
        "trace_id": trace["trace_id"],
        "status": trace["status"],
        "trace_path": str(output_path),
        "trace_ref": _project_ref(root, output_path),
        "markdown_path": str(markdown_output_path),
        "markdown_ref": _project_ref(root, markdown_output_path),
        "node_count": trace["summary"]["node_count"],
        "edge_count": trace["summary"]["edge_count"],
        "missing_node_count": trace["summary"]["missing_node_count"],
        "focus_ref": focus_ref,
        "canonical_focus_ref": trace["canonical_focus_ref"],
        "focus_depth": focus_depth,
        "node_counts_by_kind": trace["summary"]["node_counts_by_kind"],
        "edge_counts_by_relation": trace["summary"]["edge_counts_by_relation"],
        "boundaries": TRACE_BOUNDARIES,
    }


def build_trace_index(
    root: Path,
    *,
    output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    created_at = created_at or EARecord.now_iso()
    output_path = output_path or root / "traceability" / "index.yml"
    if not output_path.is_absolute():
        output_path = root / output_path
    builder = _build_trace_builder(root)
    trace = _trace_payload(root=root, builder=builder, focus_ref=None, created_at=created_at)
    index_id = f"trace-index-{created_at[:10].replace('-', '')}-{created_at[11:19].replace(':', '')}"
    index = _compact_trace_index_payload(trace, index_id=index_id)
    write_yaml(output_path, index)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "source": "ea.traceability.trace_index_summary:v0.9.6",
        "status": index["status"],
        "index_id": index_id,
        "index_path": str(output_path),
        "index_ref": _project_ref(root, output_path),
        "node_count": index["summary"]["node_count"],
        "edge_count": index["summary"]["edge_count"],
        "missing_node_count": index["summary"]["missing_node_count"],
        "node_counts_by_kind": index["summary"]["node_counts_by_kind"],
        "edge_counts_by_relation": index["summary"]["edge_counts_by_relation"],
        "boundaries": TRACE_BOUNDARIES,
    }


def build_trace_focus(
    root: Path,
    record_ref: str,
    *,
    depth: int = 2,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    safe_ref = _safe_filename(record_ref)
    output_path = output_path or root / "traceability" / f"focus-{safe_ref}.yml"
    markdown_output_path = markdown_output_path or output_path.with_suffix(".md")
    return build_project_trace_view(
        root,
        focus_ref=record_ref,
        output_path=output_path,
        markdown_output_path=markdown_output_path,
        created_at=created_at,
        focus_depth=max(depth, 0),
    )


def export_full_trace(
    root: Path,
    *,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output_path = output_path or root / "traceability" / "full_trace.yml"
    markdown_output_path = markdown_output_path or output_path.with_suffix(".md")
    result = build_project_trace_view(
        root,
        output_path=output_path,
        markdown_output_path=markdown_output_path,
        created_at=created_at,
    )
    result["export_mode"] = "full"
    return result


def _node_lookup_payload(root: Path, node: dict[str, Any] | None, node_id: str) -> dict[str, Any]:
    node = node or {"id": node_id, "kind": "unresolved_ref", "label": node_id}
    payload = {
        "id": node.get("id") or node_id,
        "kind": node.get("kind"),
        "label": node.get("label"),
        "status": node.get("status"),
        "path": node.get("path"),
        "source": node.get("source"),
        "metadata": node.get("metadata") or {},
    }
    path_ref = node.get("path") or (node_id if _looks_like_path(node_id) else "")
    if path_ref:
        absolute_path = _project_path(root, str(path_ref))
        payload["path"] = str(path_ref)
        payload["absolute_path"] = str(absolute_path)
        payload["path_exists"] = absolute_path.exists()
    elif "exists" in node:
        payload["path_exists"] = bool(node["exists"])
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _lookup_neighbors(
    root: Path,
    canonical_ref: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, str]],
) -> dict[str, Any]:
    incoming: list[dict[str, Any]] = []
    outgoing: list[dict[str, Any]] = []
    for edge in edges:
        if edge["to"] == canonical_ref:
            incoming.append(
                {
                    "relation": edge["relation"],
                    "from": _node_lookup_payload(root, nodes.get(edge["from"]), edge["from"]),
                }
            )
        if edge["from"] == canonical_ref:
            outgoing.append(
                {
                    "relation": edge["relation"],
                    "to": _node_lookup_payload(root, nodes.get(edge["to"]), edge["to"]),
                }
            )
    return {
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
        "incoming": sorted(incoming, key=lambda item: (item["relation"], item["from"]["id"])),
        "outgoing": sorted(outgoing, key=lambda item: (item["relation"], item["to"]["id"])),
    }


def lookup_trace_record(
    root: Path,
    record_ref: str,
    *,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    created_at = created_at or EARecord.now_iso()
    output_path, markdown_output_path = _normalize_trace_output_paths(
        root,
        output_path=output_path,
        markdown_output_path=markdown_output_path,
    )

    builder = _build_trace_builder(root)
    trace = _trace_payload(root=root, builder=builder, focus_ref=None, created_at=created_at)
    _write_trace_outputs(root, trace, output_path, markdown_output_path)

    canonical_ref = builder.canonical(record_ref)
    node = builder.nodes.get(canonical_ref)
    status = "found" if node is not None else "not_found"
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "source": "ea.traceability.lookup_trace_record:v0.9.6",
        "status": status,
        "query": record_ref,
        "canonical_ref": canonical_ref,
        "node": _node_lookup_payload(root, node, canonical_ref) if node else None,
        "related": (
            _lookup_neighbors(root, canonical_ref, builder.nodes, builder.edges)
            if node
            else {"incoming_count": 0, "outgoing_count": 0, "incoming": [], "outgoing": []}
        ),
        "trace_id": trace["trace_id"],
        "trace_status": trace["status"],
        "trace_path": str(output_path),
        "trace_ref": _project_ref(root, output_path),
        "markdown_path": str(markdown_output_path),
        "markdown_ref": _project_ref(root, markdown_output_path),
        "boundaries": TRACE_BOUNDARIES,
    }
