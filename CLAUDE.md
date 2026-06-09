# Movie Conceptualizer — project conventions

AI filmmaking pipeline: Fountain/FDX/PDF screenplay → scene analysis → shot
list → storyboard prompts, via CLI (`moviecon`) and a FastAPI service.

## Commands

```bash
pip install -e ".[dev,jobs,redis,postgresql]"   # full dev install
pytest -q                                        # run tests
ruff check src tests scripts                     # lint
ruff format --check src tests scripts            # formatting gate
mypy src                                         # strict, whole tree
```

CI (`.github/workflows/ci.yml`) gates on exactly those four commands on
Python 3.11 and 3.12. All four must be clean before any push.

## Non-obvious constraints

- **ruff is pinned** (`ruff==0.9.10` in the dev extra) to match the
  `ruff-pre-commit` rev in `.pre-commit-config.yaml`. The org `precommit`
  workflow runs that hook over the whole repo, including `scripts/`. Bump
  the pin and the hook rev together, never separately.
- **mypy is strict with zero per-module escapes.** The pydantic plugin is
  enabled; `prop-decorator` is disabled (false positive on
  `@computed_field` + `@property`). Untyped third-party deps are listed in
  the `ignore_missing_imports` override in `pyproject.toml`.
- **Test-suite ordering contract:** `tests/test_jobs_admin.py` must be the
  FIRST suite to import `movie_conceptualizer.api.*`. Several api modules
  freeze env config into module constants at import time, and that suite
  applies its env via `importlib.reload`. Consequences for new test files:
  never import the api at module level (lazy-import inside fixtures), name
  API-touching test files so they sort after `test_jobs_admin.py`, and key
  any `dependency_overrides` by the exact callables the route module holds
  (e.g. `routes.export.get_project_store`), not re-imported ones.
- **Two model layers exist on purpose:** `models/` (core + analysis) is the
  pipeline's source of truth; `api/schemas.py` and
  `storage/repositories.py` define parallel request/persistence models.
  The two `type: ignore[arg-type]` sites in `api/dependencies.py` mark
  that seam. Don't add a third copy.
- **MockWorkflow is dev-only.** `get_workflow()` raises if
  `MOVIECON_WORKFLOW_BACKEND=mock` outside `MOVIECON_DEV_MODE`. Tests use
  the mock; the real agent pipeline has no automated end-to-end coverage
  (needs an API key) — treat agent-touching changes accordingly.
- **Known duplication (open debt):** the CLI drives the LangGraph pipeline
  (`workflows/pipeline.py`) while the API drives its own orchestration
  (`api/dependencies.RealWorkflow` + `api/generation_service.py`). If you
  change one flow, check the other.

## Repo facts

- CodeQL was removed deliberately: code scanning requires GHAS, which is
  unavailable on this private repo. Don't re-add it without GHAS.
- Semgrep runs `--config auto` with two SQL audit rules excluded as
  documented false positives (the storage layer is fully parameterized via
  `_param()`/`_params()` placeholders).
- PDF export is real (`api/pdf_export.py`, ReportLab); JSON and PDF come
  from the same export payloads.
