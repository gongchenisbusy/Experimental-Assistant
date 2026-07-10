---
name: ea-v0-2
description: Compatibility entry point for Experimental Assistant v0.9.7. Use only when an existing task or installation still invokes $ea-v0-2; route all work to the installed $ea skill while preserving historical project identifiers.
---

# Experimental Assistant Compatibility Entry

`$ea-v0-2` is a temporary compatibility invocation, not a product version.

1. Tell the user that the stable public invocation is `$ea`.
2. Load and follow the sibling `ea/SKILL.md` as the authoritative workflow.
3. Do not rewrite historical project, provenance, package, or report identifiers.
4. If the sibling skill is missing, run `ea doctor` and recommend `ea setup` or `ea codex install-skill`.
5. Keep this compatibility entry available through the v1.0.x release line.
