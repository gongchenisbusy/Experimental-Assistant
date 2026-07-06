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

## Record Mode

Use when the user asks EA to create/update project files, register references, write ReviewRecords, write memory candidates, refresh `memory/project-working-memory.md`, or prepare literature/source-candidate staging files. Record mode may write local files but should preserve raw data and provenance boundaries.

## Execute Mode

Use for data processing, batch runs, public metadata search, literature acquisition handoff, report generation, release package creation, and other commands with side effects or substantial output. Confirm review gates, permission gates, and large-work gates before execution.

## Review Confirmation

Use `ea review add --confirm` only when the user explicitly confirms a parameter, field, or suggestion target. Do not use it to turn memory candidates or confirmed findings into durable facts. Use `ea review promote` when a prior advisory review needs explicit user promotion before reuse.
