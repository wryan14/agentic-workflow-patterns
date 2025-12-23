# Agentic Workflow Patterns

Architectural patterns for constraining AI agent behavior, extracted from a production system that has translated 200+ Latin patristic texts.

## The Problem

AI agents are unreliable across sessions. They:
- Skip steps or forget context between sessions
- Produce inconsistent output quality
- Conflate "understood the task" with "completed the task"
- Make irreversible mistakes before human review
- Hallucinate when they should follow explicit instructions

Better prompting doesn't solve this. The agent reinterprets prose instructions each session.

## The Solution

**Architectural constraints, not better prompts.**

This repository documents patterns learned from building a Latin-to-YouTube translation pipeline that has:
- Published 200+ translated texts from the 3rd-12th centuries
- Maintained $3-10 cost per translation
- Achieved zero incomplete publications
- Run for months with a single human operator

The intellectual contribution isn't the translation code—it's the patterns for making agentic workflows predictable.

## The Six Patterns

| Pattern | Problem Solved | Key Insight |
|---------|---------------|-------------|
| [State Machines Over Instructions](#1-state-machines-over-instructions) | Agent skips steps | Code reads state, not prose |
| [Hard Gates Over Checklists](#2-hard-gates-over-checklists) | Agent "forgets" validation | Exit code 1 blocks progression |
| [Parking States for Async](#3-parking-states-for-async) | Agent waits inefficiently | Design for session boundaries |
| [Private-First Publishing](#4-private-first-publishing) | Mistakes go live | Review buffer before public |
| [Templates Over Generation](#5-templates-over-generation) | Inconsistent output | Fill blanks, don't improvise |
| [Provenance Tracking](#6-provenance-tracking) | Hallucinated content | Validate source, not just format |

See [PATTERNS.md](PATTERNS.md) for detailed documentation of each pattern.

## Results

**Output:**
- [YouTube Channel](https://www.youtube.com/@bibliothecarius-modernus) — 200+ videos
- [Blog](https://bibliothecarius-modernus.github.io) — ~2,000 monthly readers
- [Translation Corpus](https://github.com/wryan14/Latin-Patristic-Texts) — Open source translations

**Whitepaper:** [DOI 10.5281/zenodo.18002473](https://doi.org/10.5281/zenodo.18002473)

**Economics:**
- Translation cost: $3-10 per text (research + translation + TTS + image generation)
- Time per text: 30-60 minutes of agent work, 5-10 minutes human review
- Failure rate since implementing patterns: Zero incomplete publications

## Lessons Learned (The Hard Way)

Each pattern exists because of a specific failure:

**State machine** — The agent translated half a document, generated audio, and uploaded it to YouTube. It reported "complete" because it had done something for each step. There was no concept of "translation covers the whole source."

**Hard gates** — The agent validated its own work by checking if files existed, not if they were correct. A validation script that could return "failed" was the only thing it couldn't rationalize away.

**Parking states** — Video encoding takes 30-60 minutes. The agent would wait, consuming context and API costs, then lose context and restart. Now it exits cleanly and resumes next session.

**Private-first** — The first few translations went directly to public. One had the wrong author attribution. One was missing the final chapter. Both were indexed by Google before anyone noticed.

**Templates** — The agent would "improve" YouTube descriptions each time, adding sections we didn't want, removing sections we did. A template with placeholders eliminated creative interpretation.

**Provenance tracking** — The agent wrote "research" by summarizing its own knowledge rather than using the actual research API output. The blog looked scholarly but contained zero citations from the research. Now we validate that specific phrases from research.md appear in the blog.

## How to Use This

This is a **case study**, not a framework to install.

1. Read [PATTERNS.md](PATTERNS.md) to understand each pattern
2. Read [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) to see what effective agent prompts look like
3. Read [ARCHITECTURE.md](ARCHITECTURE.md) for the system design
4. Look at [examples/](examples/) for concrete implementations

Then adapt the patterns to your domain. The state machine for translation won't match yours, but the principle—code enforces workflow, not instructions—transfers.

## Repository Structure

```
agentic-workflow-patterns/
├── README.md                 # This file
├── PATTERNS.md               # The six core patterns in detail
├── AGENT_INSTRUCTIONS.md     # Annotated example of agent instructions
├── ARCHITECTURE.md           # System design with state diagram
├── IMPLEMENTATION_NOTES.md   # Brief notes on components not shown
├── LICENSE                   # CC0 (public domain)
└── examples/
    ├── project_state.json    # Example state file structure
    └── validation_gate.py    # Example validation script
```

## What's Not Here

This repository contains **patterns and documentation**, not operational code.

The production system includes 15+ scripts for:
- Audio synthesis (OpenAI TTS with voice selection)
- Video composition (FFmpeg with Latin text overlays)
- YouTube upload (Data API v3, OAuth)
- Archive.org upload (S3 API)
- Blog generation (Jekyll)
- Research (OpenRouter deep research models)

These are standard API integrations. The interesting part—and what's documented here—is how they're orchestrated.

## License

[CC0 1.0 Universal (Public Domain Dedication)](https://creativecommons.org/publicdomain/zero/1.0/)

Copy, modify, and use freely. No attribution required.

---

*"The goal is not to make agents smarter. The goal is to make agent behavior predictable."*
