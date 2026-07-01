from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.storage import read_yaml, write_markdown_record, write_yaml
from ea.traceability import build_project_trace_view


def _write_trace_fixture(root: Path) -> None:
    write_markdown_record(
        root / "reports" / "rpt-trace-20260701-001.md",
        {
            "schema_version": "0.2",
            "report_id": "rpt-trace-20260701-001",
            "project_id": "prj-trace",
            "report_type": "ftir_analysis",
            "status": "draft",
            "related_results": ["res-trace-ftir-001"],
            "figure_ids": ["fig-trace-ftir-001"],
            "related_samples": ["sample-trace-001"],
            "related_experiments": ["exp-trace-001"],
            "reference_ids": ["ref-trace-001"],
            "provenance_refs": ["prov-trace-report"],
        },
        "# Trace report\n",
    )
    write_yaml(
        root / "reports" / "index.yml",
        {
            "schema_version": "0.2",
            "reports": {
                "rpt-trace-20260701-001": {
                    "report_id": "rpt-trace-20260701-001",
                    "path": "reports/rpt-trace-20260701-001.md",
                    "project_id": "prj-trace",
                    "result_ids": ["res-trace-ftir-001"],
                    "figure_ids": ["fig-trace-ftir-001"],
                    "sample_ids": ["sample-trace-001"],
                    "experiment_ids": ["exp-trace-001"],
                    "reference_ids": ["ref-trace-001"],
                }
            },
        },
    )
    write_yaml(
        root / "figures" / "index.yml",
        {
            "schema_version": "0.2",
            "figures": {
                "fig-trace-ftir-001": {
                    "figure_id": "fig-trace-ftir-001",
                    "path": "figures/fig-trace-ftir-001.png",
                    "report_id": "rpt-trace-20260701-001",
                    "result_id": "res-trace-ftir-001",
                    "raw_data_ids": ["char-trace-001"],
                    "sample_ids": ["sample-trace-001"],
                    "source_data_refs": ["processed/sample-trace-001/ftir/source.csv"],
                    "style_profile": "nature_like_clean",
                }
            },
        },
    )
    (root / "figures").mkdir(parents=True, exist_ok=True)
    (root / "figures" / "fig-trace-ftir-001.png").write_bytes(b"fake-png")
    write_yaml(
        root / "literature" / "references" / "ref-trace-001.yml",
        {
            "schema_version": "0.2",
            "reference_id": "ref-trace-001",
            "project_id": "prj-trace",
            "citation": "Trace Reference. Example Journal 1, 1-2 (2026).",
            "title": "Trace Reference",
            "doi": "10.0000/trace",
            "url": "https://doi.org/10.0000/trace",
            "source_type": "manual",
            "source_refs": [],
            "provenance_refs": ["prov-trace-reference"],
            "review_refs": [],
        },
    )
    write_yaml(
        root / "literature" / "references" / "index.yml",
        {
            "schema_version": "0.2",
            "references": {
                "ref-trace-001": {
                    "reference_id": "ref-trace-001",
                    "path": "literature/references/ref-trace-001.yml",
                    "project_id": "prj-trace",
                    "citation": "Trace Reference. Example Journal 1, 1-2 (2026).",
                    "doi": "10.0000/trace",
                    "url": "https://doi.org/10.0000/trace",
                    "source_type": "manual",
                }
            },
        },
    )
    write_yaml(
        root / "suggestions" / "ftir" / "source-packets" / "packet.yml",
        {
            "schema_version": "0.2",
            "source": "ea.ftir.assignment_source_packet:v0.2",
            "source_packet_id": "ftir-packet-trace-001",
            "status": "ready_for_suggest_assignments",
            "project_id": "prj-trace",
            "source_library_kind": "built_in",
            "source_library_ref": "builtin:generic_materials",
            "reference_seeds": {
                "ref-trace-001": {
                    "citation": "Trace Reference. Example Journal 1, 1-2 (2026).",
                    "title": "Trace Reference",
                    "doi": "10.0000/trace",
                    "url": "https://doi.org/10.0000/trace",
                    "source_type": "manual",
                }
            },
            "guidance_reference_ids": ["ref-trace-001"],
            "reference_ids": ["ref-trace-001"],
            "candidates": [
                {
                    "candidate_id": "ftir-trace-carbonyl",
                    "reference_ids": ["ref-trace-001"],
                    "unresolved_reference_ids": ["ref-trace-missing"],
                }
            ],
            "provenance_ref": "provenance/prov-trace-packet.yml",
        },
    )
    write_yaml(
        root / "suggestions" / "ftir" / "suggestion-20260701-001" / "ftir_assignment_suggestions.yml",
        {
            "schema_version": "0.2",
            "source": "ea.ftir.assignment_suggestions:v0.2",
            "suggestion_id": "suggestion-20260701-001",
            "status": "ready_for_user_review",
            "project_id": "prj-trace",
            "source_packet_ref": "suggestions/ftir/source-packets/packet.yml",
            "table_ref": "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.csv",
            "feature_table_ref": "processed/sample-trace-001/ftir/features.csv",
            "ftir_metadata_ref": "processed/sample-trace-001/ftir/ftir_metadata.yml",
            "related_records": ["reports/rpt-trace-20260701-001.md"],
            "reference_ids": ["ref-trace-001"],
            "candidates": [
                {
                    "candidate_id": "ftir-trace-carbonyl",
                    "reference_ids": ["ref-trace-001"],
                    "unresolved_reference_ids": [],
                }
            ],
            "provenance_ref": "provenance/prov-trace-suggestion.yml",
        },
    )
    write_yaml(
        root / "suggestions" / "ftir" / "suggestion-20260701-001" / "review_package.yml",
        {
            "schema_version": "0.2",
            "source": "ea.ftir.assignment_review_package:v0.2",
            "review_package_id": "suggestion-20260701-001-review-package",
            "status": "review_package_prepared",
            "suggestion_ref": "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
            "source_packet_ref": "suggestions/ftir/source-packets/packet.yml",
            "review_target_type": "ftir_assignment_suggestions",
            "review_target_ref": "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
            "reference_ids": ["ref-trace-001"],
            "provenance_ref": "provenance/prov-trace-review-package.yml",
        },
    )
    write_yaml(
        root / "reviews" / "review-trace-001.yml",
        {
            "review_id": "review-trace-001",
            "target_type": "ftir_assignment_suggestions",
            "target_ref": "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
            "review_status": "user_confirmed",
            "decision": "confirmed_by_user",
            "reviewed_at": "2026-07-01T16:00:00",
            "user_original_text": "可以，保存",
            "reviewed_content_hash": "abc123",
        },
    )
    write_markdown_record(
        root / "memory" / "candidates" / "memcand-trace-001.md",
        {
            "schema_version": "0.2",
            "memory_candidate_id": "memcand-trace-001",
            "project_id": "prj-trace",
            "status": "user_confirmed",
            "category": "interpretation",
            "confidence": "medium",
            "source_refs": [
                "reports/rpt-trace-20260701-001.md",
                "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
                "ref-trace-001",
            ],
            "provenance_refs": ["prov-trace-memory"],
            "review_refs": ["review-trace-001"],
            "committed_memory_id": "mem-trace-001",
        },
        "Candidate memory from reviewed FTIR source-backed suggestion.",
    )
    write_yaml(
        root / "memory" / "candidates" / "index.yml",
        {
            "schema_version": "0.2",
            "candidates": {
                "memcand-trace-001": {
                    "memory_candidate_id": "memcand-trace-001",
                    "path": "memory/candidates/memcand-trace-001.md",
                    "project_id": "prj-trace",
                    "status": "user_confirmed",
                    "category": "interpretation",
                    "confidence": "medium",
                    "source_refs": ["reports/rpt-trace-20260701-001.md"],
                    "provenance_refs": ["prov-trace-memory"],
                    "review_refs": ["review-trace-001"],
                    "committed_memory_id": "mem-trace-001",
                }
            },
        },
    )
    write_yaml(
        root / "memory" / "index.yml",
        {
            "schema_version": "0.2",
            "memories": {
                "mem-trace-001": {
                    "memory_id": "mem-trace-001",
                    "project_id": "prj-trace",
                    "category": "interpretation",
                    "confidence": "medium",
                    "candidate_ref": "memory/candidates/memcand-trace-001.md",
                    "source_refs": ["reports/rpt-trace-20260701-001.md"],
                    "provenance_refs": ["prov-trace-memory"],
                    "review_refs": ["review-trace-001"],
                    "target_ref": "memory/confirmed-findings.md",
                }
            },
        },
    )
    for provenance_id, workflow, inputs, outputs in [
        ("prov-trace-reference", "reference_registration", [], ["literature/references/ref-trace-001.yml"]),
        ("prov-trace-report", "report_generation", ["processed/sample-trace-001/ftir/ftir_metadata.yml"], ["reports/rpt-trace-20260701-001.md"]),
        ("prov-trace-packet", "ftir_assignment_source_packet", [], ["suggestions/ftir/source-packets/packet.yml"]),
        (
            "prov-trace-suggestion",
            "ftir_assignment_suggestion",
            ["suggestions/ftir/source-packets/packet.yml"],
            ["suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml"],
        ),
        (
            "prov-trace-review-package",
            "ftir_assignment_review_package",
            ["suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml"],
            ["suggestions/ftir/suggestion-20260701-001/review_package.yml"],
        ),
        ("prov-trace-memory", "memory_candidate_proposal", ["reports/rpt-trace-20260701-001.md"], ["memory/candidates/memcand-trace-001.md"]),
    ]:
        write_yaml(
            root / "provenance" / f"{provenance_id}.yml",
            {
                "schema_version": "0.2",
                "provenance_id": provenance_id,
                "workflow": workflow,
                "created_at": "2026-07-01T16:05:00",
                "skill_name": "ea-core",
                "skill_version": "0.2.0",
                "inputs": {"records": inputs, "files": []},
                "outputs": {"records": outputs, "files": []},
                "parameters": {},
                "review_refs": ["review-trace-001"] if "memory" in workflow else [],
                "source_refs": ["ref-trace-001"],
            },
        )


def test_project_trace_view_links_reports_suggestions_reviews_and_memory(tmp_path: Path) -> None:
    _write_trace_fixture(tmp_path)

    result = build_project_trace_view(tmp_path, created_at="2026-07-01T16:10:00")
    trace = read_yaml(Path(result["trace_path"]))
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    kinds = {node["kind"] for node in trace["nodes"]}
    edges = {(edge["from"], edge["relation"], edge["to"]) for edge in trace["edges"]}

    assert result["status"] == "complete"
    assert "report" in kinds
    assert "figure" in kinds
    assert "source_packet" in kinds
    assert "suggestion_record" in kinds
    assert "review_package" in kinds
    assert "reference" in kinds
    assert "source_library" in kinds
    assert "review" in kinds
    assert "memory_candidate" in kinds
    assert "memory" in kinds
    assert (
        "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
        "from_source_packet",
        "suggestions/ftir/source-packets/packet.yml",
    ) in edges
    assert (
        "suggestions/ftir/source-packets/packet.yml",
        "from_source_library",
        "source_library:builtin:generic_materials",
    ) in edges
    assert (
        "suggestions/ftir/source-packets/packet.yml",
        "has_reference_seed",
        "reference:ref-trace-001",
    ) in edges
    assert (
        "suggestions/ftir/source-packets/packet.yml",
        "candidate_unresolved_reference",
        "reference:ref-trace-missing",
    ) in edges
    assert (
        "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
        "candidate_uses_reference",
        "reference:ref-trace-001",
    ) in edges
    assert (
        "reviews/review-trace-001.yml",
        "reviews_target",
        "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml",
    ) in edges
    assert (
        "memory/candidates/memcand-trace-001.md",
        "has_review",
        "reviews/review-trace-001.yml",
    ) in edges
    assert (
        "reports/rpt-trace-20260701-001.md",
        "includes_figure",
        "figures/fig-trace-ftir-001.png",
    ) in edges
    assert (
        "memory/candidates/memcand-trace-001.md",
        "has_source",
        "reference:ref-trace-001",
    ) in edges
    reference_node = next(node for node in trace["nodes"] if node["id"] == "reference:ref-trace-001")
    assert reference_node["path"] == "literature/references/ref-trace-001.yml"
    assert reference_node["metadata"]["doi"] == "10.0000/trace"
    assert "Trace views read local EA artifacts" in " ".join(trace["boundaries"])
    assert "EA Trace View" in markdown
    assert "suggestion-20260701-001" in markdown
    assert "ref-trace-001" in markdown


def test_public_xps_example_trace_links_source_backed_references(tmp_path: Path) -> None:
    root = Path("examples/public-xps-be-project")

    result = build_project_trace_view(
        root,
        output_path=tmp_path / "public_xps_trace.yml",
        markdown_output_path=tmp_path / "public_xps_trace.md",
        created_at="2026-07-01T17:00:00",
    )
    trace = read_yaml(Path(result["trace_path"]))
    node_ids = {node["id"] for node in trace["nodes"]}
    edges = {(edge["from"], edge["relation"], edge["to"]) for edge in trace["edges"]}
    nodes = {node["id"]: node for node in trace["nodes"]}

    assert result["status"] == "complete"
    assert "source_library:builtin:generic_xps_parameters" in node_ids
    assert "source_library:builtin:oxide_o1s_binding_energy" in node_ids
    assert "reference:builtin-xps-thermo-c" in node_ids
    assert "reference:builtin-xps-thermo-si" in node_ids
    assert "reference:builtin-xps-thermo-o" in node_ids
    assert "reference:builtin-xps-cardiff-o1s-reference" in node_ids
    assert "reference:builtin-xps-o1s-oxygen-vacancy-critical-2025" in node_ids
    assert nodes["reference:builtin-xps-thermo-c"]["path"] == "literature/references/builtin-xps-thermo-c.yml"
    assert "thermofisher.com" in nodes["reference:builtin-xps-thermo-c"]["metadata"]["url"]
    assert nodes["reference:builtin-xps-thermo-o"]["path"] == "literature/references/builtin-xps-thermo-o.yml"
    assert "thermofisher.com" in nodes["reference:builtin-xps-thermo-o"]["metadata"]["url"]
    assert (
        "suggestions/xps/source-packets/xps_binding_energy_candidates.yml",
        "from_source_library",
        "source_library:builtin:generic_xps_parameters",
    ) in edges
    assert (
        "suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml",
        "from_source_library",
        "source_library:builtin:oxide_o1s_binding_energy",
    ) in edges
    assert (
        "suggestions/xps/source-packets/xps_binding_energy_candidates.yml",
        "has_reference_seed",
        "reference:builtin-xps-thermo-c",
    ) in edges
    assert (
        "suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml",
        "has_reference_seed",
        "reference:builtin-xps-thermo-o",
    ) in edges
    assert (
        "suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml",
        "candidate_uses_reference",
        "reference:builtin-xps-thermo-c",
    ) in edges
    assert (
        "suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml",
        "candidate_uses_reference",
        "reference:builtin-xps-thermo-o",
    ) in edges
    assert (
        "reports/rpt-public-xps-be-example-20260603-001.md",
        "cites_reference",
        "reference:builtin-xps-thermo-c",
    ) in edges
    assert (
        "reports/rpt-public-xps-be-example-20260603-001.md",
        "cites_reference",
        "reference:builtin-xps-thermo-o",
    ) in edges
    assert (
        "memory/candidates/memcand-20260603-001.md",
        "has_source",
        "reference:builtin-xps-thermo-c",
    ) in edges
    assert (
        "memory/candidates/memcand-20260603-003.md",
        "has_source",
        "reference:builtin-xps-thermo-o",
    ) in edges
    assert (
        "reviews/review-20260603-006.yml",
        "reviews_target",
        "suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml",
    ) in edges


def test_cli_trace_view_supports_focus_refs(tmp_path: Path, capsys) -> None:
    _write_trace_fixture(tmp_path)

    assert (
        main(
            [
                "trace",
                "view",
                str(tmp_path),
                "--focus",
                "review-trace-001",
                "--output",
                "traceability/focused_trace.yml",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    trace = read_yaml(tmp_path / "traceability" / "focused_trace.yml")
    node_ids = {node["id"] for node in trace["nodes"]}

    assert output["trace_ref"] == "traceability/focused_trace.yml"
    assert output["markdown_ref"] == "traceability/focused_trace.md"
    assert output["canonical_focus_ref"] == "reviews/review-trace-001.yml"
    assert "reviews/review-trace-001.yml" in node_ids
    assert "suggestions/ftir/suggestion-20260701-001/ftir_assignment_suggestions.yml" in node_ids
    assert "reports/rpt-trace-20260701-001.md" in node_ids


def test_traceability_docs_and_registry_are_discoverable() -> None:
    root = Path.cwd()
    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    onboarding = (root / "docs" / "PUBLIC_ONBOARDING.md").read_text(encoding="utf-8")
    registry = read_yaml(root / "skill-registry" / "index.yml")
    manifest = read_yaml(root / "skill-registry" / "builtins" / "project-traceability.yml")["ea_skill"]

    assert "ea trace view" in readme
    assert "traceability/project_trace.yml" in readme
    assert "registered references, reference seeds, built-in/source-library refs" in readme
    assert "build report-memory traceability views" in skill
    assert "ea trace view" in skill
    assert "registered references, reference seeds, built-in/source-library refs" in skill
    assert "ea trace view" in onboarding
    assert "registered references, reference seeds, built-in/source-library refs" in onboarding
    trace_record = next(item for item in registry["skills"] if item["id"] == "ea.project-traceability")
    assert "Project traceability view implemented" in trace_record["notes"]
    assert "reference seeds" in trace_record["notes"]
    assert "traceability_view" in manifest["output_artifacts"]
    assert "traceability_markdown" in manifest["output_artifacts"]
    assert "literature_reference_index" in manifest["input_artifacts"]
    assert "project_trace_view_yaml_and_markdown" in manifest["current_v0_2_support"]["implemented"]
    assert "registered_reference_and_reference_seed_edges" in manifest["current_v0_2_support"]["implemented"]
    assert "source_library_reference_edges" in manifest["current_v0_2_support"]["implemented"]
    assert "no_memory_commit" in manifest["current_v0_2_support"]["boundaries"]
