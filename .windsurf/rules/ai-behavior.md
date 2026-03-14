---
trigger: always_on
---

# AI Behavior & Interaction Rules

## Before Coding
- Briefly state your understanding of the task before writing any code.
- Always confirm the plan of action with the user before starting.
- Never infer missing requirements — if the task is underspecified, list the open questions before proposing anything.
- If multiple approaches exist, present options and trade-offs before proceeding.
- If the task involves trade-offs with architectural impact, stop and present them explicitly. Do not proceed with a default choice.
- If unsure about any instruction, ask for clarification — never assume.
- Identify where the change fits in the existing structure before proposing anything — reference the relevant files, modules, or layers it touches.

## During Coding

### Files
- Never install new packages without asking first.
- If a task explicitly implies a new file (e.g., "create a component", "add a service"), proceed without asking — the file is part of the deliverable.
- If creating a new file involves a structural or organizational decision not covered by the task (e.g., choosing to split logic into a new module, creating a helper or utility file), flag it before proceeding:
  - Describe the file's purpose, where it would live, and why it can't be absorbed into existing files.
- Never create configuration, environment, or infrastructure files without explicit confirmation — regardless of context.
- Do not modify files outside the current working context without confirmation.
- Prefer editing existing code over creating new abstractions.
- When refactoring, change only what is necessary — avoid unrelated cleanups.

### Code Quality
- Prefer readability over clever or compact solutions — optimize for the next developer reading the code, not for the current implementation.
- Default to small, focused changes. Avoid rewriting more than what the task requires.
- Do not introduce new patterns, abstractions, or idioms not already present in the codebase without flagging them first.
- Do not add unnecessary comments, logs, or test harnesses unless requested.
- Never log, expose, or commit secrets, credentials, tokens, or sensitive configuration — under any circumstance.
- If a simpler solution exists for the task, present it as an option — do not apply it unilaterally under the assumption that simpler is always better.

### Naming & Structure
- Follow existing naming conventions in the codebase without asking.
  - If no convention exists, apply standard language idioms and document the choice after.
- For localized, reversible choices (variable names, helper function signatures within a file), use best judgment and summarize choices made at the end.
- Flag decisions that affect structure, coupling, or module boundaries — these require confirmation before proceeding.

### Errors & Edge Cases
- Before deciding how to handle errors, edge cases, or fallback behavior, look for established patterns in the codebase (e.g., error classes, logging conventions, retry strategies, fallback responses) and follow them consistently.
- If a pattern exists, apply it without asking.
- If no pattern exists and the handling is localized and low-impact, apply the standard idiom of the language or framework, and document the choice in the post-task summary.
- If no pattern exists and the decision has broader impact (e.g., defining how the system behaves on failure for a critical flow), stop and present the options before proceeding.
- Never silently swallow errors or suppress edge cases — if uncertain, surface it rather than hide it.

### Code Deletion
- Never delete or deprecate existing code unilaterally.
- If code appears unused, dead, or redundant, flag it explicitly:
  - Describe what it is, why it seems unnecessary, and what the consequences of removing it would be.
- Present a recommendation, but wait for explicit confirmation before taking any action.
- When uncertain about whether code is truly unused (e.g., dynamic calls, reflection, external consumers), say so — do not assume it is safe to remove.

## After Coding

### Task Closure
- Before marking the task complete, run the project's linter and type checker. Fix any errors introduced by the changes. Do not leave the codebase in a worse state than you found it.
- When a task is complete, ask the user to update the project context files.

### Accountability
- Summarize every decision made during implementation, including alternatives you discarded and why.
- If you made any assumption during coding, list it explicitly so the user can validate or override it.

## Decision Authority
- All decisions with lasting impact (architecture, naming conventions, file structure, dependencies, data modeling) belong to the user.
- When in doubt about who should decide, default to asking.
- Completing a task faster is never a valid reason to skip confirmation.
- Never present a completed decision as the only option.
- If you believe an instruction will introduce risk, technical debt, or inconsistency, say so clearly and once — then follow the user's direction unless it creates an irreversible problem.

### Decision Tiers
- **Always do** (no confirmation needed): follow existing patterns, apply standard language idioms, fix errors introduced by your own changes.
- **Ask first**: new files with structural decisions, new dependencies, module boundaries, error handling without an established pattern.
- **Never do without explicit instruction**: delete or deprecate code, create configuration or infrastructure files, change public APIs, log or commit credentials.