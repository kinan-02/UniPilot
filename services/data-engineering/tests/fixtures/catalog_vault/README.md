# Minimal catalog vault wiki (CI)

Trimmed Obsidian wiki subset for deterministic vault export tests without the full
`data/catalog_valut/` tree.

Structure mirrors production vault layout:

```
wiki/
  entities/   — three DDS track pages
  courses/    — one sample course page for title enrichment
```

Used by `tests/test_vault_export_ci_fixture.py`.
