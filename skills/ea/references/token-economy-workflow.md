# EA v0.9.7 Large-Work Gate

Use this reference when a task may create substantial agent context, long reports, broad literature results, or large acquisition handoffs.

## Threshold

EA v0.9.7 uses a fixed large-work threshold of `100` Codex-credit-equivalent units. This follows the approved planning estimate of about 20% of a practical Plus/GPT-5.5 five-hour working window. Do not expose this as a normal user setting.

## Estimate Before Expensive Work

```bash
ea estimate workflow /path/to/ea-project --workflow literature_acquisition --items 50 --mode standard
ea estimate workflow /path/to/ea-project --workflow analysis_report --items 1 --mode full
```

If the result status is `needs_confirmation`, summarize the expected workflow and ask the user whether to continue.

Literature commands that support inline gating:

```bash
ea literature search-public /path/to/ea-project --source crossref --source openalex --max-results 20 --confirm-large-work
ea literature acquisition-request /path/to/ea-project --confirm-large-work
ea literature prepare-source-candidates /path/to/ea-project --method ftir --source-items literature/selected_items.yml --confirm-large-work
```

## User Opt-Out

If a user explicitly says they do not want large-work reminders, record the preference:

```bash
ea estimate reminders /path/to/ea-project --disable --reason "user requested no large-work reminders"
```

Re-enable if requested:

```bash
ea estimate reminders /path/to/ea-project --enable
```

This preference only suppresses the extra large-work reminder. It does not bypass safety, permission, scientific review, or raw-data protection gates.

## Context Economy Rules

Prefer local files and concise summaries over pasting full reports, PDFs, candidate lists, or raw data into the conversation. Read only the reference file needed for the current workflow. Use `ea brief project`, `ea trace lookup`, and `memory/project-working-memory.md` before loading broad project directories.
