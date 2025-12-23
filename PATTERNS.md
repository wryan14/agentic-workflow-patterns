# Agentic Workflow Patterns

Six patterns for constraining AI agent behavior, learned from production use.

---

## 1. State Machines Over Instructions

### Problem

Agents interpret prose instructions differently each session. "First do X, then Y, then Z" becomes "I've done something related to X, Y, and Z" with no guarantee of order, completeness, or correctness.

When you tell an agent to "translate the document, validate it, generate audio, and upload," it may:
- Translate half the document and call it done
- Skip validation because it "looks fine"
- Generate audio for what it translated, not the full document
- Report success while the source file remains half-processed

### Solution

Replace prose workflow descriptions with a formal state machine. The agent reads the current state and follows explicit transitions, not remembered instructions.

```
SELECTING → RESEARCHING → TRANSLATING → VALIDATING →
GENERATING_AUDIO → GENERATING_VIDEO → AWAITING_VIDEO →
DISTRIBUTING → PUBLISHING → REVIEW → COMPLETE
```

Each state has:
- **Entry requirements**: What must be true to enter this state
- **Exit requirements**: What must be true to leave this state
- **Allowed transitions**: Which states can follow this one

### Implementation

The state lives in a JSON file that persists across sessions:

```json
{
  "project_id": "de-trinitate-20251214",
  "state": "TRANSLATING",
  "source": {
    "title_latin": "De Trinitate",
    "author": "Augustine of Hippo",
    "file_path": "/path/to/source.txt"
  },
  "translation": {
    "file_path": null,
    "validation": { "passed": null }
  }
}
```

At session start, the agent reads the state file and executes the appropriate action:

```python
from pipeline.state import get_active_projects

projects = get_active_projects()
if projects:
    project = projects[0]
    print(f"Resuming: {project['project_id']} in state {project['state']}")
```

The agent can't skip to GENERATING_AUDIO because the state file says TRANSLATING. It can't claim to be done because `translation.validation.passed` is still null.

### Transferable Insight

**State machines work because they're external to the agent's context.**

The agent's memory resets each session. Instructions get reinterpreted. But a JSON file on disk doesn't forget, doesn't reinterpret, and doesn't rationalize.

For any multi-step workflow:
1. Define states as a directed graph
2. Store current state persistently (file, database, API)
3. Make the agent's first action be "read current state"
4. Block transitions that skip required states

---

## 2. Hard Gates Over Checklists

### Problem

Agents treat validation as a formality. When told to "check that the translation is complete before proceeding," the agent checks... something... and proceeds. It may check if the file exists, if it has content, if it "looks reasonable." It will not catch the translation that ends mid-sentence at 60% completion.

Checklists don't work because the agent decides whether each item passes. Given enough context pressure (time, complexity, user expectation), the agent will find reasons to check boxes.

### Solution

Replace checklists with scripts that return exit codes. Exit code 0 means pass. Exit code 1 means blocked. The agent cannot proceed without code 0.

```bash
python validation/validate_translation.py source.txt translation.json
# Exit 0: Proceed to next state
# Exit 1: Fix the issue, cannot proceed
```

The critical insight: **the agent doesn't decide if validation passed.** The script decides. The agent just reads the result.

### Implementation

Validation scripts check structural properties, not vibes:

```python
def check_source_coverage(source_text: str, last_latin: str) -> Tuple[bool, str]:
    """Check if the last translated chunk appears near the end of source."""

    source_normalized = normalize_latin(source_text)
    last_latin_normalized = normalize_latin(last_latin)

    # Find where the last translated text appears in source
    pos = source_normalized.find(last_latin_normalized[-100:])

    if pos == -1:
        return False, "Last translated chunk not found in source!"

    # Calculate remaining untranslated content
    remaining = len(source_normalized) - pos
    remaining_pct = remaining / len(source_normalized) * 100

    if remaining > 500:  # More than ~500 chars = incomplete
        return False, f"Translation incomplete: {remaining_pct:.1f}% remains"

    return True, "Translation covers source text"
```

The script checks if the last translated Latin appears near the end of the source. If 30% of the source remains untranslated, exit code 1. No negotiation.

When validation fails, the agent's instructions say:

```
On exit code 1:
1. Report the exact error to the user
2. Add note to project state
3. STOP - do not proceed to next state
```

### Transferable Insight

**Gates work because they're binary and external.**

The agent can't partially pass a gate. The agent can't redefine what passing means. The gate script is the single source of truth.

For any quality-critical transition:
1. Write a script that checks concrete properties
2. Return exit code 1 on any failure
3. Make the agent's instructions explicit: "Do not proceed if exit code is 1"
4. Log failures to the state file for debugging

---

## 3. Parking States for Async Operations

### Problem

Some operations take longer than a session should last. Video encoding takes 30-60 minutes. Deep research API calls take 5-10 minutes. API rate limits require waiting.

If the agent waits, it:
- Consumes context window doing nothing
- Risks timeout or context confusion
- May restart the operation on resume
- Costs money for idle API connections

### Solution

Design explicit "parking states" where the agent exits cleanly and resumes later.

```
GENERATING_VIDEO → AWAITING_VIDEO → PUBLISHING
     │                   ↑
     └───────────────────┘
     (start job, exit session)
```

The agent:
1. Starts the long-running operation
2. Records the job in state
3. Transitions to the parking state
4. **Exits the session**
5. Next session: checks if operation is complete
6. If complete, proceeds; if not, exits again

### Implementation

For video encoding:

```python
# GENERATING_VIDEO state action
def start_video_encoding(project):
    subprocess.Popen([
        'ffmpeg', '-i', audio_path, '-i', cover_path,
        '-c:v', 'libx264', video_path
    ])

    project['video']['job_started_at'] = datetime.utcnow().isoformat()
    transition_state(project, 'AWAITING_VIDEO')

    print("Video encoding started. Exiting session.")
    print("Run `python pipeline/state.py check-video PROJECT_ID` to check status.")
    sys.exit(0)
```

The check function verifies the video is complete and stable:

```python
def check_video_stable(video_path: str, wait_seconds: int = 60) -> bool:
    """Check if video file size is stable (encoding complete)."""
    if not os.path.exists(video_path):
        return False

    size1 = os.path.getsize(video_path)
    time.sleep(wait_seconds)
    size2 = os.path.getsize(video_path)

    return size1 == size2 and size1 > 0
```

### Transferable Insight

**Design for session boundaries, not continuous operation.**

Agents aren't daemons. They start, they run, they stop. Long-running operations need explicit hand-off points where the agent can safely exit.

For any operation longer than ~5 minutes:
1. Create a parking state (AWAITING_X)
2. Record operation start in state file
3. Exit the session cleanly with a status message
4. On resume: check completion, proceed or exit again
5. Make the check fast and idempotent

---

## 4. Private-First Publishing

### Problem

Agents make mistakes. Not occasionally—reliably. If the workflow publishes directly to production:
- Wrong metadata gets indexed by search engines
- Incomplete content reaches subscribers
- Fixing requires delete-and-reupload (breaking links)
- Human review happens after the damage

### Solution

All publishing goes to a private/draft state first. Human review happens before anything is public.

```
PUBLISHING → REVIEW → COMPLETE
    │           │
    │           └── Human reviews, fixes, approves
    └── Upload as PRIVATE
```

The REVIEW state provides commands for fixes:

```bash
python pipeline/review.py fix-title PROJECT_ID "Corrected Title"
python pipeline/review.py fix-desc PROJECT_ID --file new_description.txt
python pipeline/review.py fix-thumb PROJECT_ID --file new_thumbnail.jpg
python pipeline/review.py approve PROJECT_ID
```

Only after approval does content become public:

```bash
python pipeline/review.py publish PROJECT_ID
```

### Implementation

The upload script enforces private-first:

```python
def upload_video(video_path, metadata, thumbnail_path):
    """Upload video to YouTube as PRIVATE."""

    request_body = {
        'snippet': {
            'title': metadata['title'],
            'description': metadata['description'],
            'tags': metadata['tags']
        },
        'status': {
            'privacyStatus': 'private',  # ALWAYS private
            'selfDeclaredMadeForKids': False
        }
    }

    # Upload...

    return video_id
```

There is no `--public` flag. The agent cannot upload as public. Only the `review.py publish` command changes visibility, and it requires explicit human invocation.

### Transferable Insight

**Build review into the architecture, not the process.**

Telling agents to "review before publishing" doesn't work. Making it structurally impossible to publish without review does.

For any irreversible operation:
1. Route through a draft/private state first
2. Provide fix commands that work on the draft
3. Require explicit human action to make it final
4. Never give the agent a "skip review" escape hatch

---

## 5. Templates Over Generation

### Problem

Agents add creative flourishes. Given "write a YouTube description," the agent will include sections you didn't ask for, remove sections you need, add emoji, change formatting, and generally "improve" things each time.

This makes output inconsistent and breaks downstream processes that expect specific formats.

### Solution

Give the agent a template with placeholders. The agent fills in values, but doesn't modify structure.

```
{title}

{one_sentence_summary}

{chapter_timestamps}

Read the translation: {blog_url}
Download the audio: {archive_url}
Source text and translation: {github_url}

Patrologia Latina Volume {volume}
```

The agent can't add a "SUBSCRIBE!" section because there's no placeholder for it. The agent can't add emoji because the template doesn't have any.

### Implementation

The description generator uses a template file:

```python
def generate_description(template_path, values):
    """Generate description by filling template placeholders."""

    template = Path(template_path).read_text()

    # Validate all required placeholders are provided
    placeholders = re.findall(r'\{(\w+)\}', template)
    missing = [p for p in placeholders if p not in values]
    if missing:
        raise ValueError(f"Missing values: {missing}")

    # Fill placeholders
    for key, value in values.items():
        template = template.replace(f'{{{key}}}', str(value))

    return template
```

The template is version-controlled. Changes to output format require changing the template, not re-prompting the agent.

Validation catches deviations:

```python
def validate_description(content):
    """Check description follows template format."""

    forbidden_patterns = [
        r'RESOURCES',
        r'SUBSCRIBE',
        r'BIBLIOGRAPHY',
        r'##',  # Markdown headers
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, content):
            return False, f"Forbidden pattern found: {pattern}"

    return True, "Description follows template"
```

### Transferable Insight

**Constrain the output space, not the process.**

You can't reliably tell an agent "don't add extra sections." You can give it a template where adding sections would require modifying the template itself—which it can't do.

For any structured output:
1. Create a template with explicit placeholders
2. Have the agent fill placeholders, not generate structure
3. Validate output matches expected format
4. Reject output that deviates from template

---

## 6. Provenance Tracking

### Problem

Agents hallucinate. When asked to "use the research to write a blog post," the agent may:
- Summarize its own knowledge instead of the research file
- Mix research content with invented content
- Drop citations while keeping claims
- Produce plausible-looking content that's fabricated

The output looks scholarly but contains none of the actual research.

### Solution

Validate that specific content from source files appears in output files. Don't check format—check provenance.

If research.md contains citations like `[journals.openedition.org]` and the blog post has zero matching citations, the blog was not generated from the research.

### Implementation

The blog validation script checks multiple provenance signals:

```python
def validate_blog_content(blog_content: str, research_content: str):
    """Verify blog contains actual research content, not AI summary."""

    errors = []

    # 1. Check citation preservation
    research_citations = extract_citations(research_content)
    blog_citations = extract_citations(blog_content)

    preserved = research_citations & blog_citations
    if len(preserved) / len(research_citations) < 0.5:
        errors.append("Citations from research not preserved in blog")

    # 2. Check for distinctive research phrases
    unique_phrases = extract_unique_phrases(research_content)
    found_in_blog = sum(1 for p in unique_phrases if p in blog_content.lower())

    if found_in_blog == 0:
        errors.append("No distinctive research phrases found in blog")

    # 3. Check for generic AI filler
    generic_count = count_generic_phrases(blog_content)
    if generic_count > 5:
        errors.append(f"Found {generic_count} generic AI-filler phrases")

    return len(errors) == 0, errors
```

Generic phrases that indicate AI summarization rather than research extraction:

```python
GENERIC_PHRASES = [
    r'witnessed intensifying debates over',
    r'these debates were not merely academic',
    r'reflected genuine tensions within',
    r'throughout Western Christendom',
    r'one of the most prolific',
    r'in recent decades',
    r'some scholars have argued',
]
```

If the blog contains generic academic-sounding filler instead of the specific claims and citations from the research, validation fails.

### Transferable Insight

**Validate content origin, not just content quality.**

An agent can produce perfectly formatted, grammatically correct, topically relevant content that is entirely fabricated. Format validation doesn't catch this.

For any synthesis task:
1. Identify unique markers in source content (citations, specific phrases, names)
2. Verify those markers appear in output
3. Flag generic filler that indicates summarization over extraction
4. Reject output that doesn't demonstrate use of source material

---

## Summary

| Pattern | Constraint Type | What It Prevents |
|---------|----------------|------------------|
| State Machines | Workflow order | Skipping or reordering steps |
| Hard Gates | Quality enforcement | Proceeding with failed validation |
| Parking States | Session management | Wasted context on long operations |
| Private-First | Publication safety | Irreversible mistakes going live |
| Templates | Output structure | Creative deviation from format |
| Provenance | Content origin | Hallucinated content passing as research |

Each pattern removes a degree of freedom from the agent. Fewer decisions means fewer wrong decisions.

The goal is not to make agents smarter. The goal is to make agent behavior predictable.
