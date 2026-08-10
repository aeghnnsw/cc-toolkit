---
name: handoff
version: 1.0.0
description: Create a concise handoff document so a fresh Claude Code or Codex session can continue the current work. Use when the user asks to hand off work, transfer context, resume later, compact a conversation, or prepare another agent or session to take over.
argument-hint: What should the next session focus on?
disable-model-invocation: true
---

# Handoff

Create a Markdown handoff in the operating system's temporary directory, never
in the current workspace unless the user requests another location. Use a
clear, time-stamped filename.

Include these sections:

- **Goal**: what the user is trying to achieve.
- **Current state**: completed work and repository state when relevant.
- **Decisions**: important choices and constraints.
- **Next steps**: concrete actions in priority order.
- **Verification and blockers**: checks already run, failures, risks, or needed
  input.
- **Relevant artifacts**: paths, commits, issues, or URLs to consult.
- **Suggested skills**: available skills that may help the next session and why.

Reference existing specs, plans, diffs, commits, and other artifacts instead of
copying their contents. If the user gives a focus for the next session, tailor
the handoff to it. Redact secrets and sensitive personal information.

After saving the file, report its exact path to the user.
