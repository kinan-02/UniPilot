# DDS Catalog Signoff Review Report

Generated: 2026-06-19T15:52:38+00:00
Review status: **ready-for-staging-with-review-flags**

> Agent-assisted source verification only — **not** true human approval.

## Review verdict
**ready-for-staging-with-review-flags**

## Files reviewed
- `/Users/tymoribrahim/Desktop/כתיבת תוכנה בלמידת מכונה/UniPilot/services/data-engineering/data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json`
- `/Users/tymoribrahim/Desktop/כתיבת תוכנה בלמידת מכונה/UniPilot/services/data-engineering/data/raw/technion/technion_dds_catalog_from_docx_clean.md`
- `courses_2025_200.json`
- `courses_2025_201.json`
- `courses_2025_202.json`

## What was verified
- Top-level structure: 3 expected program codes present.
- 009216-1-000: totalCredits=155.0 verified.
- 009009-1-000: totalCredits=155.0 verified.
- 009118-1-000: totalCredits=155.0 verified.
- 009216-1-000:enrichment=6.0 credit bucket verified.
- 009216-1-000:free-elective=4.0 credit bucket verified.
- 009216-1-000:physical-education=2.0 credit bucket verified.
- 009216-1-000:core-mandatory=108.0 credit bucket verified.
- 009216-1-000:elective-ds=24.5 credit bucket verified.
- 009216-1-000:elective-faculty=10.5 credit bucket verified.
- 009216-1-000:elective-general=12.0 credit bucket verified.
- 009009-1-000:enrichment=6.0 credit bucket verified.
- 009009-1-000:free-elective=4.0 credit bucket verified.
- 009009-1-000:physical-education=2.0 credit bucket verified.
- 009009-1-000:core-mandatory=103.0 credit bucket verified.
- 009009-1-000:elective-faculty=40.0 credit bucket verified.
- 009009-1-000:elective-general=12.0 credit bucket verified.
- 009118-1-000:enrichment=6.0 credit bucket verified.
- 009118-1-000:free-elective=4.0 credit bucket verified.
- 009118-1-000:physical-education=2.0 credit bucket verified.
- 009118-1-000:core-mandatory=107.5 credit bucket verified.
- 009118-1-000:elective-faculty=35.5 credit bucket verified.
- 009118-1-000:elective-general=12.0 credit bucket verified.
- DS semester-1 includes 02340117 (markdown-supported).
- DS semester-1 includes 03240033 (markdown-supported).
- DS semester-1 includes 00940345 (markdown-supported).
- DS semester-1 includes 01040031 (markdown-supported).
- DS semester-1 includes 01040166 (markdown-supported).
- 009009-1-000:ie-statistics-elective-chain: choose-N/chain encoded as rule, not mandatory list.
- 009009-1-000:ie-behavior-science-chain: choose-N/chain encoded as rule, not mandatory list.
- 009009-1-000:ie-focus-chain: choose-N/chain encoded as rule, not mandatory list.
- 009118-1-000:is-behavior-science-chain: choose-N/chain encoded as rule, not mandatory list.
- 009118-1-000:is-focus-chain-performance: choose-N/chain encoded as rule, not mandatory list.
- 009118-1-000:is-focus-chain-ml: choose-N/chain encoded as rule, not mandatory list.
- 009118-1-000:is-focus-chain-game-theory: choose-N/chain encoded as rule, not mandatory list.
- DS faculty elective pool remains prefix-rule based (no flattened list).
- DS math-analytics track 26-credit rule preserved.
- DS cognition track sourced from markdown.

## Fixes applied during signoff
- Title hints filled: 0
- Credit buckets marked verified where markdown values matched.
- Footnote markers propagated where clearly tied in markdown.

## Counts
- Programs: 3
- Requirement groups: 41
- Course references: 113
- Missing title hints: 11
- Manual review items: 138
- Executable rule groups: 19
- Non-executable rule groups: 22

## Remaining unresolved issues
- 009009-1-000:ie-additional-faculty-electives: could not locate markdown source marker.
- 009118-1-000:is-additional-faculty-electives: could not locate markdown source marker.
- Missing titleHint: 00906292 in 009216-1-000:elective-ds-pool
- Missing titleHint: 00970211 in 009216-1-000:semester-4-matrix
- Missing titleHint: 00970329 in 009216-1-000:cognition-track:requirements
- Missing titleHint: 00980312 in 009216-1-000:semester-4-matrix
- Missing titleHint: 00980455 in 009216-1-000:semester-4-matrix
- Missing titleHint: 01040030 in 009216-1-000:semester-4-matrix
- Missing titleHint: 01340020 in 009216-1-000:elective-ds-pool
- Missing titleHint: 01500411 in 009009-1-000:semester-3-matrix
- Missing titleHint: 01500411 in 009216-1-000:semester-2-matrix
- Missing titleHint: 02300401 in 009216-1-000:semester-2-matrix
- Missing titleHint: 02740300 in 009216-1-000:elective-ds-pool

## IE/IS chain rule assessment
- Choose-N and focus-chain rules remain non-executable `course_pool` groups with `manualReviewRequired: true`.
- No chain courses were flattened into mandatory requirements.

## DS tracks assessment
- Math-analytics 26-credit rule preserved as track requirement note.
- Cognition track remains manual review.
- Faculty elective pool remains prefix-rule based.

## Footnote assessment
- Markers `*`, `**`, `***` propagated only when clearly adjacent to course numbers in markdown.
- `#` / `##` enrichment/free-elective buckets remain at credit-bucket level.

## Phase 8 recommendation
Safe to import to staging with review flags preserved; non-executable chain/track rules require human validation before production use.

## Production promotion recommendation
Do not promote to production until human signoff on chain rules, tracks, and unresolved titles.

## MongoDB / staging
- **No MongoDB writes occurred.**
- **No staging or production collections were modified.**
