# Hivemind Chat

This repository is the Hivemind-owned Open WebUI branch used by
`hivemind-orchestrator` as the only browser chat surface.

Upstream base:

- Repository: https://github.com/open-webui/open-webui
- Branch created from upstream commit: 90f4b4fcd
- Local branch: `hivemind/main`

The first migration keeps Open WebUI's runtime shape intact and lets the
orchestrator build or run this repository as `hivemind-chat:dev`. Hivemind
specific UI and MCP changes should land here instead of patching the upstream
container image in the orchestrator.
