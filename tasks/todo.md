# Verified phase checklist

- [x] 1 Audit: 406 baseline tests passed; file-by-file plan written/reviewed.
- [x] 2 Legacy isolation: 92 tracked moves; 406 tests passed in 141.33s; Ruff passed.
- [x] 3 Config/state/resume: 100 affected tests, Ruff and full .venv smoke passed.
- [x] 4 Selection/QC: 114 selection tests; 45 QC/batch/production; 44 render/API regressions; 57 config/transcription/bounded-download tests passed. Full-suite follow-up remains in final verification.
- [x] 5 SQLite migrations/repositories: 62 order/batch/production tests and 32 focused persistence/resume checks passed; smoke and Ruff passed.
- [x] 6 Campaigns: structured/prose parsing, persisted rules, source/content/destination/deadline gates; 23 focused tests, Ruff and smoke passed.
- [ ] 7 Manual/mock publishing.
- [ ] 8 Performance, experiments, feedback.
- [ ] 9 Business tests, CLI/API and smoke.
- [ ] 10 Documentation and final verification.
