# Contributing

## Setup

```bash
pip install -e ".[dev,jobs,redis,postgresql]"
pre-commit install   # optional but recommended
```

## Before you push

CI gates on exactly these four commands (Python 3.11 and 3.12); run them locally:

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy src          # strict, whole tree
pytest -q
```

## Ground rules

- **ruff is pinned** to the version in the `dev` extra, matching the
  `ruff-pre-commit` rev in `.pre-commit-config.yaml`. Bump both together.
- **mypy strict has no per-module escapes.** New code ships typed. If a
  third-party dependency has no stubs, add it to the documented
  `ignore_missing_imports` list in `pyproject.toml`.
- **Tests accompany behavior changes.** Anything user-facing (CLI command,
  API route, export format) needs a test that exercises it end-to-end with
  the LLM mocked.
- **Test files that import `movie_conceptualizer.api` must lazy-import it**
  inside fixtures and be named to sort after `test_jobs_admin.py`. See the
  note at the top of `tests/test_pdf_export.py` and `CLAUDE.md` for why.
- Version lives in `pyproject.toml` only; everything else reads
  `movie_conceptualizer.__version__`.

See `CLAUDE.md` for the full list of non-obvious project constraints.
