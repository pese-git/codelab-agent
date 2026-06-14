Here's the English translation in Markdown format.

# What is AGENTS.md

`AGENTS.md` is an instruction file for AI agents working with a repository.

Its purpose is similar to `README.md`, but the target audience is not human developers. Instead, it is intended for agent-based systems such as:

* OpenAI Codex
* Claude Code
* Cursor
* Gemini CLI
* Copilot Agents
* Other AI-assisted development tools

The file should help an agent:

* understand the project structure;
* run the project;
* execute validation checks;
* follow architectural constraints;
* adhere to established conventions;
* make changes safely.

---

# Core Principles

## 1. Specificity

Prefer specific instructions.

Bad:

```text
Write clean code.
```

Good:

```text
Use Ruff for formatting.
All public functions require type hints.
```

---

## 2. Verifiability

Every requirement should be verifiable.

Bad:

```text
Write high-quality tests.
```

Good:

```text
Run:

make test
```

---

## 3. Minimal Sufficiency

Include only information that helps the agent make decisions.

Avoid duplicating:

* API documentation;
* detailed business requirements;
* large architectural documents.

Use separate documents for that information.

---

## 4. Architecture Over Style

The most valuable information includes:

* architectural constraints;
* project structure;
* execution commands;
* testing requirements;
* security restrictions.

Formatting rules are usually enforced by linters and formatters.

---

# Recommended AGENTS.md Structure

```text
# AGENTS

## Project Overview

## Environment & Commands

## Repository Structure

## Architecture Constraints

## Coding Standards

## Testing Requirements

## Security Rules

## Git Workflow

## Agent Workflow

## Known Pitfalls

## Definition of Done
```

---

# Section Descriptions

## Project Overview

A brief description of the project.

Recommended content:

* project purpose;
* technology stack;
* major components;
* core domain entities.

Example:

```md
## Project Overview

ACP platform for AI agents.

Components:

- FastAPI backend
- ACP server
- Web UI
- PostgreSQL
```

---

## Environment & Commands

Development-related commands.

Recommended content:

* dependency installation;
* application startup;
* test execution;
* linting;
* full validation checks.

Example:

```md
## Environment & Commands

Install dependencies:

uv sync

Run application:

uv run python -m app

Run tests:

make test

Run lint:

make lint

Run all checks:

make check
```

---

## Repository Structure

Description of the repository layout.

Example:

```md
## Repository Structure

src/
tests/
docs/
scripts/
```

Optionally describe the purpose of each directory.

---

## Architecture Constraints

A key section for most projects.

Recommended content:

* system layers;
* allowed dependencies;
* prohibited dependencies;
* architectural restrictions.

Example:

```md
## Architecture Constraints

API -> Services -> Repositories

Reverse dependencies are prohibited.

Business logic belongs to services.

Routes must remain thin.
```

---

## Coding Standards

Code conventions and practices.

Example:

```md
## Coding Standards

- Use type hints.
- Avoid wildcard imports.
- Prefer dataclasses.
- Use async/await where appropriate.
```

---

## Testing Requirements

Testing expectations.

Example:

```md
## Testing Requirements

For every change:

- Add tests for new functionality.
- Update tests if behavior changes.
- Run make test.
```

---

## Security Rules

Security requirements.

Example:

```md
## Security Rules

Never:

- commit secrets;
- disable authentication;
- bypass authorization checks.

Always:

- validate external input;
- use parameterized queries.
```

---

## Git Workflow

Git conventions and requirements.

Example:

```md
## Git Workflow

Commit prefixes:

- feat:
- fix:
- refactor:
- docs:
- test:

Before commit:

- make format
- make lint
- make test
```

---

## Agent Workflow

Recommended workflow for AI agents.

Example:

```md
## Agent Workflow

Before making changes:

1. Read relevant code.
2. Read existing tests.
3. Understand the architecture.

Before completing a task:

1. Run checks.
2. Review the diff.
3. Verify tests.
```

---

## Known Pitfalls

Known project-specific caveats.

Example:

```md
## Known Pitfalls

- Registry loads only at startup.
- Generated files must not be edited manually.
- Database migrations are required for schema changes.
```

---

## Definition of Done

Task completion criteria.

Example:

```md
## Definition of Done

A task is complete only if:

- code builds;
- tests pass;
- lint passes;
- documentation is updated;
- no debug code remains.
```

---

# File Size Recommendations

Recommended size:

```text
50–150 lines
```

Acceptable size for large projects:

```text
up to 300 lines
```

If the file grows significantly larger, consider:

* moving details into separate documents;
* keeping only critical instructions in `AGENTS.md`.

---

# File Location

## Minimal Setup

```text
repo/
└── AGENTS.md
```

---

## Large Projects

```text
repo/
├── AGENTS.md
├── backend/
│   └── AGENTS.md
├── frontend/
│   └── AGENTS.md
└── infrastructure/
    └── AGENTS.md
```

---

# Instruction Inheritance

Recommended approach:

1. The root `AGENTS.md` contains global rules.
2. Local `AGENTS.md` files contain instructions specific to their area.
3. Local instructions refine or extend global instructions.
4. Avoid duplicating the same rules across multiple files.

---

# Anti-Patterns

Avoid:

* documenting the entire business logic;
* duplicating the README;
* embedding large architecture documents;
* using vague requirements without verification criteria;
* storing secrets or internal credentials.

Examples of poor instructions:

```text
Write clean code.
```

```text
Use best practices.
```

```text
Think carefully before coding.
```

Such statements do not provide actionable guidance to an agent.

---

# Summary

A good `AGENTS.md` should answer the following questions:

1. What is this project?
2. How do I run it?
3. How do I validate changes?
4. What architectural constraints exist?
5. What coding conventions should be followed?
6. When is a task considered complete?

If an agent can confidently answer these questions after reading the file, then the `AGENTS.md` is serving its purpose.
