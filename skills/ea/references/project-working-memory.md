# EA Project Working Memory

Use this reference when resuming long project work or after meaningful project changes.

## Purpose

`memory/project-working-memory.md` is a compact, rewrite-in-place continuity file. It helps future agents recover current project state after context compaction or long pauses without loading raw data, full reports, or every provenance file.

It does not replace review-gated scientific memory. Scientific findings still flow through memory candidates, review, and commit.

## Commands

Create or refresh:

```bash
ea memory refresh-project /path/to/ea-project
ea memory refresh-project /path/to/ea-project --max-items 8
```

Read compactly:

```bash
ea memory show-project /path/to/ea-project
ea memory show-project /path/to/ea-project --full
```

The file is also created as a skeleton during `ea init-project`.

## What To Store

Store compact pointers:

- project id, material system, stage, and update time
- latest open-items refs
- latest report refs and report ids
- pending memory candidates and committed memory refs
- next actions that help a future agent continue

Do not paste full raw data, long report bodies, full literature tables, secrets, credentials, or private browser/Zotero paths.
