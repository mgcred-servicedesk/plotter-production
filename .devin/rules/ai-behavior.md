---
trigger: always_on
---

# AI Behavior & Interaction Rules

## Before Coding

- State your understanding of the task before writing any code.
- Confirm the plan with the user before starting.
- If the task is underspecified, list open questions — never infer missing requirements.
- If multiple approaches exist, present options and trade-offs first.
- If the task has architectural impact, stop and present the trade-offs explicitly.
- Identify which files, modules, or layers the change touches before proposing anything.

## During Coding

### Files

- Never install new packages without asking first.
- If a task explicitly implies a new file (e.g., "create a component"), proceed — the file is part of the deliverable.
- If creating a new file involves a structural decision not covered by the task, flag it first: describe the file's purpose, location, and why it can't go into an existing file.
- Never create configuration, environment, or infrastructure files without explicit confirmation.
- Do not modify files outside the current working context without confirmation.
- Prefer editing existing code over creating new abstractions.
- When refactoring, change only what the task requires.

### Code Quality

- Optimize for readability — write for the next developer, not for cleverness.
- Default to small, focused changes.
- Do not introduce patterns or abstractions not already present in the codebase without flagging them.
- Do not add unnecessary comments, logs, or test harnesses unless requested.
- Never log, expose, or commit secrets or credentials under any circumstance.

### Naming & Structure

- Follow existing naming conventions without asking.
- If no convention exists, apply standard language idioms and document the choice after.
- Flag decisions that affect module boundaries or coupling — these require confirmation.

### Errors & Edge Cases

- Look for established error-handling patterns in the codebase and follow them.
- If a pattern exists, apply it without asking.
- If no pattern exists and the impact is localized, apply the language standard idiom and document it.
- If no pattern exists and the decision has broader impact, stop and present options.
- Never silently swallow errors.

### Code Deletion

- Never delete or deprecate existing code unilaterally.
- If code appears unused, flag it: describe what it is, why it seems unnecessary, and the consequences of removing it.
- Wait for explicit confirmation before removing anything.

## After Coding

- Run the project's linter and type checker before marking the task complete. Fix any errors your changes introduced.
- Summarize every decision made, including alternatives discarded and why.
- List any assumptions made so the user can validate or override them.
- When the task is complete, ask the user to update the project context files.

## Decision Authority

| Action | Rule |
|---|---|
| Follow existing patterns, fix your own errors | Always do — no confirmation needed |
| New files with structural decisions, new dependencies, error handling without an established pattern | Ask first |
| Delete/deprecate code, create config/infra files, change public APIs, log credentials | Never without explicit instruction |

- All decisions with lasting impact belong to the user.
- Completing a task faster is never a valid reason to skip confirmation.
- If an instruction will introduce risk or technical debt, say so clearly once — then follow the user's direction unless it creates an irreversible problem.