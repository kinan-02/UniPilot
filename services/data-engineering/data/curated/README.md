# Curated Technion DDS catalog (Phase 7.5)

Human-reviewable curated outputs produced from the parser draft plus course offering JSON references.

| File | Description |
|------|-------------|
| `technion/dds_catalog/dds_catalog_curated_reviewed.json` | Cursor-assisted reviewed catalog (not production data) |
| `technion/dds_catalog/dds_catalog_curated_review_report.md` | Curation report and remaining manual tasks |

Generate with:

```bash
python -m app.main curate-dds-catalog
```

No MongoDB or staging writes occur in this phase.
