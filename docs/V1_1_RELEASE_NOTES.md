# Experimental Assistant v1.1.0 Release Notes

Experimental Assistant v1.1.0 is a backward-compatible reliability release driven by public issues #23–#26. It keeps the v1 local-first, review-gated contract while repairing workflow integrity from protected import through HTML delivery.

## Highlights

- Protected raw imports and report bundles now use transaction-safe, idempotent copying. Failed imports roll back newly created artifacts, and repeated protected provenance inputs are reused by source and hash.
- Consult and audit mode decisions now come from centralized command-effect metadata. Read-only method inspection, literature status, and list commands do not require execute mode.
- Reviews have explicit target types and can be checked against target references and content hashes. `draft confirm-promote` gives one clear, idempotent confirmation-and-promotion path.
- Raman/PL preview is method-aware; normalized PL results remain visible beside separately scaled raw counts.
- Direct experiment-run and sample commands, selected-sample state, method coverage, and stage-aware next actions are available in working memory.
- `composite-report` builds one reviewed multi-method report with provenance and multi-report figure backlinks, then exports HTML. Draft HTML preview is visibly non-formal and cannot mutate the formal report index.
- Literature acquisition now preserves an exact confirmed target set in `literature/run.yml`, resumes by target, reconciles all count-bearing files, and rejects invalid or metadata-mismatched PDFs. Zotero is an explicit existing/skip/later choice; verified local PDFs work without Zotero.

## Upgrade

```bash
ea update --release-ref v1.1.0
ea codex install-skill
ea doctor
ea install-check
```

Restart Codex after replacing the `$ea` Skill. Existing v1.0 project format remains supported; v1.1 does not rewrite historical project records merely to change their recorded producer version.

## Compatibility and boundaries

- Python 3.11–3.13 remain supported.
- `$ea` remains the only public Skill invocation.
- The optional EA-feedback compatibility pin is recorded in `skill-registry/companion-compatibility.yml`.
- Browser, institution, Zotero, downloads, diagnostics submission, and feedback submission remain user-authorized actions.
- Optional reviewed PL local peak fitting is not part of v1.1 and is tracked in public issue #27.

See `docs/V1_1_COMMAND_CONTRACT.md`, `docs/V1_1_KNOWN_LIMITATIONS.md`, and `docs/V1_1_ISSUE_DISPOSITION.md` for the exact surface and disposition.
