# Implementation Notes

This repository documents patterns, not implementation code. Here are brief notes on the components that exist in the production system but aren't included here.

## What's Not Included

The production system has 15+ operational scripts. These are standard API integrations—the interesting part is how they're orchestrated, which is documented in [ARCHITECTURE.md](ARCHITECTURE.md) and [PATTERNS.md](PATTERNS.md).

### Research Pipeline

**Deep Research** (`research_deep.py`)
- Uses OpenRouter API with `openai/o4-mini-deep-research` model
- Prompts for author biography, historical context, theological significance
- Requires structured output: citations, image candidates, key terms
- Validates minimum word count (1200+) and citation count (8+)

The research prompt is heavily structured to ensure consistent output across texts. Research content becomes blog content, so quality here determines downstream quality.

### Translation Pipeline

**Translation** (`translate.py`)
- Uses Claude via OpenRouter with JSON schema enforcement
- Chunks large texts (~50K chars) at natural break points (chapters, paragraphs)
- Resume capability for interrupted translations
- Accepts pre-verified metadata to prevent hallucination

The translation script is included in `examples/` in simplified form. The production version handles chunking, progress tracking, and metadata validation.

### Audio Pipeline

**Audio Synthesis** (`generate_audio.py`)
- OpenAI TTS API with two voices:
  - `echo` for chapter headings and announcements
  - `onyx` for body narration
- Generates per-chunk audio files
- Creates timing file mapping chunks to timestamps
- Concatenates chunks with crossfade

Voice selection is driven by the `speaker` field in translation JSON. The timing file enables video composition with synced text overlays.

### Video Pipeline

**Video Composition** (`compose_video.py`)
- FFmpeg with complex filter graphs
- Static background image (DALL-E generated cover)
- Latin text overlays synced to audio timing
- Text fades in/out with narration
- Output: 1080p MP4, ~20-30 minute typical length

Video encoding takes 30-60 minutes, which is why AWAITING_VIDEO is a parking state.

**Cover Generation** (`generate_cover.py`)
- DALL-E 3 with text-to-image prompt
- Style: medieval manuscript illumination aesthetic
- No text on cover (text added via thumbnail script)

**Thumbnail Generation** (`generate_thumbnail.py`)
- Takes cover image as base
- Adds title text overlay with medieval-style font
- Optimized dimensions for YouTube thumbnails

### Publishing Pipeline

**YouTube Upload** (`upload_youtube.py`)
- YouTube Data API v3 with OAuth 2.0
- Always uploads as PRIVATE (no public flag exists)
- Sets title, description, tags from metadata
- Uploads custom thumbnail
- Returns video ID for state tracking

OAuth token is stored in `youtube_token.pickle`. Browser-based re-authentication is required if token expires—this is why the agent instructions explicitly forbid deleting credential files.

**Archive.org Upload** (`upload_archive.py`)
- Archive.org S3 API via `internetarchive` Python package
- Uploads audio file with metadata
- Creates permanent URL for YouTube description
- Free, stable archival storage

**GitHub Commit** (`commit_github.py`)
- Commits translation JSON and source text to translations repository
- Creates structured directory: `vol_XXX/text_name/`
- Generates URL for YouTube description

**Blog Generation** (`generate_blog.py`)
- Takes research.md and translation.json as input
- Extracts research content directly (no summarization)
- Processes image candidates (validates URLs, places in content)
- Generates Jekyll-compatible markdown with front matter
- Scheduled publishing support (`listed: false` → `listed: true` via cron)

Blog generation is where provenance tracking matters most. The script extracts content from research.md rather than generating new content about the topic.

### Review Pipeline

**Review Commands** (`review.py`)
- `show PROJECT_ID` — Display summary of published content
- `fix-title PROJECT_ID "New Title"` — Update YouTube title
- `fix-desc PROJECT_ID --file description.txt` — Update description
- `fix-thumb PROJECT_ID --file thumbnail.jpg` — Update thumbnail
- `approve PROJECT_ID` — Mark as approved, transition to COMPLETE
- `publish PROJECT_ID` — Change YouTube visibility to PUBLIC

The review step is the human checkpoint. Nothing goes public without explicit `publish` command.

### Validation Scripts

**Translation Validation** (`validate_translation.py`)
- Checks last translated Latin appears near end of source
- Validates metadata consistency with project state
- Catches incomplete translations before audio synthesis
- Included in `examples/` with detailed comments

**Research Validation** (`validate_research.py`)
- Minimum word count across sections
- Minimum citation count with URLs
- Required sections present
- At least one image candidate

**Blog Validation** (`validate_blog.py`)
- Citation preservation from research.md
- Distinctive phrase matching
- Generic AI-filler detection
- Word count requirements

**Description Validation** (`validate_description.py`)
- Template compliance
- No forbidden sections (RESOURCES, SUBSCRIBE, etc.)
- No markdown headers
- Required URLs present

### Utility Scripts

**State Management** (`state.py`)
- `get_active_projects()` — List projects not in terminal states
- `load_project(id)` — Load project state
- `save_project(project)` — Save project state
- `transition_state(project, target)` — Validate and execute transition
- `check_video_stable(path)` — Check if video encoding is complete

**Cost Tracking** (`cost_tracking.json`)
- Per-project cost breakdown
- Running monthly total
- Historical aggregates

## What Makes These Interesting

The individual scripts are not novel—they're standard API integrations. What makes the system work is:

1. **The state machine** — Scripts update project state, state determines which script runs next
2. **The validation gates** — Scripts return exit codes, exit codes block or allow progression
3. **The parking states** — Long-running operations trigger clean session exits
4. **The private-first policy** — Upload scripts can't publish directly
5. **The provenance tracking** — Validation checks content origin, not just format

These patterns are documented in [PATTERNS.md](PATTERNS.md). The scripts are just the implementation of those patterns.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| State storage | JSON files | Simple, human-readable, version-controllable |
| Translation | Claude Sonnet | Strong Latin, consistent formatting |
| Research | OpenRouter deep research | Web search with synthesis |
| TTS | OpenAI | High quality, multiple voices |
| Video | FFmpeg | Flexible, scriptable, free |
| Blog | Jekyll on GitHub Pages | Free hosting, markdown native |
| Archive | Archive.org | Free, permanent, API available |

JSON files for state are deliberately low-tech. They can be inspected, edited, and debugged without tooling. A database would add complexity without benefit for single-project-at-a-time operation.

## Adapting to Other Domains

The implementation details are specific to Latin translation. The patterns are not.

If you're building a different agentic workflow:

1. **Define your states** — What are the discrete phases of your workflow?
2. **Define your gates** — What must be true to proceed at each phase?
3. **Identify parking states** — Which operations take longer than a session?
4. **Design your review step** — Where does human oversight happen?
5. **Choose your templates** — What output formats must be consistent?
6. **Plan your validation** — How do you verify content origin, not just format?

The scripts will be different. The patterns won't.
