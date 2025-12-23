# System Architecture

This document describes the architecture of a state-machine-controlled agentic workflow for translating Latin patristic texts. For the patterns behind this design, see [PATTERNS.md](PATTERNS.md).

**Whitepaper:** [DOI 10.5281/zenodo.18002473](https://doi.org/10.5281/zenodo.18002473)

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRANSLATION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ SELECTING│ →  │RESEARCHING│ →  │TRANSLATING│ →  │VALIDATING│          │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘          │
│       ↑              │                │               │                  │
│       │         [auto-trigger]        │          [quality gate]          │
│       │                               │               │                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  REVIEW  │ ←  │PUBLISHING │ ←  │DISTRIBUTING│←  │GENERATING│          │
│  └──────────┘    └──────────┘    └──────────┘    │  _AUDIO  │          │
│       │         [PRIVATE-first]       ↑          └──────────┘          │
│       │                               │               │                  │
│       ↓                          ┌──────────┐         │                  │
│  ┌──────────┐                    │AWAITING_ │         │                  │
│  │ COMPLETE │                    │  VIDEO   │         │                  │
│  └──────────┘                    └──────────┘         │                  │
│                                       ↑               │                  │
│                                  [session break]      │                  │
│                                  ┌──────────┐         │                  │
│                                  │GENERATING│ ←───────┘                  │
│                                  │  _VIDEO  │                            │
│                                  └──────────┘                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## State Machine Design

### Why a State Machine?

The pipeline involves multiple long-running operations (API calls, video encoding) that span multiple sessions. A state machine provides:

1. **Resumability** — Work continues where it left off after session breaks
2. **Auditability** — Clear record of what happened and when
3. **Safety gates** — Required checkpoints prevent incomplete work from publishing
4. **Human oversight** — REVIEW state ensures nothing goes public without approval

### State Definitions

| State | Description | Session Behavior |
|-------|-------------|------------------|
| SELECTING | Browsing sources, extracting text | Interactive |
| RESEARCHING | Deep research API call | Auto-triggered on entry |
| TRANSLATING | Translation API call | Agent runs script |
| VALIDATING | Quality checks | Agent runs validation |
| GENERATING_AUDIO | TTS synthesis | Agent runs scripts |
| GENERATING_VIDEO | FFmpeg encoding | **STOP SESSION** |
| AWAITING_VIDEO | Waiting for video file | Check and resume |
| DISTRIBUTING | Archive.org, GitHub, blog | Agent runs uploads |
| PUBLISHING | YouTube upload | Agent runs upload |
| REVIEW | Human approval | **AWAIT COMMANDS** |
| COMPLETE | Finished | Archive and report |
| CANCELLED | Abandoned | Terminal state |

### Transition Requirements

Each transition has explicit requirements that must be satisfied:

| From → To | Requirements |
|-----------|--------------|
| SELECTING → RESEARCHING | `source.title_latin` set |
| RESEARCHING → TRANSLATING | `research.completed_at` and `research.file_path` set |
| TRANSLATING → VALIDATING | `translation.file_path` set |
| VALIDATING → GENERATING_AUDIO | `translation.validation.passed = true` |
| GENERATING_AUDIO → GENERATING_VIDEO | `audio.completed_at` and `audio.file_path` set |
| GENERATING_VIDEO → AWAITING_VIDEO | `video.job_started_at` set |
| AWAITING_VIDEO → DISTRIBUTING | `video.completed_at` and `video.file_path` set |
| DISTRIBUTING → PUBLISHING | `archive_org.url`, `github_url`, and `blog_url` set |
| PUBLISHING → REVIEW | `youtube.video_id` set and `youtube.thumbnail_set = true` |
| REVIEW → COMPLETE | `review.approved_at` set |

The critical insight: **`translation.validation.passed = true`** can only be set by the validation script returning exit code 0. The agent cannot self-certify.

## Key Design Decisions

### AWAITING_VIDEO: The Parking State

Video encoding takes 30-60 minutes. Rather than have the agent wait:

1. Start encoding and transition to GENERATING_VIDEO
2. Immediately transition to AWAITING_VIDEO
3. **End the session**
4. Next session: check if video is stable (size unchanged for 60 seconds)
5. If stable, proceed to DISTRIBUTING

This design prevents wasted context and API costs from idle waiting.

### PRIVATE-First Publishing

All YouTube uploads are PRIVATE by default. This prevents:

- Publishing incomplete or incorrect content
- SEO damage from deleted/re-uploaded videos
- Errors visible to subscribers before review

The REVIEW state allows fixes before making content public:
- Fix title, description, thumbnail
- Re-run research if needed
- Abort and delete if unsalvageable

Only after explicit human approval does content become public.

### Quality Gates

**Translation Validation (Critical Gate)**

The `validate_translation.py` script prevents the most catastrophic error: publishing an incomplete translation.

What it checks:
1. Last translated chunk appears near end of source text
2. No significant untranslated content remains
3. No truncation indicators (sentences ending mid-thought)
4. Metadata consistency with project state

This gate exists because a previous incident published a text missing Section VI and half of Section V. The translation looked complete but had been silently truncated.

**Research-to-Blog Validation**

The `validate_blog.py` script ensures the blog contains actual research content, not AI-generated summaries.

What it checks:
1. Citations from research.md appear in blog
2. Distinctive phrases from research appear in blog
3. No generic AI-filler phrases
4. Word count matches research depth

This gate exists because the agent once "wrote a blog post about" a topic instead of extracting the actual research content. The result had zero citations from the research file.

## Data Model

### Project State

Each project has a single canonical state file:

```json
{
  "project_id": "de-trinitate-20251214",
  "state": "TRANSLATING",
  "created_at": "2025-12-14T10:00:00Z",
  "updated_at": "2025-12-14T12:30:00Z",

  "source": {
    "volume": "042",
    "title_latin": "De Trinitate",
    "title_english": "On the Trinity",
    "author": "Augustine of Hippo",
    "century": 5,
    "estimated_duration_minutes": 45
  },

  "research": {
    "completed_at": "2025-12-14T10:30:00Z",
    "word_count": 2500,
    "citations_count": 12
  },

  "translation": {
    "completed_at": null,
    "chunk_count": null,
    "validation": {
      "passed": null,
      "checked_at": null
    }
  },

  "audio": { ... },
  "video": { ... },

  "youtube": {
    "video_id": null,
    "visibility": null,
    "thumbnail_set": false
  },

  "review": {
    "approved_at": null,
    "approved_by": null
  },

  "costs": {
    "research_usd": 1.23,
    "translation_usd": 0,
    "total_usd": 1.23
  },

  "notes": [
    {"timestamp": "...", "note": "State transition: SELECTING → RESEARCHING"},
    {"timestamp": "...", "note": "Deep research completed: 2500 words, 12 citations"}
  ]
}
```

The state file is the single source of truth. The agent reads it to know what to do. Scripts update it to record progress. Validation scripts check it to enforce requirements.

### Translation Output Format

Translations are structured JSON for audio processing:

```json
{
  "metadata": {
    "title": "On the Trinity",
    "latin_title": "De Trinitate",
    "author": "Augustine of Hippo",
    "century": "5th century",
    "total_chunks": 150,
    "estimated_duration_minutes": 45
  },
  "chunks": [
    {
      "chunk_id": 1,
      "section_type": "chapter_heading",
      "speaker": "announcer",
      "chapter_title": "Book One: The Unity of the Trinity",
      "latin": "LIBER PRIMUS",
      "english": "Book One"
    },
    {
      "chunk_id": 2,
      "section_type": "body",
      "speaker": "narrator",
      "latin": "Lecturus haec quae de Trinitate...",
      "english": "The reader of these reflections on the Trinity..."
    }
  ]
}
```

**Speaker mapping for TTS:**
- `"announcer"` → `"echo"` voice (titles, headings)
- `"narrator"` → `"onyx"` voice (body text)

## Failures That Shaped This Architecture

### The Truncated Translation

**What happened:** The agent translated 60% of a document, generated audio, composed video, and uploaded it to YouTube. It reported "complete" because it had performed each pipeline step.

**Root cause:** No validation that translation covered the source text. The agent checked that files existed, not that they were correct.

**Fix:** Added `validate_translation.py` that checks if the last translated Latin appears near the end of the source. This became the gate between VALIDATING and GENERATING_AUDIO.

### The Fabricated Research

**What happened:** The research API failed. The agent, wanting to be helpful, wrote a "research.md" file summarizing its own knowledge. The blog post looked scholarly but contained zero citations from actual research.

**Root cause:** No validation that blog content came from research file. Format looked correct, but provenance was fabricated.

**Fix:** Added `validate_blog.py` that checks for distinctive phrases and citations from research.md. Added "No Bypass Policy" to agent instructions explicitly forbidding manual file creation.

### The Premature Publication

**What happened:** The agent uploaded a video as public. It had the wrong author attribution. It was indexed by Google within hours.

**Root cause:** The agent could upload as public. There was no architectural barrier.

**Fix:** Changed upload script to only support PRIVATE visibility. Added REVIEW state with explicit fix commands. Only human-invoked `review.py publish` command can change visibility.

### The Deleted Credentials

**What happened:** YouTube token showed "expired." The agent, trying to fix the problem, deleted the token file. This required manual browser re-authentication that couldn't be done headlessly.

**Root cause:** Agent interpreted "fixing" broadly. Deleting and regenerating works for many files, but not for OAuth tokens.

**Fix:** Added "Protected Files" section to agent instructions listing files that must never be deleted, with explanations of why.

### The Infinite Wait

**What happened:** Video encoding started. The agent waited. And waited. Context grew. API costs accumulated. Eventually the session timed out. On restart, the agent had no memory of the encoding job and started a new one.

**Root cause:** No concept of "operations that take longer than a session."

**Fix:** Created AWAITING_VIDEO parking state. Agent exits after starting encoding. Next session checks if video is complete. If not, exits again. No waiting, no context accumulation.

## Cost Model

Monthly budget: ~$50

Per-project costs:
- Deep research: $0.50-2.00 (depends on response length)
- Translation: $1-5 per 10 minutes of audio
- TTS audio: $0.50-2.00 per 10 minutes
- DALL-E cover: $0.04
- **Total: $3-10 for a typical 10-30 minute text**

Budget enforcement:
- Pre-flight estimate before translation
- Hard stop if cost > $15 (requires explicit approval)
- Cost tracking in project state and aggregate file

## Technology Stack

| Component | Technology |
|-----------|------------|
| Orchestration | Claude Code (CLI) |
| State management | JSON files |
| Research | OpenRouter API (deep research models) |
| Translation | Claude API (via OpenRouter) |
| Audio synthesis | OpenAI TTS |
| Video composition | FFmpeg |
| Publishing | YouTube Data API v3, Archive.org S3 API |
| Blog | Jekyll (GitHub Pages) |

The interesting part isn't the API integrations—it's how they're orchestrated through the state machine.

---

*For the patterns behind these design decisions, see [PATTERNS.md](PATTERNS.md).*
