# Movie Conceptualizer

AI-powered filmmaking platform: **Script → Shot List → Storyboard**

Transform your screenplay into professional pre-production materials using multi-agent AI.

## Features

- **Fountain Parser**: Parse industry-standard Fountain screenplay format
- **Script Analysis**: AI-powered scene analysis for emotional beats, pacing, and visual opportunities
- **Shot Designer**: Automated shot list generation with film grammar awareness
- **Storyboard Artist**: Generate detailed image prompts for each shot
- **Full Pipeline**: End-to-end workflow from script to storyboard
- **REST API**: FastAPI-based API for integration
- **CLI**: Command-line interface for local processing

## Installation

```bash
# Clone the repository
git clone https://github.com/gr8monk3ys/movie-conceptualizer.git
cd movie-conceptualizer

# Install dependencies
pip install -e .

# For development
pip install -e ".[dev]"
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
- `POST /api/v1/projects` - Create project
- `POST /api/v1/projects/{id}/script` - Upload script
- `POST /api/v1/projects/{id}/generate` - Run full pipeline
- `GET /api/v1/projects/{id}/export/shotlist` - Export shot list

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
├── api/              # FastAPI REST API
│   ├── main.py       # Application setup
│   └── routes/       # API endpoints
└── cli.py            # Command-line interface
```

## Multi-Agent System

The platform uses LangGraph to orchestrate three specialized AI agents:

1. **Script Analyzer**: Extracts emotional beats, pacing, tone, and visual emphasis points
2. **Shot Designer**: Generates shot lists with appropriate shot types based on scene analysis
3. **Storyboard Artist**: Creates detailed image prompts maintaining character consistency

## Supported Formats

**Input:**
- `.fountain` - Fountain screenplay format
- `.txt` - Plain text with Fountain formatting

**Output:**
- JSON - Structured data for all outputs
- PDF - Shot lists and storyboard packets (planned)

## Environment Variables

```bash
ANTHROPIC_API_KEY=your-key-here  # For Claude models
OPENAI_API_KEY=your-key-here     # For OpenAI models (optional)
```

## Development

```bash
# Run tests
pytest

# Type checking
mypy src

# Linting
ruff check src
```

## Roadmap

- [ ] Phase 1: Script → Shot List → Storyboard (current)
- [ ] Phase 2: Blocking diagrams + video animatics
- [ ] Phase 3: Production scheduling + budgeting
- [ ] Phase 4: Collaboration + enterprise features

## License

MIT License - see LICENSE file
