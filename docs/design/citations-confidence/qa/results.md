# QA results: citations-confidence

STATUS: run by the lead in the main session: 330 passed (tests/unit/core and tests/unit/test_adr_0008_status.py, `PYTHONPATH` not needed, main-checkout venv `python -m pytest`). The test-engineer hook blocked the runner, so its table was filled by the lead.

Test files:
- /home/yevhend/claude-projects/law_by_ai/.claude/worktrees/priceless-nash-6a3201/tests/unit/core/test_citations.py
- /home/yevhend/claude-projects/law_by_ai/.claude/worktrees/priceless-nash-6a3201/tests/unit/test_adr_0008_status.py
- existing: tests/unit/core/test_notices.py

| Case | Status | Test | Reason |
|------|--------|------|--------|
| QA-001 to QA-005 | pass | test_qa_001 .. test_qa_005 (test_citations.py) | passes in the lead run |
| QA-006 | pass | test_qa_006_adr_0008_accepted (test_adr_0008_status.py) | passes in the lead run |
| QA-007 to QA-044 | pass | test_qa_007 .. test_qa_044 (core file, one per id) | passes in the lead run |
| QA-045 | pass | ruff check, ruff format --check, pyright 0 errors, `--cov=core.citations --cov-fail-under=100` run by the lead | mypy not used (project uses pyright); bandit and pip-audit run in CI |
| QA-046 | pass | test_qa_046_large_hit_list | passes in the lead run |
| QA-047 | pass | test_qa_047_hit_sets_pass_validity | passes in the lead run |
| QA-048 | pass | test_qa_048_weights_provisional (test_adr_0008_status.py) | passes in the lead run |
| QA-049 | pass | test_qa_049_notice_on_refusal_with_source | passes in the lead run |

Notes from reading src/core/citations.py (static, unexecuted): the module logic matches cases 1-44 and 47; no product bug seen. QA-006 checks the exact ADR phrases "0.4 and 0.6 are provisional" and "Persistence is deferred", which exist in docs/adr/0008-mvp-scope.md. The ADR index is docs/adr/index.md (row says Accepted).
