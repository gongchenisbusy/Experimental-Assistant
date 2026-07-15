# Literature OA Acquisition

Use this reference only after metadata targets and acquisition scope are confirmed.

EA core may plan and reconcile acquisition. A compatible literature companion performs public OA resolution, retrieval, browser/Zotero work, and returns protocol-v2 status. Keep no-Zotero and user-supplied PDF/BibTeX/RIS paths available.

For each target: normalize DOI/title/version; resolve a lawful OA candidate; validate HTTP status, MIME, `%PDF-` header, size, page count, and SHA-256; record created/reused/partial/rolled-back state; then update the local content-addressed cache manifest. One failed optional resolver must not disable metadata or local-PDF paths.

Pause on login, CAPTCHA, access denial, license uncertainty, or missing authorization. Save compact resumable state and ask once for the next user action. Never inspect credentials, cookies, tokens, private Zotero tags, or unrestricted browser history.

Retries must be idempotent: no duplicate parent item, PDF attachment, cache object, or EA reference. Preserve failure codes and diagnostics refs on disk.
