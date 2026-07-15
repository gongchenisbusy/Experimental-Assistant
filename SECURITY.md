# Security Policy

## Supported Versions

Security fixes are provided for the latest public release. During the v0.9.8 release-candidate period, v0.9.7 remains the stable fallback.

## Reporting A Vulnerability

Do not open a public issue for credentials, arbitrary code execution, data loss, path traversal, unsafe archive handling, or private research-data exposure.

Email `ea_feedback@163.com` with:

- affected version and operating system;
- a minimal reproduction without private research data;
- expected and observed behavior;
- potential impact;
- whether the report may be acknowledged publicly.

Never include API keys, passwords, cookies, browser profiles, Zotero secrets, institution sessions, private full text, or raw experimental data.

The maintainer will acknowledge the report, assess severity, coordinate a fix and disclosure, and credit the reporter when permission is given.

## Security Boundaries

EA is local-first. Zotero, browser assistance, institution login, downloads, diagnostics submission, and feedback submission remain opt-in. EA must not bypass paywalls, CAPTCHA, MFA, SSO, or publisher access controls.
