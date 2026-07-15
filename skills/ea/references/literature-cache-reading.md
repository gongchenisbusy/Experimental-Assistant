# Literature Cache and Targeted Reading

Use this reference for local, permission-safe full-text caches and evidence retrieval.

Cache objects are addressed by PDF SHA-256. Project and Zotero manifests may point to one shared object; legacy item-key aliases remain readable. Freshness depends on PDF hash, extractor version, and schema version.

Build/search a local SQLite FTS5 index when available. Begin targeted reading with roughly three chunks of about 1,200 characters. Expand automatically when evidence is weak, conflicting, lacks a page anchor, or has low extraction quality. Stop only when the evidence requirement is satisfied or the complete searchable text has been examined.

Never translate “not found in the first chunks” into “not present in the paper.” Record the searched scope. Multi-column, scanned, rotated, formula-heavy, table-heavy, or incomplete documents must expose a quality state and an OCR/original-page fallback rather than silently dropping content.

Keep restricted full text local. Downstream records use citation metadata, hashes, page/chunk anchors, short permitted excerpts, and review state.
