# Public Initialization

Use this reference whenever project setup, literature setup, browser access, Zotero, cache paths, or tests are involved.

EA must default to an unknown public user environment. Do not hardcode developer paths, accounts, browser profiles, institution login routes, Zotero collections, local literature cache folders, or test datasets.

For a first-project public-user walkthrough in the repository docs, read `docs/PUBLIC_ONBOARDING.md`.

Ask for or explicitly disable:

- Project root, project name, and project slug.
- Default report language.
- Raw data source directory.
- Whether Zotero is enabled and how to access the user's Zotero Local API.
- Whether a project Zotero collection should be used or created.
- Literature cache root.
- Whether browser-assisted acquisition is allowed.
- Browser name/profile if browser assist is enabled.
- Institution, SSO, VPN, or proxy notes. Never store credentials.
- Literature deployment scope and top N.

Tests may use local fixtures only when the fixture path is explicit and marked as test/demo input.
