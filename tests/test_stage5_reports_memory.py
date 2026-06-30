from pathlib import Path

import pytest

from ea.cli import main
from ea.memory import (
    MemoryBoundaryError,
    commit_memory_candidate,
    propose_memory_candidate,
    record_suggestion,
    review_memory_candidate,
    update_suggestion_status,
    write_confirmed_finding,
    write_decision_log_entry,
    write_open_item,
    write_progress_event,
)
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.reports import generate_raman_report
from ea.storage import read_markdown_record, read_yaml


PUBLIC_RAW = Path("tests/fixtures/public/test-case-001/raw_data")


def _raman_result(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-3(1).txt",
        project_id="project-20260602-mos2",
        sample_refs=["20260516-run1-sub1"],
        imported_at="2026-06-02T16:00:00",
    )
    column_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        project,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    result = process_raman_result(
        project,
        characterization_metadata_path=raw.metadata_path,
        project_id="project-20260602-mos2",
        sample_refs=["20260516-run1-sub1"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-02T16:05:00",
    )
    return project, result


def test_raman_report_is_chinese_cautious_and_has_no_next_step_suggestions(tmp_path: Path) -> None:
    project, result = _raman_result(tmp_path)

    report_path = generate_raman_report(
        project,
        project_id="project-20260602-mos2",
        raman_metadata_path=result,
        related_experiments=["exp-20260516-001"],
        related_samples=["20260516-run1-sub1"],
        created_at="2026-06-02T16:10:00",
    )
    frontmatter, body = read_markdown_record(report_path)

    assert frontmatter["report_type"] == "raman_analysis"
    assert frontmatter["language"] == "zh"
    assert frontmatter["include_next_step_suggestions"] is False
    assert frontmatter["status"] == "draft"
    assert frontmatter["provenance_refs"]
    assert "Raman 分析报告" in body
    assert "谨慎解释" in body
    assert "下一步建议" not in body
    for forbidden in ["证明了", "毫无疑问", "机制已经确定"]:
        assert forbidden not in body


def test_suggestion_acceptance_does_not_create_decision_log(tmp_path: Path) -> None:
    suggestion = record_suggestion(
        tmp_path,
        project_id="project-20260602-mos2",
        trigger="user asked what to do next",
        suggestion_text="可以考虑补充 AFM，但这只是建议草稿。",
        related_records=["report-20260602-001"],
        source_refs=["report-20260602-001"],
    )
    update_suggestion_status(suggestion, status="accepted", user_response="这个建议可以")

    frontmatter, _ = read_markdown_record(suggestion)
    assert frontmatter["status"] == "accepted"
    assert not (tmp_path / "memory" / "decision-log.md").exists()

    with pytest.raises(MemoryBoundaryError):
        write_progress_event(
            tmp_path,
            user_original_text="EA 建议可以做 AFM",
            ea_summary="Do AFM",
            event_type="analysis",
            source_kind="suggestion",
            source_refs=[suggestion.name],
        )


def test_explicit_user_decision_and_confirmed_finding_are_separate(tmp_path: Path) -> None:
    with pytest.raises(MemoryBoundaryError):
        write_decision_log_entry(
            tmp_path,
            user_original_text="这个建议可以",
            ea_summary="User accepted a suggestion",
        )

    decision_review = write_review_record(
        tmp_path,
        target_type="decision_log_entry",
        target_ref="memory/decision-log.md",
        user_response="可以，保存",
        reviewed_content="continue multiple CVD runs",
    )
    decision_log = write_decision_log_entry(
        tmp_path,
        user_original_text="我下一步计划用这个标准条件继续多烧几炉。",
        ea_summary="Continue multiple CVD runs using the confirmed standard condition.",
        related_suggestion_ref="suggestion-20260602-001",
        source_refs=["exp-20260516-001"],
        review_refs=[decision_review.stem],
        decided_at="2026-06-02T16:20:00",
    )
    assert "decision-" in decision_log.read_text(encoding="utf-8")

    with pytest.raises(MemoryBoundaryError):
        write_confirmed_finding(
            tmp_path,
            finding_text="Raman result confirms monolayer MoS2.",
            source_refs=["report-20260602-001"],
            user_response="可能吧",
            reviewed_content="finding draft",
            provenance_refs=["prov-20260602-001"],
            finding_type="hypothesis",
        )

    finding_path = write_confirmed_finding(
        tmp_path,
        finding_text="用户确认该 Raman 结果可作为当前样品分析记录的一部分，但层数结论仍需结合更多表征。",
        source_refs=["report-20260602-001"],
        user_response="可以，保存",
        reviewed_content="finding draft",
        provenance_refs=["prov-20260602-001"],
        reviewed_at="2026-06-02T16:25:00",
    )
    assert "Confirmed Finding" in finding_path.read_text(encoding="utf-8")
    assert list((tmp_path / "provenance").glob("*.yml"))


def test_open_items_are_tracked_without_becoming_confirmed_memory(tmp_path: Path) -> None:
    open_item = write_open_item(
        tmp_path,
        item_type="missing_metadata",
        description="Raman laser power is missing and should be confirmed by user.",
        related_records=["char-20260602-001"],
        priority="high",
        source_refs=["char-20260602-001"],
    )
    data = read_yaml(open_item)

    assert data["status"] == "open"
    assert data["priority"] == "high"
    assert not (tmp_path / "memory" / "confirmed-findings.md").exists()


def test_memory_candidate_requires_review_before_commit(tmp_path: Path) -> None:
    source = tmp_path / "reports" / "source-report.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("source report", encoding="utf-8")

    candidate = propose_memory_candidate(
        tmp_path,
        project_id="project-20260602-mos2",
        candidate_text="Raman peak separation may be consistent with a thin MoS2 region, pending supporting evidence.",
        source_refs=["reports/source-report.md"],
        provenance_refs=["prov-20260602-001"],
        category="interpretation",
        confidence="medium",
        rationale="Candidate extracted from report interpretation.",
        created_at="2026-06-02T17:00:00",
    )
    frontmatter, body = read_markdown_record(candidate)
    candidate_index = read_yaml(tmp_path / "memory" / "candidates" / "index.yml")

    assert frontmatter["status"] == "draft"
    assert frontmatter["memory_candidate_id"] == "memcand-20260602-001"
    assert "thin MoS2" in body
    assert candidate_index["candidates"][frontmatter["memory_candidate_id"]]["status"] == "draft"

    with pytest.raises(MemoryBoundaryError, match="user_confirmed"):
        commit_memory_candidate(tmp_path, candidate_path=candidate)

    review_memory_candidate(
        tmp_path,
        candidate_path=candidate,
        user_response="可能吧，先别保存",
        reviewed_at="2026-06-02T17:05:00",
    )
    frontmatter, _ = read_markdown_record(candidate)
    assert frontmatter["status"] == "deferred"

    with pytest.raises(MemoryBoundaryError, match="user_confirmed"):
        commit_memory_candidate(tmp_path, candidate_path=candidate)

    review_memory_candidate(
        tmp_path,
        candidate_path=candidate,
        user_response="可以，保存",
        reviewed_content="confirmed memory candidate",
        reviewed_at="2026-06-02T17:10:00",
    )
    frontmatter, _ = read_markdown_record(candidate)
    assert frontmatter["status"] == "user_confirmed"
    assert len(frontmatter["review_refs"]) == 2

    memory_path = commit_memory_candidate(
        tmp_path,
        candidate_path=candidate,
        review_ref=frontmatter["review_refs"][-1],
        committed_at="2026-06-02T17:15:00",
    )
    committed_frontmatter, _ = read_markdown_record(candidate)
    memory_index = read_yaml(tmp_path / "memory" / "index.yml")

    assert memory_path == tmp_path / "memory" / "confirmed-findings.md"
    assert "Memory mem-20260602-001" in memory_path.read_text(encoding="utf-8")
    assert committed_frontmatter["status"] == "committed"
    assert committed_frontmatter["committed_memory_id"] == "mem-20260602-001"
    assert memory_index["memories"]["mem-20260602-001"]["candidate_ref"].endswith("memcand-20260602-001.md")


def test_hypothesis_candidate_commits_to_hypotheses(tmp_path: Path) -> None:
    source = tmp_path / "reports" / "image-report.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("image source", encoding="utf-8")
    candidate = propose_memory_candidate(
        tmp_path,
        project_id="project-20260602-mos2",
        candidate_text="Image contrast may indicate local topography variation.",
        source_refs=["reports/image-report.md"],
        provenance_refs=["prov-20260602-002"],
        category="hypothesis",
        confidence="low",
    )
    review_memory_candidate(tmp_path, candidate_path=candidate, user_response="可以，保存")
    frontmatter, _ = read_markdown_record(candidate)
    memory_path = commit_memory_candidate(tmp_path, candidate_path=candidate, review_ref=frontmatter["review_refs"][-1])

    assert memory_path == tmp_path / "memory" / "hypotheses.md"
    assert "category: hypothesis" in memory_path.read_text(encoding="utf-8")


def test_memory_candidate_cli_roundtrip(tmp_path: Path, capsys) -> None:
    source = tmp_path / "reports" / "cli-source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("cli source", encoding="utf-8")

    assert main(
        [
            "memory",
            "propose",
            str(tmp_path),
            "--project-id",
            "project-20260602-mos2",
            "--text",
            "CLI candidate memory text.",
            "--source-ref",
            "reports/cli-source.md",
            "--provenance-ref",
            "prov-cli-001",
            "--category",
            "finding",
            "--confidence",
            "high",
        ]
    ) == 0
    propose_output = capsys.readouterr().out
    assert "memcand-" in propose_output
    candidate = next((tmp_path / "memory" / "candidates").glob("memcand-*.md"))

    assert main(
        [
            "memory",
            "review",
            str(tmp_path),
            "--candidate",
            candidate.relative_to(tmp_path).as_posix(),
            "--user-response",
            "可以，保存",
        ]
    ) == 0
    review_output = capsys.readouterr().out
    assert "memcand-" in review_output
    frontmatter, _ = read_markdown_record(candidate)

    assert main(
        [
            "memory",
            "commit",
            str(tmp_path),
            "--candidate",
            candidate.relative_to(tmp_path).as_posix(),
            "--review-ref",
            frontmatter["review_refs"][-1],
        ]
    ) == 0
    commit_output = capsys.readouterr().out
    assert "confirmed-findings.md" in commit_output
