# Memory Workflow

Use this reference when saving durable project memory.

Core rule:

- Do not write analysis, suggestions, hypotheses, or next-step ideas directly into confirmed project memory.
- First create a memory candidate under `memory/candidates/`.
- Record user review as a separate ReviewRecord.
- Commit only candidates with `status: user_confirmed` and a linked user-confirmed review.
- Keep suggestions in `suggestions/`, open questions in `open-items/`, hypotheses in `memory/hypotheses.md`, and confirmed findings or interpretations in `memory/confirmed-findings.md`.

Recommended command shape:

```bash
ea memory propose /path/to/project \
  --text "Candidate finding..." \
  --source-ref reports/rpt-example.md \
  --provenance-ref prov-20260630-001 \
  --category interpretation \
  --confidence medium

ea memory review /path/to/project \
  --candidate memory/candidates/memcand-20260630-001.md \
  --user-response "可以，保存"

ea memory commit /path/to/project \
  --candidate memory/candidates/memcand-20260630-001.md \
  --review-ref review-20260630-001
```

`memory/index.yml` is the lookup table for committed memory. It stores memory ID, category, confidence, candidate ref, source refs, provenance refs, review refs, target file, and commit time.
