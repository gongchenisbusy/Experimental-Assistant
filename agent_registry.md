# EA v0.1 Agent Registry

## Policy

- Default sub-agent mode: `fork_context: false`.
- Hidden truth and evaluator-only files are forbidden for all build agents.
- Each worker gets a disjoint write scope.
- Completed agents should be closed after their output is integrated.

## Agents

| Agent ID | Nickname | Role | Task | Fork Context | Allowed Files | Forbidden Files | Write Scope | Status |
|---|---|---|---|---|---|---|---|---|
| 019e88a0-dc33-7460-9cac-2274d3194936 | Hilbert | Context Librarian | Prepare Stage 1 minimum context package | false | selected P0 specs, architecture map | hidden truth, evaluator-only files | none | closed |
| pending | Architecture & Schema | Core architecture | Implement schema/storage foundations | false | P0 specs, architecture map | hidden truth, evaluator-only files | `src/ea/schema/`, `src/ea/storage/`, tests | planned |
| pending | Review Workflow | Review state machine | Implement confirmation classification and ReviewRecord writing | false | review spec, schema spec, memory spec | hidden truth, evaluator-only files | `src/ea/review/`, tests | planned |
| pending | Experiment Log & Sample | Logs and samples | Implement review-gated experiment/sample workflows | false | schema/review specs, public conversation | hidden truth, evaluator-only files | `src/ea/experiments/`, `src/ea/samples/`, tests | planned |
| pending | Raw Import | Raw data boundary | Implement readonly controlled copy, hash, alias metadata | false | raw import spec, provenance spec, public raw files | hidden truth, evaluator-only files | `src/ea/raw_import/`, tests | planned |
| pending | Raman Pipeline | Raman processing | Implement reader, inspection, confirmation gate, processing, plotting | false | Raman/raw/provenance specs, public raw files | hidden truth, evaluator-only files | `src/ea/raman/`, tests | planned |
| pending | Report & Scientific Language | Reports | Implement cautious Chinese Raman report generation | false | product charter, Raman spec, memory spec | hidden truth, evaluator-only files | `src/ea/reports/`, tests | planned |
| pending | Memory & Provenance | Memory boundaries | Implement provenance, progress, suggestions, decisions, open items, memory writes | false | memory/provenance/review specs | hidden truth, evaluator-only files | `src/ea/memory/`, `src/ea/provenance/`, tests | planned |
| pending | Test Harness | Public tests | Implement public workflow tests without hidden truth | false | public test input, P0 specs | hidden truth, evaluator-only files | `tests/` | planned |
| 019e88b1-a0e5-7781-9243-ab62ee6d9f13 | Aquinas | QA Reviewer | Read-only review for Stage 6 critical EA boundary failures | false | build code, specs, public tests | hidden truth, evaluator-only files | none | closed; pass_with_notes |
