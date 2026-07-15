# Literature Zotero and Browser Handoff

Use this reference when preparing or checking the optional `zotero-codex-literature` companion.

```bash
ea literature handoff /path/to/project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/project
ea literature institution-access-guide /path/to/project --institution-name "Institution" --access-method library_proxy
ea literature zotero-bridge /path/to/project --zotero-config /user/supplied/config.json --project-collection "Project"
ea literature zotero-readiness /path/to/project
```

Readiness reports app availability, data-library presence, API/connector state, protocol compatibility, current-task blockers, and a degraded no-Zotero path. It must not enumerate private items, attachments, tags, credentials, sessions, or browser profiles.

The companion owns Zotero/browser/institution execution. EA owns targets, review/provenance, imported status, reconciliation, and the user-facing summary. Parent + PDF child is one logical transaction: verify the attachment before success; otherwise report partial or rollback. Re-running the same targets must reuse verified records.
