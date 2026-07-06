# EA v0.9.5 Onboarding Workflow

Use this reference after installing, updating, or downloading the skill.

## Post-Install Flow

```bash
ea version
ea codex install-skill
ea onboarding post-install --event install --lang zh
ea install-check
```

For an update, use:

```bash
ea onboarding post-install --event update --lang zh
```

The onboarding message should identify Experimental Assistant v0.9.5, mention the internal compatibility id `ea-v0-2`, and remind the user to restart Codex after skill installation or replacement.

## Downloaded Instructions Sync

Every EA version update must update:

- `skills/ea-v0-2/SKILL.md`
- `skills/ea-v0-2/agents/openai.yaml`
- `docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md`
- `docs/PUBLIC_ONBOARDING.md`
- `docs/RELEASE_VERIFICATION.md`
- release manifest/package/checklist defaults

Run before release:

```bash
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
```

These checks ensure downloaded instructions name the current public version and include the current onboarding, literature preflight, working-memory, estimate, and review-promotion commands.

## Literature Setup Preflight

Before literature acquisition or a Zotero/browser handoff, run:

```bash
ea literature setup-preflight /path/to/ea-project --lang zh
```

This writes `literature/setup_preflight.yml` unless `--no-write` is used. It groups status into automatically satisfied items, user-required items, and items that cannot be configured automatically. It must not launch Zotero, open a browser, inspect credentials, download PDFs, or use institution access.
