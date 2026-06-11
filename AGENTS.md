# AGENTS.md

Guidance for human and AI contributors working in this repository.

## 1. Purpose

This repository, `hivemind-chat`, is the Hivemind Open WebUI branch used by `hivemind-orchestrator` as the main browser chat surface.

## 2. Core Engineering Rules

1. **Never use, try to use, or go down the rabbit hole in this project of trying to get regular API keys to work for any of the foundation model services.** The system strictly intends on using the host machine's CLI interfaces (e.g., Claude Code, Codex, Hermes, OpenClaw) and their pre-authenticated credentials synced from the host. Do not configure standard API keys (e.g., OpenAI or Anthropic API keys) directly.
