# EA v0.1 P0 Spec Mapping

## Implemented Coverage

| P0 Spec | Implementation | Test Coverage |
|---|---|---|
| `EA_SCHEMA_SPEC.md` | `src/ea/schema/models.py`, `src/ea/storage/` | `tests/test_stage1_core.py` |
| `EA_REVIEW_STATE_MACHINE.md` | `src/ea/review/`, review-gated experiment and memory writes | `tests/test_stage1_core.py`, `tests/test_stage2_experiments_samples.py`, `tests/test_stage5_reports_memory.py` |
| `EA_RAW_IMPORT_SPEC.md` | `src/ea/raw_import/` | `tests/test_stage3_raw_import.py`, `tests/test_stage6_public_workflow.py` |
| `EA_RAMAN_V0_1_SPEC.md` | `src/ea/raman/` | `tests/test_stage4_raman.py`, `tests/test_stage6_public_workflow.py` |
| `EA_MEMORY_BOUNDARY_SPEC.md` | `src/ea/memory/`, `src/ea/reports/` | `tests/test_stage5_reports_memory.py`, `tests/test_stage6_public_workflow.py` |
| `EA_PROVENANCE_MINIMUM_SPEC.md` | `src/ea/provenance/` plus workflow calls in project/log/raw/Raman/report/memory services | `tests/test_stage1_core.py`, `tests/test_stage2_experiments_samples.py`, `tests/test_stage3_raw_import.py`, `tests/test_stage4_raman.py`, `tests/test_stage5_reports_memory.py`, `tests/test_stage6_public_workflow.py` |

## Explicit v0.1 Boundaries

- Hidden truth is not required or referenced by tests or implementation.
- Public fixture path is `工作指南/test_cases/test-case-001/public/`.
- PL files are importable as raw files but are rejected by the Raman processing pipeline.
- Reports default to Chinese, draft status, and no next-step suggestions.
- Suggestion acceptance does not create decisions or progress events.
- Confirmed findings require clear user confirmation.
