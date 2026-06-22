# ZHealth Knowledge Split and Context System Implementation Checklist

Date: 2026-06-15  
Status: implementation proposal  
Primary repo: `hivemind-chat`  
Related repos: `hivemind-orchestrator`, ZHealth corpus volume at `/Volumes/Public/ZHealth`  
Scope of this document: finish the split ZHealth knowledge/context system without editing frontend or backend code in this pass.

## Goal

Finish the move from one opaque `ZHealth Corpus` Open WebUI Knowledge object to an inspectable, rebuildable, source-grounded context system:

```text
/Volumes/Public/ZHealth
  -> scripts/zhealth_corpus/build_openwebui_corpus.py
  -> /Volumes/Public/ZHealth/.hivemind/openwebui-corpus
  -> scripts/zhealth_corpus/sync_openwebui_corpus.py
  -> one Open WebUI Knowledge base per course/chapter
  -> orchestrator memory/context APIs
  -> Hivemind chat context packet and side-menu provenance
```

The compatibility bridge is the current split Open WebUI Knowledge sync. The durable target is orchestrator-owned context planning, deterministic source identity, and visible provenance in Hivemind Chat.

## Non-Goals and Guardrails

- Do not configure standard OpenAI, Anthropic, or other foundation-model API keys. This system must use the existing Hivemind local model and host CLI authentication pattern.
- Do not edit application frontend/backend code while executing this documentation pass.
- Keep user or teammate work intact. Do not revert unrelated edits.
- Treat Open WebUI Knowledge as compatibility and migration infrastructure, not the canonical long-term source of truth.
- Keep source roots explicit and bounded. Do not add arbitrary filesystem browsing.

## Workstream Ownership

- **Workstream A: Corpus Builder**
  - Owner: corpus/data sub-agent.
  - Scope: transcript discovery, topic splitting, front matter, manifests, deterministic rebuilds.

- **Workstream B: Open WebUI Split Knowledge Sync**
  - Owner: Open WebUI integration sub-agent.
  - Scope: local embedding settings, knowledge creation, diff/cleanup behavior, dry-run summaries, sync logs.

- **Workstream C: Orchestrator Source Registry and Memory**
  - Owner: orchestrator backend sub-agent.
  - Scope: source IDs, version IDs, chunk cleanup, metadata filters, memory search health.

- **Workstream D: Context Planner Contract**
  - Owner: context/retrieval sub-agent.
  - Scope: `/v1/context/*` API shape, packet assembly, query generation, ranking, budgets, evaluation cases.

- **Workstream E: Chat UX Contract**
  - Owner: chat/frontend sub-agent.
  - Scope: side-menu expectations, visible provenance, approval modes, telemetry events. Implementation happens later outside this docs-only pass.

- **Workstream F: QA and Release**
  - Owner: QA/release sub-agent.
  - Scope: test matrix, rollback, migration checklist, production dry run, acceptance signoff.

## Phase 0: Baseline and Safety

1. Confirm the live corpus source root is `/Volumes/Public/ZHealth`.
2. Confirm the generated output root is `/Volumes/Public/ZHealth/.hivemind/openwebui-corpus`.
3. Confirm the local Open WebUI API URL for this environment, expected default `http://localhost:3002/api/v1`.
4. Confirm the orchestrator project/instance that owns the ZHealth corpus mount.
5. Record the current Open WebUI Knowledge objects whose names start with `ZHealth /`.
6. Record whether the legacy monolithic `ZHealth Corpus` Knowledge object still exists and whether any model is auto-attached to it.
7. Export or screenshot the current Knowledge list before sync changes.
8. Save the current generated manifest if it exists:

```bash
cp /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.$(date +%Y%m%d-%H%M%S).bak.json
```

9. Confirm Open WebUI credentials are available through local install credentials or environment variables:

```bash
printenv OPENWEBUI_EMAIL
printenv OPENWEBUI_PASSWORD
printenv OPENWEBUI_TOKEN
```

10. Verify no normal provider API keys are required or added:

```bash
env | sort | rg 'OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|MISTRAL_API_KEY' || true
```

**Verification gate 0**

- The source root exists and is readable.
- The output root is either absent or contains only generated corpus artifacts.
- Open WebUI is reachable locally.
- No new foundation-model API key configuration is introduced.
- Rollback artifacts for the current manifest/Knowledge state are captured.

## Phase 1: Corpus Builder Hardening

11. Run a limited parser smoke test:

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --limit 3 \
  --output /tmp/zhealth-openwebui-corpus-test
```

12. Inspect the test manifest:

```bash
python3 -m json.tool /tmp/zhealth-openwebui-corpus-test/openwebui-sync-manifest.json | sed -n '1,160p'
```

13. Confirm generated Markdown contains YAML front matter with `corpus`, `source_system`, `course`, `chapter`, `episode`, `topic_id`, `start_time`, and `end_time`.
14. Confirm Markdown body includes source transcript and source media references.
15. Confirm transcript preference order works: `.smoothed.named.verbose.json`, `.smoothed.verbose.json`, `.verbose.json`, `.smoothed.named.txt`, `.smoothed.txt`, `.txt`.
16. Confirm `.hivemind` output directories are skipped during source discovery.
17. Confirm duplicate episode slugs are disambiguated with stable IDs.
18. Confirm topic splitting produces bounded chunks using `--target-words` and `--max-seconds`.
19. Confirm source paths with spaces and punctuation create stable slugs.
20. Run a full rebuild to the canonical output path:

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --output /Volumes/Public/ZHealth/.hivemind/openwebui-corpus
```

21. Summarize the rebuilt corpus:

```bash
python3 - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path('/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json').read_text())
print('episodes:', manifest['episode_count'])
print('files:', manifest['file_count'])
print('groups:', len(manifest['groups']))
for group in manifest['groups'][:20]:
    print(group['key'], len(group['manifest']), group['knowledge_name'])
PY
```

**Verification gate 1**

- Limited and full builds complete without exceptions.
- `file_count` and `group` counts are plausible for the corpus.
- Every generated file has a checksum and local path in the manifest.
- Re-running the builder without source changes produces the same group keys and stable topic IDs for unchanged topics.

## Phase 2: Open WebUI Split Knowledge Sync

22. Ensure Open WebUI is running:

```bash
curl -fsS http://localhost:3002/api/v1/health || curl -fsS http://localhost:3002/health
```

23. Configure local sentence-transformers embeddings without provider API keys:

```bash
python3 - <<'PY'
import json, os, urllib.request

base = 'http://localhost:3002/api/v1'
email = os.environ['OPENWEBUI_EMAIL']
password = os.environ['OPENWEBUI_PASSWORD']
token = json.load(urllib.request.urlopen(urllib.request.Request(
    base + '/auths/signin',
    data=json.dumps({'email': email, 'password': password}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)))['token']

urllib.request.urlopen(urllib.request.Request(
    base + '/retrieval/embedding/update',
    data=json.dumps({
        'RAG_EMBEDDING_ENGINE': '',
        'RAG_EMBEDDING_MODEL': 'sentence-transformers/all-MiniLM-L6-v2',
        'RAG_EMBEDDING_BATCH_SIZE': 64,
        'ENABLE_ASYNC_EMBEDDING': True,
        'RAG_EMBEDDING_CONCURRENT_REQUESTS': 4,
        'openai_config': None,
        'ollama_config': None,
        'azure_openai_config': None,
    }).encode(),
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    method='POST',
))
print('updated local embedding settings')
PY
```

24. Run a split-sync dry run:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --dry-run
```

25. Sync one small group first:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --group mindless-mobility/day01
```

26. If the selected group key differs, list available group keys:

```bash
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json').read_text())
for group in manifest['groups']:
    print(group['key'])
PY
```

27. Verify the single group appears in Open WebUI Knowledge with nested directories.
28. Verify one uploaded file reaches `completed` processing status.
29. Run a second dry run and confirm the already-synced group reports unmodified files.
30. Run the full split sync:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs
```

31. Save the full sync summary:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --dry-run | tee /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/post-sync-dry-run.json
```

**Verification gate 2**

- Dry run produces expected create/add/modify/delete counts.
- One-group sync completes before full sync.
- Full sync completes with no file processing failures.
- Post-sync dry run reports mostly or entirely unmodified files.
- Open WebUI Knowledge is split by course/chapter, not dependent on one monolithic object.

## Phase 3: Orchestrator Source Registry and Memory Path

32. Define canonical source identity:
    - `profile`: `zhealth`
    - `root_id`: `zhealth-corpus`
    - `source_id`: hash of `profile`, `root_id`, normalized relative path
    - `source_version_id`: hash of `source_id` and content checksum
33. Add or confirm source registry fields for path, checksum, mtime, size, indexed status, default tier, and metadata.
34. Add or confirm chunk metadata includes `source_id`, `source_version_id`, `chunk_index`, `chunk_total`, `text_hash`, course, chapter, episode, topic, timecodes, and source transcript.
35. Replace random-only chunk identity with deterministic or cleanup-aware chunk lifecycle.
36. Ensure reindexing a changed source deletes or supersedes old chunks.
37. Ensure deleted source files become inactive or removed from search.
38. Confirm `/data/corpus/.manifest.jsonl` or replacement registry can represent stale/deleted/failed states.
39. Confirm corpus watch skips generated `.hivemind` output to avoid ingest loops.
40. Publish or re-publish a representative corpus file through orchestrator ingestion.
41. Verify memory health:

```bash
curl -fsS http://localhost:8080/v1/memory/health | python3 -m json.tool
```

42. Test memory search against ZHealth metadata:

```bash
curl -fsS http://localhost:8080/v1/memory/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "pain is an output",
    "tier": "truth",
    "top_k": 8,
    "filters": {
      "source_profile": "zhealth"
    }
  }' | python3 -m json.tool
```

**Verification gate 3**

- The same source can be rebuilt/reindexed without duplicate active chunks.
- Memory search can filter to ZHealth sources.
- Search results include human-readable source path/title and provenance metadata.
- Failed extraction/indexing states are visible and retryable.

## Phase 4: Context Planner Contract

43. Specify `POST /v1/context/plan` request/response schema and align it with the proposed `HivemindContextPacket`.
44. Specify `POST /v1/context/search` for direct side-menu and manual workflows.
45. Specify `GET /v1/context/sources` for browse/filter UI.
46. Specify `POST /v1/context/reindex` for source, directory, or profile reindexing.
47. Specify `DELETE /v1/context/sources/{source_id}` or equivalent deactivation semantics.
48. Define context modes: `off`, `suggest`, and `auto`.
49. Define task classifier rules for newsletter, email sequence, marketing, research, and general chat.
50. Define negative rules so unrelated UI/code/general prompts do not pull ZHealth context.
51. Define generated query strategy for ZHealth writing prompts.
52. Define ranking policy: tier weighting, metadata match, recency if available, diversity by episode/course, and optional reranking.
53. Define compression policy to trim excerpts to the requested token budget.
54. Define provenance text included in prompts: title, path, time range, source type, and reason selected.
55. Create a golden evaluation prompt set with at least:
    - "Draft a newsletter about pain as output."
    - "Find Eric's explanation of visual targeting."
    - "Use vestibular course transcripts only."
    - "Summarize this chat without adding corpus context."
    - "Write a sales email using the July newsletter arc."
56. For each evaluation prompt, define expected source families and forbidden source families.
57. Define packet persistence rules so "used in last request" can be displayed later.

**Verification gate 4**

- Context planner schemas are stable enough for parallel frontend/backend implementation.
- Evaluation prompts produce relevant sources in suggest mode.
- Non-ZHealth prompts do not include ZHealth context.
- Packet token estimates are under budget and include provenance.

## Phase 5: Chat UX Contract and Side-Menu Integration

58. Confirm the side menu should show Map, Context, Corpus, and later Tools tabs.
59. Confirm `showConversationMinimap` remains backward compatible until settings migration is complete.
60. Define UI state names for `showHivemindSideMenu`, `hivemindSideMenuPinned`, `hivemindSideMenuWidth`, `hivemindSideMenuActiveTab`, and `hivemindContextMode`.
61. Define Context tab states: empty, suggesting, approved, auto-included, error, stale packet.
62. Define Corpus tab filters: profile, course, chapter, episode, source type, speaker, date, topic, tier, indexed status.
63. Define actions: pin source, remove source, approve packet, reject packet, search, browse, reindex source, open source details.
64. Define prompt-send behavior in `suggest` mode: block for approval or allow send without context after explicit user choice.
65. Define prompt-send behavior in `auto` mode: include high-confidence packet and show "used in last request."
66. Define mobile behavior: no dense minimap by default; use drawer or sheet for context/source inspection.
67. Define telemetry/debug events for packet creation, source approval, source removal, search, and errors.

**Verification gate 5**

- UX contract is implementable without scattering context controls through the chat stream.
- User can inspect what was used, why it was selected, and where it came from.
- User can turn automatic context off.
- Side-menu behavior does not depend on Open WebUI Knowledge as the canonical source.

## Phase 6: End-to-End QA and Release

68. Run full corpus rebuild.
69. Run split Knowledge dry run.
70. Run full split Knowledge sync.
71. Run post-sync dry run and save output.
72. Run orchestrator memory health check.
73. Run five golden context planner prompts in suggest mode.
74. Run five golden context planner prompts in auto mode if enabled.
75. Run negative tests for unrelated prompts.
76. Verify source provenance appears in the context packet and prompt payload.
77. Verify old chunks are cleaned up after editing one test source and rebuilding/reindexing.
78. Verify deleted generated files are removed or marked stale during sync cleanup.
79. Verify the legacy monolithic Knowledge object is no longer required for new ZHealth writing requests.
80. Document any remaining manual Open WebUI attachment path for emergency compatibility.
81. Prepare release notes explaining user-visible behavior and rollback.

**Verification gate 6**

- All rebuild/sync/search/context checks pass.
- QA signs off that the system produces useful ZHealth writing context and avoids unrelated context injection.
- Rollback path has been tested or dry-run.

## Exact Command Runbook

### Rebuild Corpus

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --output /Volumes/Public/ZHealth/.hivemind/openwebui-corpus
```

### Rebuild Corpus With Tighter Topic Chunks

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --output /Volumes/Public/ZHealth/.hivemind/openwebui-corpus \
  --target-words 650 \
  --max-seconds 420
```

### Build Smoke Test

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --limit 3 \
  --output /tmp/zhealth-openwebui-corpus-test
```

### List Sync Groups

```bash
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json').read_text())
for group in manifest['groups']:
    print(group['key'])
PY
```

### Configure Local Embeddings

```bash
python3 - <<'PY'
import json, os, urllib.request

base = 'http://localhost:3002/api/v1'
email = os.environ['OPENWEBUI_EMAIL']
password = os.environ['OPENWEBUI_PASSWORD']
token = json.load(urllib.request.urlopen(urllib.request.Request(
    base + '/auths/signin',
    data=json.dumps({'email': email, 'password': password}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)))['token']

urllib.request.urlopen(urllib.request.Request(
    base + '/retrieval/embedding/update',
    data=json.dumps({
        'RAG_EMBEDDING_ENGINE': '',
        'RAG_EMBEDDING_MODEL': 'sentence-transformers/all-MiniLM-L6-v2',
        'RAG_EMBEDDING_BATCH_SIZE': 64,
        'ENABLE_ASYNC_EMBEDDING': True,
        'RAG_EMBEDDING_CONCURRENT_REQUESTS': 4,
        'openai_config': None,
        'ollama_config': None,
        'azure_openai_config': None,
    }).encode(),
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    method='POST',
))
print('updated local embedding settings')
PY
```

### Split Sync Dry Run

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --dry-run
```

### Sync One Group

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --group mindless-mobility/day01
```

### Full Split Sync

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs
```

### Sync With Token Instead of Password

```bash
OPENWEBUI_TOKEN="$OPENWEBUI_TOKEN" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs
```

### Orchestrator Memory Health

```bash
curl -fsS http://localhost:8080/v1/memory/health | python3 -m json.tool
```

### Orchestrator Memory Search Smoke Test

```bash
curl -fsS http://localhost:8080/v1/memory/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "pain is an output",
    "tier": "truth",
    "top_k": 8,
    "filters": {
      "source_profile": "zhealth"
    }
  }' | python3 -m json.tool
```

### Post-Sync Audit Summary

```bash
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json').read_text())
print(json.dumps({
    'source_root': manifest['source_root'],
    'output_root': manifest['output_root'],
    'episode_count': manifest['episode_count'],
    'file_count': manifest['file_count'],
    'group_count': len(manifest['groups']),
    'largest_groups': sorted(
        [(len(group['manifest']), group['key']) for group in manifest['groups']],
        reverse=True,
    )[:20],
}, indent=2))
PY
```

## Risks

- Open WebUI sync endpoints may differ by version, causing diff, cleanup, directory, or upload calls to fail.
- Full sync can take a long time because each changed file waits for processing.
- Generated topic boundaries may be too coarse or too fine for writing workflows.
- Current orchestrator chunk IDs may create duplicate active chunks until deterministic cleanup is implemented.
- Metadata filter names may not yet match between generated Markdown, Open WebUI file metadata, and orchestrator memory records.
- A legacy model or prompt may still auto-attach the monolithic `ZHealth Corpus` object.
- Context auto mode can over-trigger and inject ZHealth excerpts into unrelated conversations.
- Large corpus rebuilds can produce many modified files if the topic policy changes.
- Local embedding model availability may differ across machines.
- Knowledge deletion/cleanup errors can leave stale files visible in Open WebUI.

## Rollback Plan

1. Turn Hivemind context mode to `off` or equivalent feature flag.
2. Stop using split Knowledge objects for new requests.
3. Re-attach the legacy monolithic `ZHealth Corpus` Knowledge object manually if a user workflow needs immediate continuity.
4. Restore the prior generated manifest if the rebuild policy caused excessive churn:

```bash
cp /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.YYYYMMDD-HHMMSS.bak.json \
  /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json
```

5. Run sync dry run to identify delete/modify fallout before applying:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --dry-run
```

6. If orchestrator memory reindexing introduced bad chunks, disable the `zhealth` source profile in context planning while leaving low-level memory intact.
7. If a specific source causes failures, mark that source inactive or exclude its group from sync using `--group` on known-good groups only.
8. Preserve split Knowledge bases until the legacy fallback is confirmed, then clean up only after signoff.

## Acceptance Criteria

- The corpus can be rebuilt from `/Volumes/Public/ZHealth` with one documented command.
- The generated manifest groups files by course/chapter and contains stable checksums.
- Split Knowledge sync can be dry-run, single-group synced, fully synced, and audited.
- No standard foundation-model API keys are added or required.
- Orchestrator search can retrieve ZHealth sources with provenance metadata.
- Context planner contracts cover suggest and auto modes, negative triggers, token budgets, and source provenance.
- The chat UX contract gives users a clear way to inspect, approve, remove, and disable context.
- Rollback can restore the previous manifest or temporarily fall back to legacy Knowledge attachment.
