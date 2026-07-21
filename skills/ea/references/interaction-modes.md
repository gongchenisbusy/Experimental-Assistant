# EA Interaction Modes

Use this reference when deciding whether to ask, record, or execute.

## Consult Mode

Default mode for unclear requests, project orientation, literature planning, parameter discussion, and report review. Read existing project state and answer with the smallest set of next decisions that changes behavior.

Question style:

```text
需要你补充：
1. ...
2. ...
```

Ask no more than the next necessary decisions. Do not ask for credentials, hidden local paths, or broad preferences unless the current workflow needs them.

Use `ea --mode consult <read-only-command>`. The CLI rejects commands that can write before entering their workflow.

Method `inspect`, assignment/source-library `list`, compact experiment `runs`, and literature `acquisition-status` commands are read-only and valid in consult/audit. Their neighboring import/process/record/session commands remain state-changing.

## Record Mode

Use when the user asks EA to create/update project files, register references, write ReviewRecords, write memory candidates, refresh `memory/project-working-memory.md`, or prepare literature/source-candidate staging files. Record mode may write local files but should preserve raw data and provenance boundaries.

Use `ea --mode record <command>`. Analysis processing, plotting, reports, exports, package lifecycle, and acquisition execution remain blocked.

## Execute Mode

Use for data processing, batch runs, public metadata search, literature acquisition handoff, report generation, release package creation, and other commands with side effects or substantial output. Confirm review gates, permission gates, and large-work gates before execution.

Use `ea --mode execute <command>` or the default command mode.

## Audit Mode

Use `ea --mode audit <read-only-command>` for health, no-write evaluation/brief, migration plan/status, diagnostics preview, release evidence inspection, `references validate-report`, `export verify-bundle`, and `export verify-archive`. Like consult, audit rejects writes, including neighboring `references` and `export` subcommands that create or change artifacts.

```bash
ea --mode audit references validate-report /path/to/project reports/REPORT.md
ea --mode audit export verify-bundle /path/to/report-bundle
ea --mode audit export verify-archive /path/to/report-bundle.zip
```

Mode-policy refusal returns `EA-MODE-COMMAND-BLOCKED`. It is distinct from `EA-IO-PERMISSION-DENIED`, which means the operating system or sandbox denied access.

## Review Confirmation

Use `ea review add --confirm` only when the user explicitly confirms a parameter, field, or suggestion target. Do not use it to turn memory candidates or confirmed findings into durable facts. Use `ea review promote` when a prior advisory review needs explicit user promotion before reuse.
