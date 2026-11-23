# Movie Conceptualizer

AI pre-production pipeline: a screenplay goes in, a shot list and storyboard prompts come out, via the `moviecon` CLI and a FastAPI service.

## Language

### The pipeline

**Script**:
A parsed screenplay (Fountain, FDX or PDF) made of Scenes and a Title Page. Input to everything else.
_Avoid_: screenplay file, document

**Scene**:
One slugline-delimited unit of a Script, numbered sequentially, with a scene type, location, time of day and ordered content blocks (Action Block, Dialogue Block, Transition).
_Avoid_: sequence, chapter

**Analyzed Scene**:
A Scene after the Script Analyzer has added its emotional beats, overall tone, pacing, dramatic moments, visual emphasis points and atmosphere. An Analyzed Script is the collection plus the main characters.
_Avoid_: scene analysis result

**Shot**:
One camera setup within a Scene, identified by a shot id such as `1A`, with a shot type, camera angle, camera movement, subject and emotional purpose.
_Avoid_: take, camera setup

**Shot List**:
The ordered Shots designed for one Scene by the Shot Designer.

**Storyboard Frame**:
One image-generation prompt for a Shot, with composition, lighting, mood and camera info. A Storyboard is the set of Frames for a Scene or Script, plus a style guide and character reference notes.
_Avoid_: panel, image

**Pipeline**:
The LangGraph workflow that runs validate input, analyze scenes, design shots and create storyboards, optionally pausing at the two human review steps. Its state is the Pipeline State.
_Avoid_: workflow engine, chain

**Agent**:
An LLM-backed pipeline stage: Script Analyzer, Shot Designer or Storyboard Artist. All extend the base agent.

**Mock Workflow**:
The dev-only API backend that fabricates results without calling an LLM. Refused outside dev mode.
_Avoid_: fake, stub

### Production breakdown

**Breakdown Element**:
Something a scene needs on set (prop, vehicle, VFX, wardrobe, stunt, ...), classified by Breakdown Category, with quantity, scenes and an optional estimated cost.

**Character**:
A speaking role in the Script, with dialogue count, scene appearances and aliases. A principal Character is flagged `is_principal`.

**Location**:
A named place in the Script, with scene type, time of day and sub-locations.

**Emotional Beat**:
In the core model, an enum of beat kinds (tension, relief, joy, ...). In the analysis model, a beat within an Analyzed Scene. Same name, two layers.

### The service

**Project**:
The API's unit of work. It owns one Script and the generated Shot Lists and Storyboards, and moves through a Project Status lifecycle (created, script_uploaded, parsing, parsed, analyzing, analyzed, generating_shots, shots_generated, generating_storyboard, completed, error). A Project has an owner.

**Job**:
A background generation run with status queued, running, succeeded or failed, attempts, progress and a current step. Created with an idempotency key; exhausted Jobs go to the dead-letter table.
_Avoid_: task

**Job Audit Log**:
Hash-chained record of administrative actions on Jobs (each row stores the previous row's hash).

**Export**:
A Shot List or Storyboard rendered as JSON or PDF from the same payload.

**Repository**:
The storage-layer class for one table family (project, script, user, job, generation, ...), SQLite by default, PostgreSQL optionally.
