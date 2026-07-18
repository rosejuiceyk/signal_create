# Archived Web and ML routes

This directory preserves the retired Phase 3.5 Web and Phase 5/6 machine-learning work for audit
history. It is not part of the installed `he3sim` package, the active CLI, or the active test suite.
Ruff also excludes it because archived modules retain their original package imports and are not
expected to run from this location.

Mappings:

- `src_app/`: former `src/he3sim/app/`;
- `src_ml/`: former `src/he3sim/ml/`;
- `tests/`: Web/ML-only tests;
- `configs/`: Web/ML configuration history;
- `docs_phases/`: retired Phase 3.5/5/6/6S stage documents;
- `docs/`: superseded Web/ML-oriented planning documents;
- `web_tools/`: scripts coupled to the retired Web backend.

Do not import archived modules from active code. Any future work must follow `docs/ROADMAP_v2.md`
through a separately approved stage.
