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
```

## Quick Start

### CLI Usage

```bash
# Parse a screenplay
moviecon parse examples/sample_screenplay.fountain

# Analyze with AI (requires ANTHROPIC_API_KEY)
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
- `POST /api/v1/projects` - Create project
- `POST /api/v1/projects/{id}/script` - Upload script
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
| `ANTHROPIC_API_KEY` | - | Claude API key (required for AI features) |
| `OPENAI_API_KEY` | - | OpenAI API key (optional) |
| **Database** | | |
| `MOVIECON_DB_BACKEND` | `sqlite` | Database backend (`sqlite` or `postgresql`) |
| `MOVIECON_DB_PATH` | `~/.movie-conceptualizer/data.db` | SQLite database path |
| `MOVIECON_DATABASE_URL` | - | PostgreSQL connection string |
| `DATABASE_URL` | - | Fallback PostgreSQL URL |
| `MOVIECON_DB_POOL_SIZE` | `5` | PostgreSQL connection pool size |
| **Authentication** | | |
| `MOVIECON_SECRET_KEY` | (random) | JWT signing key |
| `MOVIECON_REQUIRE_AUTH` | `false` | Require authentication |
| `MOVIECON_DEV_MODE` | `true` | Enable dev mode (creates test user) |
| `MOVIECON_TOKEN_EXPIRE_MINUTES` | `30` | JWT token expiration |
| **Rate Limiting** | | |
| `MOVIECON_RATE_LIMIT_BACKEND` | `memory` | Backend (`memory` or `redis`) |
| `MOVIECON_RATE_LIMIT` | `100/minute` | Default rate limit |
| `MOVIECON_RATE_LIMIT_GENERATION` | `10/minute` | AI endpoint limit |
| `MOVIECON_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `MOVIECON_REDIS_PREFIX` | `moviecon:ratelimit:` | Redis key prefix |

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

**Output:**
- JSON - Structured data for all outputs
- PDF - Shot lists and storyboard packets (planned)

## Development

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

## Roadmap

- [x] Phase 1: Script → Shot List → Storyboard
- [x] Production hardening: SQLite, JWT auth, rate limiting
- [x] PostgreSQL & Redis backends
- [ ] Phase 2: Blocking diagrams + video animatics
- [ ] Phase 3: Production scheduling + budgeting
- [ ] Phase 4: Collaboration + enterprise features

## License

MIT License - see LICENSE file
