# AGENTS.md — Luna AI Autonomous Agent Protocol

This repository is governed by the Luna AI Multi-Agent Architecture.

## Roles & Responsibilities

- **Accio (Local Orchestrator & Engineer):** Manages local execution, filesystem diffs, environment configuration, server lifecycles, and verification.
- **Claude (Lead Architect & UI/Design Lead):** Owns UI/UX simplicity, layout ergonomics, prompt engineering, and core module logic design.
- **Manus (Autonomous Research & Flow Execution):** Performs deep web research, library benchmarking, and asynchronous flow planning.
- **Cline (VS Code In-Editor Agent):** Executes localized surgical refactoring and code completions within the developer's IDE using OpenRouter / local LLMs.

## Core Operational Rules

1. **Targeted Diff Policy:** Avoid full-file rewrites on large files (`index.html`, `luna_server.py`). Always locate target code blocks via search/grep and perform surgical edits.
2. **Zero-Token Waste:** Never run blind tests or loops in background. Provide single-line PowerShell verification commands.
3. **No Credential Exposure:** Never print, log, or commit `.env`, API keys, or secret tokens.
4. **Clean Git Tree:** Implementations, tests, documentation, and assets must reside in their respective designated directories (`docs/`, `tests/`, `scripts/`, `assets/`, `static/`).
