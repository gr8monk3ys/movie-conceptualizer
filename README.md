# Movie Conceptualizer

AI-powered filmmaking platform: **Script → Shot List → Storyboard**

Transform your screenplay into professional pre-production materials using multi-agent AI.

## Features

- **Fountain Parser**: Parse industry-standard Fountain screenplay format
- **Script Analysis**: AI-powered scene analysis for emotional beats, pacing, and visual opportunities
- **Shot Designer**: Automated shot list generation with film grammar awareness
- **Storyboard Artist**: Generate detailed image prompts for each shot
- **Full Pipeline**: End-to-end workflow from script to storyboard
- **REST API**: FastAPI-based API with JWT authentication and rate limiting
- **CLI**: Command-line interface for local processing
- **Production Ready**: PostgreSQL support, Redis rate limiting, configurable backends

## Installation

```bash
# Clone the repository
git clone https://github.com/gr8monk3ys/movie-conceptualizer.git
cd movie-conceptualizer

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# With PostgreSQL support
pip install -e ".[postgresql]"

# With Redis support
pip install -e ".[redis]"

# All extras (dev + postgresql + redis)
pip install -e ".[dev,postgresql,redis]"

# PDF OCR extras (requires system deps: tesseract + poppler)
pip install -e ".[pdf]"
```

## Quick Start

### CLI Usage

```bash
# Parse a screenplay
moviecon parse examples/sample_screenplay.fountain

# Analyze with AI (requires ANTHROPIC_API_KEY or OPENAI_API_KEY)
moviecon analyze examples/sample_screenplay.fountain -o analysis.json

# Generate shot list
moviecon shots examples/sample_screenplay.fountain -o shots.json

# Generate storyboard prompts
moviecon storyboard examples/sample_screenplay.fountain -o storyboard.json

# Run full pipeline
moviecon pipeline examples/sample_screenplay.fountain -o ./output

# Start API server
moviecon serve --port 8000
```

### Python API

```python
from movie_conceptualizer.parsers import load_script, get_script_summary
from movie_conceptualizer.workflows import run_pipeline, PipelineConfig

# Parse a screenplay
script = load_script("screenplay.fountain")
summary = get_script_summary(script)
print(f"Title: {script.title}")
print(f"Scenes: {summary['scene_count']}")
print(f"Characters: {summary['character_count']}")

# Run the AI pipeline (requires API key)
config = PipelineConfig(
    model_name="claude-sonnet-4-20250514",
    style_guide="cinematic, dramatic lighting"
)
result = run_pipeline(script, config)

# Access results
for shot_list in result.shot_lists:
    for shot in shot_list.shots:
        print(f"{shot.shot_number}: {shot.shot_type} - {shot.description}")
```

### REST API

```bash
# Start the server
moviecon serve

# Or directly with uvicorn
uvicorn movie_conceptualizer.api.main:app --reload
```

API endpoints:
- `POST /api/v1/auth/token` - Get JWT token
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Revoke refresh token
- `POST /api/v1/projects` - Create project
- `POST /api/v1/projects/{id}/script` - Upload script
- `POST /api/v1/projects/{id}/script/upload` - Upload script file
- `POST /api/v1/projects/{id}/script/upload/async` - Upload script file (async)
- `POST /api/v1/projects/{id}/generate` - Run full pipeline
- `GET /api/v1/projects/{id}/export/shotlist` - Export shot list
- `GET /health` - Health check with backend status
- `GET /health/redis` - Redis-specific health check

API docs available at `http://localhost:8000/docs`

## Architecture

```
movie_conceptualizer/
├── models/           # Pydantic data models
│   ├── core.py       # Script, Scene, Character, Location
│   ├── shots.py      # Shot, ShotList, ShotType, CameraMovement
│   ├── storyboard.py # StoryboardFrame, Storyboard
│   ├── blocking.py   # BlockingDiagram, CharacterPosition
│   └── analysis.py   # AnalyzedScene, emotional beats
├── parsers/          # Screenplay parsing
│   ├── fountain_parser.py  # Fountain format parser
│   └── script_loader.py    # File loading utilities
├── agents/           # AI agents
│   ├── script_analyzer.py    # Scene analysis
│   ├── shot_designer.py      # Shot list generation
│   └── storyboard_artist.py  # Image prompt generation
├── workflows/        # LangGraph orchestration
│   ├── state.py      # Pipeline state definitions
│   └── pipeline.py   # Multi-agent workflow
├── storage/          # Database backends
│   ├── database.py   # SQLite & PostgreSQL support
│   └── repositories.py # Repository pattern
├── api/              # FastAPI REST API
│   ├── main.py       # Application setup
│   ├── auth.py       # JWT authentication
│   ├── ratelimit.py  # Rate limiting (memory/Redis)
│   └── routes/       # API endpoints
└── cli.py            # Command-line interface
```

## Multi-Agent System

The platform uses LangGraph to orchestrate three specialized AI agents:

1. **Script Analyzer**: Extracts emotional beats, pacing, tone, and visual emphasis points
2. **Shot Designer**: Generates shot lists with appropriate shot types based on scene analysis
3. **Storyboard Artist**: Creates detailed image prompts maintaining character consistency

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **AI** | | |
| `MOVIECON_LLM_PROVIDER` | `anthropic` | LLM provider (`anthropic` or `openai`) |
| `MOVIECON_LLM_MODEL` | - | Override model name for selected provider |
| `MOVIECON_OPENAI_MODEL` | `gpt-4o-mini` | Default OpenAI model (if provider is `openai`) |
| `MOVIECON_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Default Anthropic model |
| `ANTHROPIC_API_KEY` | - | Claude API key (required for Anthropic) |
| `OPENAI_API_KEY` | - | OpenAI API key (required for OpenAI) |
| `OPENAI_IMAGE_MODEL` | `gpt-image-1` | OpenAI image model for pre-vis generation |
| `OPENAI_IMAGE_SIZE` | `1536x1024` | Image size for pre-vis generation |
| `OPENAI_IMAGE_QUALITY` | `high` | Image quality (low, medium, high, auto) |
| `OPENAI_IMAGE_BACKGROUND` | `opaque` | Image background (opaque or transparent) |
| `OPENAI_IMAGE_OUTPUT_FORMAT` | `png` | Output format for generated images |
| `OPENAI_IMAGE_OUTPUT_COMPRESSION` | `0` | JPEG/WebP compression (0-100) |
| **Database** | | |
| `MOVIECON_DB_BACKEND` | `sqlite` | Database backend (`sqlite` or `postgresql`) |
| `MOVIECON_DB_PATH` | `~/.movie-conceptualizer/data.db` | SQLite database path |
| `MOVIECON_DATABASE_URL` | - | PostgreSQL connection string |
| `DATABASE_URL` | - | Fallback PostgreSQL URL |
| `MOVIECON_DB_POOL_SIZE` | `5` | PostgreSQL connection pool size |
| **Authentication** | | |
| `MOVIECON_SECRET_KEY` | (random) | JWT signing key |
| `MOVIECON_REQUIRE_AUTH` | `false` | Require authentication |
| `MOVIECON_DEV_MODE` | `false` | Enable dev mode behaviors |
| `MOVIECON_ALLOW_DEV_FALLBACK` | `false` | Enable dev login/plaintext fallback (dev only) |
| `MOVIECON_TOKEN_EXPIRE_MINUTES` | `60` | JWT token expiration |
| `MOVIECON_ADMIN_POLICY` | `role` | Admin policy (`env` or `role`) |
| `MOVIECON_ADMIN_USERS` | - | Comma-separated admin usernames (required if `ADMIN_POLICY=env`) |
| `MOVIECON_STRICT_CONFIG` | `false` | Fail startup on config warnings |
| `MOVIECON_ALLOWED_ROLES` | `user,admin` | Allowed role names |
| `MOVIECON_PASSWORD_MIN_LENGTH` | `8` | Minimum password length |
| `MOVIECON_PASSWORD_REQUIRE_UPPER` | `false` | Require uppercase letter |
| `MOVIECON_PASSWORD_REQUIRE_LOWER` | `true` | Require lowercase letter |
| `MOVIECON_PASSWORD_REQUIRE_DIGIT` | `true` | Require digit |
| `MOVIECON_PASSWORD_REQUIRE_SPECIAL` | `false` | Require special character |
| `MOVIECON_PASSWORD_POLICY_ENFORCE` | `true` | Enforce password policy on registration |
| `MOVIECON_REFRESH_TOKENS_ENABLED` | `true` | Enable refresh tokens |
| `MOVIECON_REFRESH_TOKEN_EXPIRE_DAYS` | `14` | Refresh token TTL (days) |
| `MOVIECON_REFRESH_ROTATE` | `true` | Rotate refresh tokens on use |
| `MOVIECON_ADMIN_MFA_SECRET` | - | Base32 TOTP secret for admin MFA |
| `MOVIECON_ADMIN_MFA_WINDOW` | `1` | TOTP window (steps) |
| `MOVIECON_INPROCESS_INLINE` | `false` | Run in-process jobs inline (useful for tests) |
| `MOVIECON_IDEMPOTENCY_TTL_DAYS` | `7` | Idempotency TTL (days) |
| `MOVIECON_AUDIT_LOG_SIGNING_KEY` | - | HMAC key for audit log hash chaining |
| `MOVIECON_METRICS_ENABLED` | `true` | Enable `/metrics` endpoint |
| **Rate Limiting** | | |
| `MOVIECON_RATE_LIMIT_BACKEND` | `memory` | Backend (`memory` or `redis`) |
| `MOVIECON_RATE_LIMIT` | `100/minute` | Default rate limit |
| `MOVIECON_RATE_LIMIT_GENERATION` | `10/minute` | AI endpoint limit |
| `MOVIECON_RATE_LIMIT_AUTH` | `10/minute` | Auth endpoint limit |
| `MOVIECON_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `MOVIECON_REDIS_PREFIX` | `moviecon:ratelimit:` | Redis key prefix |
| **PDF OCR** | | |
| `MOVIECON_PDF_OCR` | `auto` | OCR mode (`auto`, `always`, `never`) |
| `MOVIECON_PDF_OCR_DPI` | `200` | OCR rendering DPI |
| `MOVIECON_PDF_OCR_MAX_PAGES` | - | Limit OCR pages for large PDFs |
| `MOVIECON_PDF_SCENE_CHUNK` | `3` | Paragraphs per synthetic scene when no headings found |
| `MOVIECON_PDF_PREPROCESS` | `true` | Enable OCR text preprocessing |
| **Logging** | | |
| `MOVIECON_LOG_LEVEL` | `INFO` | Log level |
| `MOVIECON_LOG_FORMAT` | `json` | Log format (`json` or `text`) |
| **Uploads** | | |
| `MOVIECON_MAX_UPLOAD_MB` | `25` | Max upload size (MB) |

### Pre-Vis Image Generation

Generate pre-vis frames from the storyboard prompt pack using the OpenAI Images API:

```bash
python3 scripts/generate_previs_images.py \
  --prompts output/previs_prompts.json \
  --out-dir output/previs_frames \
  --manifest output/previs_manifest.json
```

If you want to limit the number of frames during tests:

```bash
python3 scripts/generate_previs_images.py --limit 5 --dry-run
```
| `MOVIECON_AV_SCAN` | - | Antivirus scan mode (`clamav`) |

### Database Configuration

**SQLite (default):**
```bash
# No configuration needed - uses ~/.movie-conceptualizer/data.db
moviecon serve
```

**PostgreSQL:**
```bash
export MOVIECON_DB_BACKEND=postgresql
export MOVIECON_DATABASE_URL=postgresql://user:pass@localhost:5432/moviecon
moviecon serve
```

### Rate Limiting Configuration

**In-Memory (default):**
```bash
# No configuration needed
moviecon serve
```

**Redis:**
```bash
export MOVIECON_RATE_LIMIT_BACKEND=redis
export MOVIECON_REDIS_URL=redis://localhost:6379/0
moviecon serve
```

## Supported Formats

**Input:**
- `.fountain` - Fountain screenplay format
- `.txt` - Plain text with Fountain formatting
- `.fdx` - Final Draft XML format (best-effort)
- `.pdf` - PDF (best-effort text extraction, OCR fallback)

**Output:**
- JSON - Structured data for all outputs
- PDF - Shot lists and storyboard packets (planned)

## Development

### Schema Evolution

Migrations are applied automatically on startup. For production, take a backup before upgrading.

```bash
moviecon db backup
```

Commands:
```bash
moviecon db status
moviecon db migrate
```

Rollback strategy:
- SQLite: restore the previous database file backup.
- PostgreSQL: restore a `pg_dump` snapshot taken before migration.

```bash
# Run tests (109 tests)
uv run pytest

# Type checking
uv run mypy src

# Linting
uv run ruff check src

# Format code
uv run ruff format src
```

## Production Deployment

```bash
# Install with production extras
pip install movie-conceptualizer[postgresql,redis]

# Configure environment
export MOVIECON_DB_BACKEND=postgresql
export MOVIECON_DATABASE_URL=postgresql://user:pass@db:5432/moviecon
export MOVIECON_RATE_LIMIT_BACKEND=redis
export MOVIECON_REDIS_URL=redis://redis:6379/0
export MOVIECON_REQUIRE_AUTH=true
export MOVIECON_SECRET_KEY=your-secure-secret-key
export ANTHROPIC_API_KEY=your-api-key

# Run with gunicorn
gunicorn movie_conceptualizer.api.main:app -k uvicorn.workers.UvicornWorker -w 4
```

### Background Jobs (Arq)

```bash
# Install job queue extras
pip install movie-conceptualizer[jobs]

# Configure job backend and Redis
export MOVIECON_JOB_BACKEND=arq
export MOVIECON_JOB_REDIS_URL=redis://redis:6379/0

# Start Arq worker
arq movie_conceptualizer.api.arq_tasks.WorkerSettings
```

Note:
- Set `MOVIECON_INPROCESS_INLINE=true` to execute in-process jobs inline (helpful for tests or debugging).

Job endpoints:
- `GET /api/v1/jobs/{id}` - job status (includes progress, attempts)
- `GET /api/v1/jobs` - list jobs (owner or admin)
- `GET /api/v1/jobs?status=<status>` - filter jobs by status (`queued`, `running`, `succeeded`, `failed`)
- `GET /api/v1/jobs/dead-letter` - list failed jobs
- `POST /api/v1/jobs/dead-letter/replay` - replay dead-letter jobs (admin)
- `POST /api/v1/jobs/{id}/retry` - re-enqueue failed job (arq backend only)
- `GET /api/v1/jobs/metrics` - job metrics (admin)
- `POST /api/v1/jobs/purge` - purge jobs (admin)
- `POST /api/v1/jobs/idempotency/purge` - purge idempotency records (admin)
- `GET /api/v1/jobs/audit` - audit log list (admin, supports `format=csv`)
- `POST /api/v1/jobs/audit/purge` - purge audit logs (admin)
- `GET /metrics` - request + job metrics (if enabled)

Admin access:
- Default policy is role-based. Assign `admin` role to users who need admin access.
- Set `MOVIECON_ADMIN_POLICY=env` and `MOVIECON_ADMIN_USERS` to restrict admin endpoints by username.
Roles:
- Set `MOVIECON_ADMIN_POLICY=role` to require users with role `admin`.
- Use `POST /api/v1/auth/users/{id}/role` (admin only) to update roles.
Audit logging:
- Admin job actions are recorded in `job_audit_logs`. Set `MOVIECON_AUDIT_LOG_SIGNING_KEY` to HMAC-sign audit hashes.
Audit CSV format:
- `created_at` values are UTC ISO8601 timestamps with a `Z` suffix.
- `schema_version` indicates the audit CSV schema version.
Dev auth fallback:
- Set `MOVIECON_ALLOW_DEV_FALLBACK=true` (with `MOVIECON_DEV_MODE=true`) to enable dev login shortcuts. Disabled by default.
Logging:
- Logs include `request_id` when clients provide an `X-Request-ID` header. For job workers, `request_id` is set to the job ID.
Idempotency:
- Provide an `Idempotency-Key` header on async generation requests to dedupe job submissions.
Health checks:
- `GET /health/jobs` returns background job backend health.

Ownership:
- Projects and jobs are associated with a `user_id`. Non-admin users can only access their own records.

Project ownership helpers:
- `POST /api/v1/projects/{id}/owner` - assign project owner (admin)
- `POST /api/v1/projects/owner/bulk-assign` - bulk assign owner (admin)

## Roadmap

- [x] Phase 1: Script → Shot List → Storyboard
- [x] Production hardening: SQLite, JWT auth, rate limiting
- [x] PostgreSQL & Redis backends
- [ ] Phase 2: Blocking diagrams + video animatics
- [ ] Phase 3: Production scheduling + budgeting
- [ ] Phase 4: Collaboration + enterprise features

## License

MIT License - see LICENSE file
