# Verified phase checklist

- [x] 1 Audit: 406 baseline tests passed; file-by-file plan written/reviewed.
- [x] 2 Legacy isolation: 92 tracked moves; 406 tests passed in 141.33s; Ruff passed.
- [x] 3 Config/state/resume: 100 affected tests, Ruff and full .venv smoke passed.
- [x] 4 Selection/QC: 114 selection tests; 45 QC/batch/production; 44 render/API regressions; 57 config/transcription/bounded-download tests passed; final full-suite regression also passed.
- [x] 5 SQLite migrations/repositories: 62 order/batch/production tests and 32 focused persistence/resume checks passed; smoke and Ruff passed.
- [x] 6 Campaigns: structured/prose parsing, persisted rules, source/content/destination/deadline gates; 23 focused tests, Ruff and smoke passed.
- [x] 7 Manual/mock publishing: campaign/hash/idempotency gates passed; official uploads unavailable. Full smoke, 19 focused tests and Ruff passed.
- [x] 8 Imported performance, experiments, bounded feedback wired to selection: 48 batch/production/sections and 102 scoring/analytics checks passed; Ruff passed.
- [x] 9 Business tests, CLI/API and smoke: analytics aggregation/validation, render outcomes, calendar-span rates, order-linked reward/hour, canonical dispatch, and cached-runtime recovery covered. Full supported suite: 552 passed, 1 skipped; Ruff and in-repo smoke passed.
- [x] 10 Documentation and final verification: architecture, pipeline, configuration, legacy, audit, README and plan describe the supported runtime and limits. Wheel built and passed import plus API/worker smoke from outside the checkout; `git diff --check` and supported-tree secret-pattern scan found no issues.
