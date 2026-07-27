"""Shared pytest configuration.

Mechanically enforces the test-ordering contract documented in CLAUDE.md:
``tests/test_jobs_admin.py`` must be the first suite to import
``movie_conceptualizer.api.*``, because several api modules freeze env
config into module constants at import time and that suite applies its env
via ``importlib.reload``. Alphabetical collection happens to satisfy this
today; this hook keeps it true under pytest-randomly, pytest-xdist's
per-file ordering, or explicit file arguments.
"""


def pytest_collection_modifyitems(session, config, items):
    def _order(item):
        return 0 if "test_jobs_admin" in str(getattr(item, "fspath", "")) else 1

    items.sort(key=_order)
