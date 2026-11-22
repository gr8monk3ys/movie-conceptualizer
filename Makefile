.PHONY: check
check:
	ruff check src tests scripts
	ruff format --check src tests scripts
	mypy src
	pytest -q --cov=movie_conceptualizer --cov-fail-under=65
