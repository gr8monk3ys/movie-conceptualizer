# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install ".[redis,jobs,postgresql]"

FROM python:3.13-slim

# Run as an unprivileged user; the SQLite default path lives under $HOME.
RUN useradd --create-home --uid 1000 moviecon

COPY --from=builder /install /usr/local

USER moviecon
WORKDIR /home/moviecon

EXPOSE 8000

# python-based healthcheck: the slim image ships no curl/wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "movie_conceptualizer.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
