# Coding with Agentic AIs — Consolidated Best Practices

> Compiled from the AutoBrain / SignalSpace / Loom project archives.
> Sources: community research, published articles, academic papers, and hard-won lessons
> from 50+ AI-assisted development sessions across Kiro, Cursor, Claude Code, and Gemini.
>
> Last compiled: 2026-04-07

---

## Table of Contents

1. [The Core Problem: Why AI Agents Lose Fidelity](#1-the-core-problem-why-ai-agents-lose-fidelity)
2. [Context Rot — The Silent Killer](#2-context-rot--the-silent-killer)
3. [Summary Compression & The Lost Details Trap](#3-summary-compression--the-lost-details-trap)
4. [AI Memory Syndrome (AMS) — The Butterfly Effect](#4-ai-memory-syndrome-ams--the-butterfly-effect)
5. [The Steering System Framework](#5-the-steering-system-framework)
6. [Session Recovery & Progress Tracking](#6-session-recovery--progress-tracking)
7. [Coding Discipline Rules](#7-coding-discipline-rules)
8. [Anti-Patterns to Block](#8-anti-patterns-to-block)
9. [Prompt Templates & Recovery Routines](#9-prompt-templates--recovery-routines)
10. [Agent Memory Architecture — Technology Landscape](#10-agent-memory-architecture--technology-landscape)
11. [The Decision Framework: Continue / Compact / Clear](#11-the-decision-framework-continue--compact--clear)
12. [Master Dos and Don'ts](#12-master-dos-and-donts)
13. [Sources & References](#13-sources--references)

---

## 1. The Core Problem: Why AI Agents Lose Fidelity

AI coding agents suffer from three compounding problems that erode output quality over time:

### The Butterfly Effect of Hallucination
When a chat window hits its token limit and the agent summarizes the conversation:
1. The agent hallucinates slightly during "summarize your chat"
2. After multiple chat sessions, that small hallucination compounds
3. Initial intent gets lost, steering commands get summarized away
4. Architecture decisions silently change
5. After 20+ sessions, the agent is working on a different project than what was specified

This is not a single-point failure. It's a cascading degradation where each summarization
cycle introduces small errors that compound into architectural drift.

### The Three Failure Modes
1. **Context Rot** — The agent's ability to recall early instructions degrades as the chat grows
2. **Summary Compression** — Technical details get lossy-compressed during context rollover
3. **Memory Loss** — Decisions, constraints, and steering commands vanish across sessions

### Why This Happens (Research Findings)
- Adding just 4,000 tokens of irrelevant context causes LLM accuracy to drop from 70-75% down to 55-60% (Stanford study)
- Models pay close attention to information at the beginning and end of their context window, but the middle gets fuzzy ("Lost in the Middle" — Liu et al., 2023)
- The reasoning behind decisions degrades faster than the decisions themselves
- LLM performance drops sharply after 60-70% of the advertised context window is consumed — not gradually, but in sudden cliffs

### Practical Context Window Budgets

| Model/Tool | Advertised Window | Reliable Window | Drop-off |
|---|---|---|---|
| Claude 4.5 Sonnet | 200K tokens | ~130K (65%) | Sudden |
| GPT-4.1 | 1M tokens | ~600-700K | Gradual then sharp |
| Cursor (practical) | Varies | 70K-120K | Auto-trims older files |
| Claude Code | 200K | ~130K, then auto-compact | Managed compression |


---

## 2. Context Rot — The Silent Killer

### What It Looks Like
You provide a brilliant multi-step plan. The AI executes Step 1 perfectly, but by Step 3
it starts hallucinating, forgetting file structures, and re-introducing bugs you fixed
an hour ago.

### Root Cause
The context window acts as the model's short-term memory. LLMs suffer from a "lost-in-the-middle"
effect: they prioritize tokens at the start and end of the prompt, while the middle gets foggy.
As the session accumulates debugging logs and failed attempts, the original architectural rules
are buried in noise.

### The Korean Output Incident (Real Case Study)
An LLM put entire ASAM document paths as "must read" instructions inside a steering file.
This caused the agent to load massive documents into context on every session, burning through
the window in minutes and causing cascading summarization that eventually produced output in
Korean after 10+ chat sessions. The lesson: steering files are control surfaces, not documentation.
Never embed large docs or "must read" instructions in always-loaded files.

### How to Detect Context Rot
- Agent starts looping on the same approach
- Agent re-introduces bugs that were already fixed
- Agent contradicts its own earlier statements
- Agent forgets file structures or architectural decisions
- Agent starts producing output in unexpected languages or formats
- The "Can I close this chat without anxiety?" test fails — if closing the session
  creates discomfort, your context is trapped inside a medium that was never designed
  to preserve it

### How to Fix It
1. Never let the AI hold the master plan in its chat history memory
2. Force it to maintain a physical Progress Tracker on your hard drive
3. Load that file at the start of every session
4. Treat context as a temporal, managed resource — not an infinite scroll
5. When rot is detected: save state to progress tracker, clear chat, start fresh

### The Working Memory Problem
The context problem in agentic systems is NOT an input problem — users arrive with short requests.
The problem emerges during work: the model reads files, runs commands, explores dead ends, backtracks.
Over a session, it generates hundreds of thousands of tokens of working context, most of which becomes
irrelevant the moment it's been used. This is fundamentally a working memory management problem,
not a data processing problem.

---

## 3. Summary Compression & The Lost Details Trap

### What It Looks Like
After a context rollover, the AI changes the architecture while believing it's still following
the plan. Example: swapping SharedArrayBuffer for postMessage because the summary compressed
the implementation detail. Or swapping a high-performance memory stream for a basic event listener.

### Root Cause
Lossy summarization. LLMs compress specific technical mandates into generic actions:
- "Send data via SharedArrayBuffer ring buffer" becomes "send data to main thread"
- "Using PKCE auth flow" becomes "using auth"
- "FalkorDB with Graphiti temporal edges" becomes "using a graph database"

Summaries track *where you are*, but they are NOT a reliable source of *what you should build*.

### The Fix: Re-Anchoring Routine
At the start of any new or summarized session:
1. Load the progress tracker
2. Re-read the current task from the spec/design files
3. Use the chat summary ONLY for "where am I" — never for "what to build"
4. Confirm technical requirements before writing code

### Mid-Session Intercept (When You Catch Drift)
When you notice the agent drifting from the plan:
1. Stop the agent immediately
2. Identify the specific detail that was lost
3. Point the agent to the physical spec file containing the correct detail
4. Have the agent acknowledge the correction before continuing

---

## 4. AI Memory Syndrome (AMS) — The Butterfly Effect

### The Problem Statement
> "I need another database for keeping track of the coding progress due to context window used up
> and then agent has to compress and summary the chat into new chat. I found out after certain
> amount of chat sessions, we lost fidelity, initial intent, minor details and small hallucination
> became big or part of the major requirement items."
> — Jerry Chen, Loom project creator

### How AMS Manifests
1. **Session 1-5**: Agent performs well, follows instructions precisely
2. **Session 5-10**: Small details start slipping — variable names change, minor constraints forgotten
3. **Session 10-20**: Architectural decisions silently shift — the agent "remembers" a different design
4. **Session 20+**: The agent is effectively working on a different project than what was specified

### Why Traditional Solutions Fail
- **Chat history**: Subject to summarization and compression — details get lost
- **Steering files**: Only work if they're concise and well-maintained — bloat causes its own problems
- **Progress trackers**: Only work if updated consistently — stale trackers are worse than none
- **Memory tools**: Only work if they capture the right information — most capture too much noise

### The Dual-Purpose Solution
The AMS layer should serve as both:
1. A project tracker that maintains session continuity across unlimited chat clears
2. A "digital twin" that learns the engineer's patterns, preferences, and coding style over time

Key requirements for an AMS solution:
- Session IDs to create relationships between chats
- Project IDs to track what's being built
- Objective IDs to maintain the "main thread" across scattered sessions
- Steering commands stored as PERMANENT constraints — never summarized away
- Raw transcripts preserved for audit
- Compact resumption context generated for new sessions

---

## 5. The Steering System Framework

### Architecture: The Three-Layer System

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: CORE STEERING (always loaded)                 │
│  Budget: <800 tokens                                    │
│  Contains: identity, architecture, hard rules, tool     │
│  commands, current phase. NO large docs or file paths.  │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────────┐   ┌─────────────────────────┐
│  Layer 2: DOMAIN  │   │  Layer 2: DOMAIN         │
│  SKILLS           │   │  SKILLS                  │
│  (conditional)    │   │  (conditional)           │
│  Budget: <1500    │   │  Budget: <1500           │
│  tokens each      │   │  tokens each             │
└───────────────────┘   └─────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Layer 3: SESSION CONTEXT (manual / ephemeral)          │
│  Progress tracker loaded explicitly at session start    │
│  Contains: current task, decisions, next steps          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  PASSIVE (never loaded by agent):                       │
│  DEV_JOURNEY.md — development history for humans only   │
└─────────────────────────────────────────────────────────┘
```

### Layer 1: Core Steering Rules
1. Token budget: under 800 tokens. Loaded on EVERY interaction.
2. No file paths to read — never instruct the agent to "read file X."
3. No embedded documentation — reference tools/databases, not raw docs.
4. Must contain: project identity, current phase, architecture summary, hard rules (max 5), tool commands.
5. Must NOT contain: full API specs, schema definitions, historical context, domain-specific knowledge.

### Layer 2: Domain Skill Files
1. Token budget: under 1500 tokens each.
2. Use conditional inclusion — loaded only when matching files are in context.
3. One skill per domain — don't combine unrelated domains.
4. Contains: domain terminology, tool commands, constraints, common pitfalls.

### Layer 3: Progress Tracker
1. Manual inclusion — loaded only when explicitly referenced.
2. Updated at the END of every significant work session.
3. Contains current state only — not history.
4. Must include: current task, status, key decisions (and WHY), blockers, next steps, technical details that would be lost in summarization.

### The Token Budget Rule
Every steering file, every "always include" document, every tool schema eats into your reasoning
budget. A typical steering file costs 2,000-5,000 tokens. If you have 5 always-included files
at 3,000 tokens each, that's 15,000 tokens gone before the conversation starts.

### Five Design Patterns for Context Files
1. **Minimal** — Under 10 lines. For small projects. Only what's essential.
2. **Sectioned** — Separate "catastrophic if broken" rules from "style guidelines."
3. **Task-Focused** — Rewrite at session start. Three sections: "Today's task," "Files to touch," "Constraints."
4. **Hierarchical** — Root-level for project-wide, subdirectory-level for module-specific.
5. **Context Index** — Don't copy docs into the steering file. Use it as an index pointing to what to read.

### Adapting to Different Tools

| This Framework | Kiro | Claude Code | Cursor | GitHub Copilot |
|---|---|---|---|---|
| Core Steering | `.kiro/steering/project-core.md` (always) | `CLAUDE.md` at root | `.cursor/rules/core.mdc` (alwaysApply) | `AGENTS.md` at repo root |
| Domain Skills | `.kiro/steering/{domain}.md` (fileMatch) | Subdirectory `CLAUDE.md` | `.cursor/rules/{domain}.mdc` (autoAttached) | `.github/skills/{domain}/SKILL.md` |
| Progress Tracker | `.kiro/steering/progress-tracker.md` (manual) | `MEMORY.md` or manual file | `.cursor/rules/progress.mdc` (manual) | Manual file in AGENTS.md |


---

## 6. Session Recovery & Progress Tracking

### The Context Anchoring Principle
The test: "Could I close this conversation right now and start a new one without anxiety?"
If that creates discomfort, your context is trapped inside a medium that was never designed
to preserve it. Developers keep conversations running far longer than they should, not because
long sessions are productive, but because closing the session means losing everything. This
creates a vicious cycle where the longer you hold on, the less reliable the thing you're
holding on to becomes.

Solution: Externalize decisions, reasoning, and constraints to physical files. The conversation
should be disposable. The knowledge should be persistent.

### The Re-Anchoring Routine
At the start of any new or summarized session:
1. Load the progress tracker
2. Tell the agent: "Re-read the current task from the spec. Use the progress tracker for where we are, but consult the spec files for what to build."
3. This prevents the "lossy summarization" problem where technical details get compressed into generic descriptions.

### Progress Tracker Template
```markdown
# Progress Tracker — [Project Name]

Last updated: [date]

## Current Task
[What we're working on right now]

## Status
[Where we are in the current task]

## Key Decisions (This Session)
- [Decision 1 and WHY]
- [Decision 2 and WHY]

## Technical Details (Anti-Compression)
[Specific technical choices that MUST survive context rollover.
Example: "Using SharedArrayBuffer ring buffer, NOT postMessage"
Example: "Auth uses PKCE flow, NOT implicit grant"
Example: "DB migration uses blue-green deployment, NOT in-place"]

## Blockers
- [Blocker 1]

## Next Steps
1. [Next thing to do]
2. [After that]
```

### Progress Update Protocol
- At session start, read the progress tracker before doing substantive work.
- Update whenever a milestone completes, a design decision changes, a blocker changes, or the next steps change.
- Always update before summarizing, handing off, clearing context, or ending a long session.
- Keep it concise. Replace stale status and next steps instead of appending noisy chat summaries.
- Record decisions, status, blockers, and next steps. Do not use the progress file as a raw transcript dump.
- If chat state and the progress tracker disagree, refresh the progress file and treat it as the handoff source of truth.

### Session Protocol Pattern
Multiple sources converge on the same pattern: never let the AI hold the master plan in chat
history. Force it to write the plan to a physical file, and load that file at the start of
every session. The Session Protocol project (sessionprotocol.dev) formalizes this as a
"persistent knowledge graph of development work."

---

## 7. Coding Discipline Rules

### Rule 1: Zero-Skip Policy
Explicitly forbid the AI from using lazy placeholders:
- No `// ... implement logic here`
- No `// ... rest of the code`
- No `TODO` stubs where real logic should be
- No mock data where real integration should be

If you see placeholder code, stop the agent immediately. In AI-assisted coding, technical
debt accrues infinitely faster because the agent will build on top of the placeholder as
if it were real implementation.

### Rule 2: Plan-Implement-Run (PIR)
Every non-trivial task should follow this cycle:
1. **Plan** — Agent describes what it will do, which files it will touch, and what the expected outcome is. Human approves or corrects.
2. **Implement** — Agent writes the code. No placeholders.
3. **Run** — Agent runs tests, linter, or build to verify. Human confirms the app actually works.

Never skip the Run step. Code that "looks right" but hasn't been executed is an assumption,
not a deliverable.

### Rule 3: Rebuild Over Patching
If a component has been patched 3+ times in the same session and is still unstable,
don't let the agent stack another micro-patch. Instead:
1. Save the current state to the progress tracker
2. Document what this component SHOULD do (from the spec, not from the broken implementation)
3. Start a fresh chat session
4. Rebuild the component from scratch

Micro-patches create Jenga towers. A clean rebuild with fresh context is faster and more reliable.

### Rule 4: Debug-First, Don't Guess
When the agent encounters a bug, it should NOT immediately guess the fix. Instead:
1. Add targeted debug/log statements after key operations
2. Run the code and review the output
3. Only then propose a fix based on evidence

This prevents the "fix-break-fix" loop where the agent introduces new bugs while
guessing at the cause of the original one.

### Rule 5: Gap Analysis Before Integration
When integrating a complex library or external system:
1. List the exact methods, types, and APIs required from the library
2. Compare against what the current codebase has
3. Identify what's missing, what's stubbed, and what's wrong
4. Get human approval before writing integration code

Never let the agent integrate multiple complex libraries in a single session.
One at a time, module by module.

### Rule 6: Module-by-Module Integration
Never integrate multiple complex systems in one shot. Break the work into:
1. Gap analysis first
2. Implement one module at a time
3. Every phase must end with a task that wires components together and verifies the system runs end-to-end
4. Integration tasks are mandatory — a component directory is useless if the app doesn't run

### Rule 7: Keep Files Under 200 Lines
Break large modules into single-purpose files. This reduces the context cost of loading
any single file and makes it easier for the agent to reason about the code.

### Rule 8: Version Control as Safety Net
- Commit the moment code works. Don't wait for "the whole feature."
- Branch aggressively before risky changes.
- Revert immediately when the agent derails — don't try to fix forward.
- After 20+ messages of debugging without resolution: revert, save state, fresh session.
- Git is the only real undo button in AI-assisted development.

---

## 8. Anti-Patterns to Block

### 1. Mockup Shell Trap
**Symptom**: AI builds a structurally perfect shell but maps everything to placeholders or mock data.
**Cause**: AI gravitates toward the path of least resistance. Scaffolding a layout is easy; wiring real logic requires deep context.
**Fix**: Zero-Skip Policy. Stop the agent the moment you see a placeholder. Demand real components with a Demo Mode that proves they work.

### 2. Shallow Integration
**Symptom**: You ask the AI to integrate a complex library. It creates the file but writes hollow wrapper functions or uses mock data instead of actually calling the library's real methods.
**Cause**: Integrating multiple libraries at once overwhelms the context window. The AI panics and hallucinates generic function names.
**Fix**: Gap Analysis first, then module-by-module integration. Never integrate multiple complex libraries in a single session.

### 3. Components Built in Isolation
**Symptom**: AI builds beautiful individual components but never wires them into the running application. The app entry point still has default boilerplate.
**Cause**: Specs have tasks for every component but no task to compose them.
**Fix**: Every spec phase needs an explicit integration task at the end. Plus a steering rule that catches it automatically.

### 4. Lazy LLM Syndrome (Ingestion)
**Symptom**: When given massive documentation to read, the AI reports 100% success. But audits reveal blank fields, edge cases ignored, and hallucinated data.
**Cause**: Massive documents create "navigational noise" that bloats the context window. Without aggressive prompting, the AI acts as a pass-through filter.
**Fix**: Programmatic extraction (Python-first), verification receipts, and anti-pass-through rules. Force the AI to use its sandbox to parse structured files. Use a "Distillation Pyramid" to extract atomic insights.

### 5. Steering File Bloat
**Symptom**: After many sessions, the agent starts producing garbage output, wrong languages, or hallucinations.
**Cause**: Always-loaded steering files grew too large, or contain "must read" instructions pointing to massive documents.
**Fix**: Core steering < 800 tokens. No file paths. No embedded docs. Domain knowledge in conditional skill files only.

### 6. Monolithic Steering Files
One giant file with everything. Wastes tokens on irrelevant context every session.

### 7. Keeping Dead Context Alive
Failed approaches, old debugging attempts, superseded decisions — all still in the context window, consuming tokens and confusing the agent.

### 8. Mixing Instructions and History
Foundational rules must live in steering files, not in chat flow. Chat flow is subject to summarization and compression; steering files are not.

### 9. Trusting Chat Summaries for Technical Details
Summaries compress "SharedArrayBuffer ring buffer" into "post data to main thread." Never trust a summary for implementation specifics.

### 10. No Physical Save State
Relying on chat history as the only record of decisions and progress. When the chat is cleared, everything is lost.

### 11. Personas Don't Improve Code Quality
**Symptom**: You prefix prompts with "Act as a Senior Software Architect" expecting better code. The output sounds more confident but isn't more correct.
**Research Evidence**: Schulhoff et al. (OpenAI, Microsoft, Google, Princeton, Stanford) found role prompting has "little to no effect on correctness" for code generation. A study across 4 model families and 2,410 questions found personas did not improve performance. Learn Prompting tested 12 personas — the "idiot" persona outperformed the "genius" persona.
**Fix**: Don't use personas for coding agents. Use concrete context instead: relevant code, architecture decisions, constraints, explicit output format, few-shot examples, and domain skill files.


---

## 9. Prompt Templates & Recovery Routines

### Context Serialization / Save State (End of Session)
```
We are about to end this session. Please serialize our current state into progress.md.
Include the current task, status, key architectural decisions made, and the exact next
steps. Do not omit technical constraints. Be specific — "Using PKCE auth flow" not
"using auth."
```

### Re-Anchoring (Start of New/Summarized Session)
```
We are in a new context window. Before you write any code:
1. Re-read the current task description in [tasks.md / spec file].
2. Re-read the technical constraints in [design.md / relevant spec].
3. Confirm you have the EXACT technical requirements before continuing.
Use the chat summary ONLY to understand our progress and what task is next.
For ALL technical details, architectures, and APIs, consult the physical
spec files. Do not trust the summary for implementation specifics.
```

### Mid-Session Drift Intercept
```
Hold on. You intend to [describe wrong approach].
You have fallen victim to context summary compression. The summary lost a
critical detail.
Re-read [specific section] in [specific file]. The correct approach is
[describe correct approach]. Do NOT [describe wrong approach] because
[explain consequence].
Acknowledge this correction, re-read the file, then continue.
```

### Force Integration
```
In the previous execution, all components were built in isolation but the main
application entry point was never updated. We need to fix this now.
DIRECTIVE: Wire all built components into the actual running application entry point.
Do NOT generate new feature logic. Only import, instantiate, and connect the
components we already built. Then verify the app renders without errors.
```

### Rip Out Placeholders
```
You have fallen into the "Mockup Shell" trap. The app looks great but every
panel/route maps to a placeholder component with no real logic.
ZERO-SKIP POLICY: No // TODO, no // ... implement later, no mock JSON
where real logic should be. Every function must have real implementation.
Replace all placeholder components with ACTUAL implementations now.
```

### Gap Analysis Before Integration
```
Act as a Principal Integration Architect. We are entering the "Deep Integration" phase.
DIRECTIVE 1: Perform a Gap Analysis.
Review our current codebase against [library/API documentation]. List exactly:
- Which methods and types we need from the library
- Where our current code is faking it (stubs, mocks, placeholder wrappers)
- What's missing entirely
DIRECTIVE 2: Module-by-Module Plan.
Outline a numbered, phase-by-phase plan to integrate the critical parts first.
Do NOT write all the code at once.
Then STOP and ask me: "Shall I begin rewriting the [First Module] integration?"
```

### Debug-First (When Stuck on a Bug)
```
STOP. Do not guess the fix.
Add targeted debug/log statements after these key operations:
- [operation 1]
- [operation 2]
- [branch/condition to verify]
Run the code and show me the debug output. We will diagnose from evidence,
not speculation. Do not propose a fix until we review the logs.
```

### Trigger Rebuild (3+ Patches and Still Broken)
```
This component has been patched [N] times and is still unstable. We are
not going to patch it again.
DIRECTIVE:
1. Save the current state to the progress tracker
2. Document what this component SHOULD do (from the spec, not from the
   broken implementation)
3. I will start a fresh session and rebuild it from scratch
Write the spec for what this component needs to do, including:
- Inputs and outputs
- Error handling requirements
- Performance constraints
- Integration points with other components
```

### Verification Receipt (For Bulk Ingestion)
```
Parse the provided documentation using Python. For EVERY file, provide a
"Verification Receipt":
1. File path and total line count
2. "Middle Quote": a verbatim snippet from the exact middle of the file
3. "Logic Anchor": one specific technical constraint found ONLY in this file
If you cannot provide all three, you have not actually read the file.
```

### Audit Steering Files
```
Audit all steering files for context budget violations:
1. Check each file's word count (target: core < 600 words, skills < 1100 words)
2. Flag any "must read" or "always read" instructions pointing to external files
3. Flag any embedded documentation, schemas, or large code blocks
4. Flag any file with inclusion: always that contains domain-specific knowledge
5. Report total estimated token cost of all always-loaded files
The core steering file must be under 800 tokens. If it's over, identify what
should be moved to domain skill files or removed entirely.
```

---

## 10. Agent Memory Architecture — Technology Landscape

### The Four Memory Types
The field has converged on four memory types that map to human cognition:
1. **Working Memory** (short-term) — Current conversation context
2. **Procedural Memory** — How to do things (skills, patterns, workflows)
3. **Semantic Memory** — Facts and knowledge (domain data, architecture decisions)
4. **Episodic Memory** — What happened (session history, decision trails)

### The Dual-Layer Architecture (2026 Consensus)
- **Hot Path**: Recent messages + summarized graph state (fast, always available)
- **Cold Path**: Retrieval from persistent memory systems (slower, comprehensive)
- **Memory Node**: Synthesizes what to save after each turn

### Memory System Benchmarks (LongMemEval 2026)

| System | Score | Architecture | Self-Host | Best For |
|---|---|---|---|---|
| Hindsight | 91.4% | Multi-strategy hybrid | Yes (Docker) | Highest accuracy, reflect operation |
| SuperMemory | 81.6% | Memory + RAG | Enterprise only | Closed-source option |
| Zep/Graphiti | 63.8% | Temporal knowledge graph | Via Graphiti | Best temporal reasoning |
| Mem0 | 49.0% | Vector + knowledge graph | Yes (Apache 2.0) | Largest community, efficient |
| Letta (MemGPT) | N/A | OS-inspired tiered memory | Yes | Self-editing memory blocks |

### Key Findings from Research
- **Hindsight** (91.4% LongMemEval): Four parallel retrieval strategies — semantic search, BM25 keyword, entity graph traversal, temporal filtering — with cross-encoder reranking. First to break 90% barrier.
- **Zep/Graphiti**: Temporal knowledge graph where every fact carries validity windows (valid_from, valid_to, invalid_at). Best for "What was true at time X?" queries. Up to 18.5% accuracy improvement and 90% latency reduction vs full-context baselines.
- **Mem0 vs Graphiti efficiency** (arxiv 2601.07978): Mem0 significantly outperforms Graphiti in efficiency — faster loading, lower resource consumption. But accuracy differences were NOT statistically significant.
- **Beads** (Steve Yegge / Sourcegraph, 18.7K GitHub stars): Git-backed task memory that solves the "50 First Dates" problem — agents wake up with no memory of yesterday's work. Key insight: "Coding agents need to remember what solved problems, not just find similar content."

### The Distillation Pyramid (For Large Documentation)
When a project has massive documentation but no knowledge base:

```
        ┌───────────┐
        │  Steering  │  ← Layer 1: Core rules only (~800 tokens)
        │   Core     │
        ├───────────┤
        │  Domain    │  ← Layer 2: Key concepts per domain (~1500 tokens each)
        │  Skills    │
        ├───────────┤
        │ Technical  │  ← Distilled summaries: info-dense markdown files
        │ Abstracts  │
        ├───────────┤
        │ Knowledge  │  ← Indexed DB (RAG/SQLite/vector) for exact lookups
        │   Base     │
        ├───────────┤
        │   Raw      │  ← Original docs. Agent should NEVER read these directly.
        │   Docs     │
        └───────────┘
```

Each layer compresses the one below it. The agent should only ever interact with the
top layers, never the raw docs at the bottom.

### Context as a Finite Resource (Budget Thinking)
Three layers of compression compound independently:
1. **System prompt architecture** — 60-70% reduction via structural compression
2. **MCP output compression** — 94% reduction via relevance ranking
3. **Knowledge hoarding** — Converting discovery overhead into pre-loaded capability

A landmark study found models given 300 tokens of focused context outperformed models
given 113,000 tokens of unfiltered conversation.

---

## 11. The Decision Framework: Continue / Compact / Clear

### Continue When:
- Iterating on same feature
- Context below 50% consumed
- Mid-task with important debugging history
- Agent is still performing well

### Compact When:
- Context hits 70-75%
- Same task but long conversation
- Need to shed noise but keep decisions
- Agent starting to show minor drift

### Clear and Start Fresh When:
- Switching to unrelated task
- AI contradicts itself
- Debugging exceeds ~20 messages without resolution
- Completed a task and starting the next
- Agent is looping, hallucinating, or forgetting rules
- The "Can I close this chat without anxiety?" test fails

### The 20-Message Rule
If stuck for 20+ messages of debugging without resolution, save state, clear, start fresh.
Don't try to fix forward in a degraded context.


---

## 12. Master Dos and Don'ts

### DO 🟢
- **DO maintain a Zero-Skip Policy** — No `// TODO`, no `// ... implement later`, no placeholders
- **DO structure context beforehand** — Steering files, not chat instructions. Rules at the START of context.
- **DO manage context ruthlessly** — Close files you aren't working on. Use conditional steering.
- **DO rebuild over patching** — 3+ patches on same component? Scrap and rebuild in fresh session.
- **DO use Git as your safety net** — Commit the moment code works. Branch before risky changes.
- **DO test rendering frequently** — Force integration/glue code early. A component directory is useless if the app doesn't run.
- **DO use Demo Mode as a forcing function** — Simulated data that auto-starts proves the UI works.
- **DO dictate architecture upfront** — Put it in design.md immediately. Left alone, the AI defaults to the slowest, easiest approach.
- **DO demand Python code for ingestion** — If the AI doesn't show extraction code, assume it's hallucinating.
- **DO use the Plan-Implement-Run cycle** — Plan it, build it, verify it runs. Never skip Run.
- **DO externalize decisions to physical files** — The conversation should be disposable. The knowledge should be persistent.
- **DO use the "Can I close this chat?" test** — If closing creates anxiety, externalize what's in your head.
- **DO run milestone sanity checks** — Audit steering files, progress tracker, and knowledge sources at every phase boundary.
- **DO keep core steering under 800 tokens** — Every token there costs you on every interaction.
- **DO use conditional inclusion for domain knowledge** — Load only when relevant files are touched.

### DON'T 🔴
- **DON'T keep working in a degraded chat** — Looping, hallucinating, forgetting rules = context rot. Save state, clear, fresh session.
- **DON'T ask the AI to "build the whole feature"** — Types first, then backend, then UI. Tiny scopes.
- **DON'T accept placeholder code** — Debt accrues infinitely faster in AI-assisted coding.
- **DON'T mix instructions and history** — Architectural rules go in steering files, not chat flow.
- **DON'T trust chat summaries for technical details** — Re-anchor to spec files after every rollover.
- **DON'T let the AI test itself** — Specify starting state, declare unhappy paths, verify manually.
- **DON'T guess at bugs** — Debug-first: add logs, read output, then fix based on evidence.
- **DON'T embed docs in steering files** — Point to tools that retrieve docs. Never "must read [file]."
- **DON'T assume the AI read the documentation** — Force it to cite specific methods and files to prove it.
- **DON'T integrate multiple complex libraries in one session** — One at a time, module by module.
- **DON'T use personas for coding agents** — Research shows they waste tokens without improving correctness. Use concrete context.
- **DON'T let the AI hold the master plan in chat memory** — Write it to a physical file and load it each session.
- **DON'T keep dead context alive** — Failed approaches, old debugging attempts, superseded decisions — remove them.

---

## 13. Sources & References

### Community Research & Articles
- [SFAI Labs — Context Is the New Bottleneck](https://www.sfailabs.com/guides/how-to-manage-context-when-developing-with-ai)
- [Dead Neurons — Agentic Context Management](https://deadneurons.substack.com/p/agentic-context-management-why-the)
- [Martin Fowler — Context Anchoring](https://www.martinfowler.com/articles/reduce-friction-ai/context-anchoring.html)
- [32blog — CLAUDE.md Design Patterns](https://32blog.com/en/claude-code/claude-code-context-management-claude-md-patterns)
- [Blake Niemyjski — Agentic Driven Development](https://blakeniemyjski.com/blog/agentic-driven-development/)
- [Blake Crosley — Context Is the New Memory](https://blakecrosley.com/blog/context-is-the-new-memory)
- [Datalakehouse — Context Management Strategies for Claude Code](https://blog.datalakehouse.help/posts/2026-03-context-claude-code/)
- [Session Protocol](https://www.sessionprotocol.dev/docs)
- [Steve Yegge — Introducing Beads](https://steve-yegge.medium.com/introducing-beads-a-coding-agent-memory-system-637d7d92514a)
- [Oracle Developers — Agent Memory](https://blogs.oracle.com/developers/agent-memory-why-your-ai-has-amnesia-and-how-to-fix-it)
- [CSO Online — The Dark Side of Vibe Coding](https://www.csoonline.com/article/4053635/when-ai-nukes-your-database-the-dark-side-of-vibe-coding.html)
- [Cisco Security — Persistent Memory Compromise in Claude Code](https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code)

### Academic Papers
- Liu et al., 2023 — "Lost in the Middle: How Language Models Use Long Contexts"
- arxiv 2501.13956 — Zep: Temporal Knowledge Graph Architecture for Agent Memory
- arxiv 2504.19413 — Mem0: Scalable Long-Term Memory for AI Agents
- arxiv 2601.07978 — Mem0 vs Graphiti: Cost and Accuracy Comparison
- arxiv 2512.12818 — Hindsight: Building Agent Memory that Retains, Recalls, and Reflects
- arxiv 2511.06179 — MemoriesDB: Temporal-Semantic-Relational Memory Architecture
- arxiv 2410.05779 — LightRAG: Simple and Fast Retrieval-Augmented Generation
- arxiv 2404.16130 — Microsoft GraphRAG: From Local to Global
- arxiv 2603.11073 — Vibe Coding Experience Report
- Schulhoff et al. — Role Prompting has "little to no effect on correctness" for code generation

### Memory System & Tool References
- [Hindsight](https://vectorize.io/articles/best-ai-agent-memory-systems) — 91.4% LongMemEval
- [Zep/Graphiti](https://help.getzep.com/v2/graphiti/getting-started/overview) — Temporal knowledge graph
- [Mem0](https://mem0.ai/) — Vector + knowledge graph memory
- [Letta/MemGPT](https://www.letta.com/blog/our-next-phase) — OS-inspired tiered memory
- [Beads](https://github.com/steveyegge/beads) — Git-backed task memory (18.7K stars)
- [FalkorDB](https://github.com/FalkorDB/FalkorDB) — 496x faster than Neo4j at P99
- [Cognee](https://github.com/topoteretes/cognee) — Knowledge engine from diverse sources

### Project-Internal Sources
- `archived/Mastering Vibe Coding_ A Framework for AI Development Optimization.md` — Gemini framework
- `archived/VIBE_CODING_LESSONS_LEARNED.md` — 11 battle-tested lessons with prompt templates
- `archived/steeringSkill/01_RESEARCH_CONTEXT_MANAGEMENT.md` — Research compilation
- `archived/steeringSkill/02_STEERING_SYSTEM_FRAMEWORK.md` — Three-layer steering framework v2.1
- `archived/steeringSkill/DEV_JOURNEY.md` — Development journey log
- `research/agentic_memory_architecture_2026.md` — Comprehensive memory architecture research
- `research/loom_system_design_decisions.md` — Design decisions and rationale
- `.kiro/steering/loom-core.md` — Active Loom steering rules

---

## Milestone Sanity Check Protocol

Run this checklist at every major development milestone, after architecture changes,
after context rot failures, or before starting a new major feature.

```
[ ] 1. CORE STEERING ACCURACY
    - Does the "Current Phase" match reality?
    - Are the "Hard Rules" still the right rules?
    - Are the "Tool Commands" still correct?
    - Is the token budget still under 800 tokens?
    - Are there any file paths or large docs embedded? (REMOVE if yes)

[ ] 2. DOMAIN SKILLS RELEVANCE
    - Are all domain skill files still needed?
    - Do fileMatch patterns still match the right files?
    - Are there new domains that need skill files?
    - Is each skill still under 1500 tokens?

[ ] 3. PROGRESS TRACKER CURRENCY
    - Does it reflect the actual current state?
    - Are completed tasks removed (moved to DEV_JOURNEY)?
    - Are "Technical Details" still accurate?
    - Are "Next Steps" still the right next steps?

[ ] 4. KNOWLEDGE SOURCE HEALTH
    - If using a knowledge base: are the stats current?
    - Has the data been re-validated since last milestone?
    - If no knowledge base: should one be built now?

[ ] 5. DEV_JOURNEY UPDATED
    - Is this milestone logged?
    - Are steering changes documented?

[ ] 6. CONTEXT BUDGET AUDIT
    - Total tokens of always-loaded steering: ___ (target: <800)
    - Number of conditional skill files: ___
    - Estimated worst-case token load (all skills triggered): ___
    - Is total context budget under 15% of the model's window?
```

---

## The 15 Rules — Quick Reference

### Context Management (Anti-Rot)
1. Core steering < 800 tokens. Every token there costs you on every interaction.
2. Never embed docs in steering. Point to tools that retrieve docs on demand.
3. Use conditional inclusion. Domain knowledge loads only when relevant files are touched.
4. Progress tracker is manual. Load it explicitly at session start, not automatically.
5. Update steering at milestones, not continuously. Frequent changes cause drift.
6. History goes in DEV_JOURNEY, not in steering. Steering is current state only.
7. Test: "Can I close this chat without anxiety?" If no, externalize what's in your head.
8. After context rollover: re-anchor to spec files. Never trust the summary for technical details.
9. 20-message debugging rule. If stuck for 20+ messages, save state, clear, start fresh.
10. Sanity check at every milestone. Use the checklist above.

### Coding Discipline
11. Zero-Skip Policy. No placeholders, no TODOs, no `// ... rest of code`.
12. Plan-Implement-Run. Every task: plan it, build it, verify it runs. Never skip Run.
13. Rebuild over patching. 3+ patches on the same component? Scrap it, fresh session, rebuild.
14. Debug-first, don't guess. Add logs, read output, then fix. No speculative patches.
15. Commit early, branch often. Git is the only real undo button.

---

*Compiled April 7, 2026 from the AutoBrain / SignalSpace / Loom project archives.*
*This is a living document — update as new lessons are learned.*
