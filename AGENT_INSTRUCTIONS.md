# Agent Instructions: An Annotated Example

This document is an annotated version of the agent instructions used in a production Latin translation pipeline. The annotations explain **why** each section exists and what makes effective agent instructions different from typical prompts.

> **Key insight:** These aren't "prompts" in the traditional sense. They're operating procedures that treat the agent as an unreliable executor that needs explicit constraints at every step.

---

## The Full Instructions (Annotated)

### Header

```markdown
# Project Name - Agent Reference

Latin-to-YouTube translation pipeline. Read `config/workspace.json` for paths.
```

> **Why this works:** The first line orients the agent to its role. "Agent Reference" signals this is operational documentation, not a conversation starter. The second line immediately points to external configuration—the agent shouldn't guess paths.

---

### Protected Files Section

```markdown
## CRITICAL: Protected Files - NEVER DELETE

**The following files are painful to reconfigure. NEVER delete, modify, or remove them:**

| File | Purpose | If Missing |
|------|---------|------------|
| `youtube_token.pickle` | YouTube OAuth credentials | Requires browser-based re-authentication |
| `client_secrets.json` | Google API client config | Must download from Google Cloud Console |

**If an OAuth token shows "expired" or "revoked":**
1. Do NOT delete the token file
2. Report the error to the user
3. The refresh token may still work, or the user can re-authenticate
4. NEVER attempt to "fix" auth issues by deleting credential files

**Why this matters:** These tokens require interactive browser authentication
that cannot be completed in headless environments. Deleting them breaks the
pipeline until the user manually re-authenticates.
```

> **Why this exists:** Agents try to "fix" problems. A common failure mode is deleting files that look corrupted or expired, then failing because the replacement requires human interaction. This section explicitly blocks that behavior with an explanation of *why*.
>
> **Pattern:** When you have files the agent must never touch, list them explicitly with consequences. "If Missing" makes the cost concrete.

---

### No Bypass Policy

```markdown
## CRITICAL: No Bypass Policy

**If any pipeline script fails, STOP and report the error.**

- Do NOT create files manually to work around failures
- Do NOT proceed to the next state when a script fails
- Do NOT set `model: "manual_research"` or `created_by: "manual"`
- Do NOT write research.md, description.txt, or translation.json directly

**Why:** Manual bypasses introduce hallucinated content that propagates
through the pipeline. Validation scripts check provenance and will reject
manually created files.

**When a script fails:**
1. Report the exact error to the user
2. Add a note to project state: `add_note(project, f"FAILED: {error}")`
3. Save project state and STOP
4. Wait for user to fix the underlying issue
```

> **Why this exists:** Agents are helpful. When something fails, they try workarounds. The most common workaround is creating the expected output manually, which bypasses the actual work the script was supposed to do.
>
> **Example failure this prevents:** The research API failed. The agent, wanting to be helpful, wrote a "research.md" file using its own knowledge. The blog post looked scholarly but contained zero actual research citations. This section makes manual file creation explicitly forbidden.
>
> **Pattern:** List specific bypass behaviors and explicitly prohibit them. "Do NOT create files manually" is more effective than "always use the scripts."

---

### First Action Every Session

```markdown
## First Action Every Session

```python
from pipeline.state import get_active_projects

projects = get_active_projects()
if projects:
    # Resume from current state
    project = projects[0]
    print(f"Resuming: {project['project_id']} in state {project['state']}")
else:
    # No active work - await user request
    print("No active projects. Awaiting user request.")
```
```

> **Why this exists:** The agent's first instinct is to respond to what the user just said. But there may be work in progress from a previous session. This forces the agent to check persistent state before doing anything else.
>
> **Pattern:** Define a mandatory first action that orients the agent to external state. The agent reads reality before acting on assumptions.

---

### State Machine

```markdown
## State Machine

```
SELECTING → RESEARCHING → TRANSLATING → VALIDATING → GENERATING_AUDIO →
GENERATING_VIDEO → AWAITING_VIDEO → DISTRIBUTING → PUBLISHING → REVIEW → COMPLETE
                                                                      ↘ CANCELLED
```

### Transition Requirements

| From | To | Requirements |
|------|-----|--------------|
| SELECTING | RESEARCHING | `source.title_latin` set |
| RESEARCHING | TRANSLATING | `research.completed_at` and `research.file_path` set |
| TRANSLATING | VALIDATING | `translation.file_path` set |
| VALIDATING | GENERATING_AUDIO | `translation.validation.passed = true` |
| GENERATING_AUDIO | GENERATING_VIDEO | `audio.completed_at` set |
| GENERATING_VIDEO | AWAITING_VIDEO | `video.job_started_at` set |
| AWAITING_VIDEO | DISTRIBUTING | `video.completed_at` set |
| DISTRIBUTING | PUBLISHING | `archive_org.url`, `github_url`, and `blog_url` set |
| PUBLISHING | REVIEW | `youtube.video_id` set and `youtube.thumbnail_set = true` |
| REVIEW | COMPLETE | `review.approved_at` set |
```

> **Why this exists:** This is the core constraint. The agent can't skip from TRANSLATING to PUBLISHING because the transition table doesn't allow it. The requirements column specifies what must be true for each transition.
>
> **Critical detail:** `translation.validation.passed = true` means the validation script must have run AND returned exit code 0. The agent can't self-certify.
>
> **Pattern:** Define transitions as a data structure, not prose. Tables are harder to reinterpret than paragraphs.

---

### Commands by State

```markdown
## Commands by State

### VALIDATING
```bash
python validation/validate_translation.py source.txt translation.json --project PROJECT_ID
```
- Exit 0: validation passed → auto-transitions to GENERATING_AUDIO
- Exit 1: fix translation and re-run

### GENERATING_VIDEO
```bash
python pipeline/compose_video.py translation.json audio.mp3 video.mp4 --project PROJECT_ID
```
**STOP SESSION after starting.** Video encoding takes 30-60 minutes.
Output: "Video encoding started. Run `python pipeline/state.py check-video PROJECT_ID`
to check status."

### AWAITING_VIDEO
Check video stability (size unchanged for 60 seconds):
```bash
python pipeline/state.py check-video PROJECT_ID
```
- If stable: `transition_state(project, "DISTRIBUTING")`
- If not stable: wait and check again
```

> **Why this exists:** Each state has exactly one correct action. No interpretation needed. The agent looks up the state, runs the command, reads the result.
>
> **Note the STOP instruction:** At GENERATING_VIDEO, the agent must exit the session. This is a parking state. Without explicit instruction to stop, the agent would wait 30-60 minutes consuming context.
>
> **Pattern:** Give exact commands, not descriptions. `python validation/validate_translation.py source.txt translation.json` leaves no room for "I'll validate by checking if the file looks right."

---

### Critical Constraints

```markdown
## Critical Constraints

1. **Never skip validation** - `validate_translation.py` must pass before audio
2. **Never upload as PUBLIC** - All YouTube uploads are PRIVATE; user publishes manually
3. **Always stop at AWAITING_VIDEO** - End session after starting video encoding
4. **Always update state** - Call `save_project()` or `transition_state()` after each phase
5. **Never proceed on gate failure** - If exit code is 1, fix the issue first
6. **Budget check before translation** - If cost > $15, require explicit approval
```

> **Why this exists:** These are the invariants—rules that must never be broken regardless of context. They're stated separately from the state-by-state instructions so they're visible at a glance.
>
> **Note "Never upload as PUBLIC":** There is no exception case. There is no "--force" flag. The architecture makes public upload impossible from the agent's context.
>
> **Pattern:** Separate invariants from procedures. Invariants are always-true constraints. Procedures are state-dependent.

---

### Session End Protocol

```markdown
## Session End Protocol

When stopping (especially at AWAITING_VIDEO):
```
════════════════════════════════════════════════════════════════
SESSION PAUSED
════════════════════════════════════════════════════════════════
Project: {project_id}
State: {current_state}
Next action: {what to do next session}

To check status:
  python pipeline/state.py show {project_id}

To resume:
  [specific command for next step]
════════════════════════════════════════════════════════════════
```
```

> **Why this exists:** The next session starts with no memory of this one. The session end message is documentation for the future agent (and the human). It explicitly states what to do next.
>
> **Pattern:** Define what "ending a session" looks like. The agent shouldn't just stop—it should leave a clear status report and resumption instructions.

---

### Error Handling

```markdown
## Error Handling

| Error | Action |
|-------|--------|
| Validation fails | Check error message, fix issue, re-run validation |
| API error | Check API key, retry once, report if persistent |
| File not found | Verify paths in workspace.json, check output_directory |
| State transition blocked | Read error message for missing requirements |
| Budget exceeded | Stop and report to user |
| YouTube upload fails | Check OAuth token, re-authenticate if needed |

On any unrecoverable error:
1. `add_note(project, f"ERROR: {description}")`
2. `save_project(project)`
3. Report error to user with project state
4. Do NOT transition to CANCELLED without user approval
```

> **Why this exists:** Without explicit error handling, the agent will improvise. Improvisation during errors is how you get deleted credential files and manually-created bypasses. This table defines the correct response to each error type.
>
> **Note "Do NOT transition to CANCELLED":** The agent might decide a project is hopeless and cancel it. This prevents that—only humans can cancel.
>
> **Pattern:** Define error responses as explicitly as success responses. Errors are when agents do the most damage.

---

## What Makes This Different

### It's Operating Procedure, Not Prompting

Traditional prompts try to make the agent understand. These instructions try to make the agent predictable. The difference:

| Traditional Prompt | Operating Procedure |
|-------------------|---------------------|
| "Validate the translation carefully" | "Run `validate_translation.py`. Exit 0 = proceed. Exit 1 = stop." |
| "Don't publish until ready" | "All uploads are PRIVATE. No exceptions. No flags." |
| "Handle long operations gracefully" | "STOP SESSION at AWAITING_VIDEO. Exit and resume next session." |
| "Report errors clearly" | "On error: add_note(), save_project(), report, STOP." |

### It Assumes Failure

Every constraint exists because of a past failure. "Do NOT create files manually" exists because the agent created files manually. "Do NOT delete token files" exists because the agent deleted token files.

The instructions don't assume the agent will follow them perfectly. They assume the agent will try to be helpful in ways that break things, and they explicitly block those ways.

### It's Versioned and Tested

These instructions evolve. When a new failure mode appears, a new constraint gets added. The instructions are in the repository, version-controlled, and tested by running the pipeline.

Bad instructions get discovered when the agent does the wrong thing. Good instructions prevent the wrong thing from being possible.

---

## Adapting This to Your Domain

1. **Start with failures.** What has your agent done wrong? Each failure becomes a constraint.

2. **Use external state.** Don't rely on the agent remembering. File, database, API—something persistent.

3. **Give exact commands.** Not "validate the output" but "run this script, check exit code."

4. **Define error responses.** What should happen when things fail? Be as explicit as the happy path.

5. **Block helpful improvisation.** The agent will try workarounds. List them and forbid them.

6. **Make constraints structural.** "Never upload as public" is weaker than "there is no public upload flag."

The goal isn't an agent that understands. The goal is an agent that does the same thing every time.
