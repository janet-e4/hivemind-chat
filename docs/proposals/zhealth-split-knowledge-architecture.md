# ZHealth Split-Knowledge Architecture

Date: 2026-06-15  
Status: proposal  
Primary repo: `hivemind-chat`  
Related repos: `hivemind-orchestrator`  
Scope: final architecture and runbook for ZHealth split knowledge, context selection, verification, rollback, and repair.

## Summary

ZHealth should no longer depend on one large, opaque Open WebUI Knowledge object. The final shape is a deterministic split corpus that keeps source hierarchy visible:

```text
/Volumes/Public/ZHealth
  -> generated Open WebUI corpus
  -> one Knowledge base per course/chapter
  -> episode directories
  -> topic markdown files
  -> Open WebUI/Qdrant retrieval compatibility
  -> Hivemind auto-context planning with visible provenance
```

Open WebUI Knowledge remains the compatibility surface users can inspect and attach manually. Hivemind context planning should treat the generated corpus metadata and orchestrator memory search as the durable context system.

Do not configure normal OpenAI, Anthropic, Gemini, or other foundation-model API keys for this workflow. Use existing local Open WebUI credentials, local embeddings, orchestrator endpoints, and host-authenticated CLI paths.

## Corpus Hierarchy

The source hierarchy is normalized into this generated structure:

```text
course/
  chapter/
    episode/
      001-topic-title.md
      002-topic-title.md
```

The operational hierarchy is:

```text
chapter -> episode -> topic
```

In Open WebUI this maps as:

- Knowledge base: `ZHealth / {course} / {chapter}`
- Directory: `{episode}`
- File: `{topic_index}-{topic_slug}.md`

Each topic file should include YAML front matter with stable provenance:

- `course`, `chapter`, `episode`, `topic`
- `chapter_id`, `episode_id`, `topic_id`
- `start_time`, `end_time`
- source transcript path and source media path when available
- checksum/source identity fields from the sync manifest

Topic splitting must be deterministic. Rebuilding unchanged transcripts should preserve group keys, episode IDs, topic IDs, and file checksums.

## Open WebUI Visibility And Grants

Normal Open WebUI Knowledge visibility is SQL-driven:

- A visible collection requires a `knowledge` row with `id`, `user_id`, `name`, `description`, `created_at`, and `updated_at`.
- A visible file inside a collection requires a `file` row and a `knowledge_file` join row for that `knowledge_id` and `file_id`.
- Pending files may appear briefly when `file.meta.data.knowledge_id` matches and `file.data.status` is `pending` or `processing`, but completed files must be linked through `knowledge_file`.
- Do not rely on legacy `knowledge.data.file_ids`; current listing uses `knowledge_file`.
- Do not mark split collections with `meta.document=true`; the normal UI treats those as legacy document objects instead of editable collections.

Access is controlled through `access_grant` rows:

- Private/default: no grants; owner only.
- Public read: `principal_type=user`, `principal_id=*`, `permission=read`.
- User grant: `principal_type=user`, `principal_id={user_id}`, `permission=read|write`.
- Group grant: `principal_type=group`, `principal_id={group_id}`, `permission=read|write`.

The sync script should preserve existing grants unless an explicit repair or replacement mode is requested. For shared ZHealth access, prefer adding read grants and reserve write grants for maintainers.

## Qdrant Grouping

Open WebUI writes vector entries into logical collections:

- Each standalone uploaded file is first processed into `file-{file_id}`.
- Each split ZHealth Knowledge base is indexed into a collection named exactly by its Knowledge `id`.
- The system metadata collection `knowledge-bases` stores name/description embeddings for semantic KB discovery.

The grouping rule is one Open WebUI Knowledge base per course/chapter. This keeps Qdrant collections small enough to inspect and repair, avoids one monolithic `ZHealth Corpus`, and lets retrieval target a chapter before diversifying across episodes and topics.

Hivemind orchestrator memory may also maintain its own Qdrant tiers such as `truth` and `research`. In the final architecture:

- Open WebUI/Qdrant collections are the compatibility and manual-inspection layer.
- Orchestrator memory/context APIs are the durable auto-context layer.
- Both layers must carry compatible source metadata so results can be traced to course, chapter, episode, topic, and timestamp.

## Auto-Context Selection

Hivemind context planning should operate in three modes:

- `off`: never attach ZHealth context automatically.
- `suggest`: retrieve and show candidate context before the request is sent.
- `auto`: include only high-confidence context and show what was used after send.

Selection flow:

1. Classify the prompt.
2. Trigger ZHealth retrieval for newsletter, email, marketing, course, rehab, transcript, Dr. Cobb, ZHealth, or source-specific requests.
3. Do not trigger ZHealth retrieval for unrelated coding, UI, account, scheduling, or general chat requests.
4. Generate focused retrieval queries from the user request.
5. Apply metadata filters when the user names a course, chapter, episode, topic, or source family.
6. Search orchestrator memory first when available; fall back to Open WebUI split Knowledge for compatibility.
7. Rank by semantic match, metadata match, source tier, diversity by episode, and transcript provenance.
8. Build a context packet with excerpts, source title/path, time range, reason selected, and token estimate.
9. Persist enough packet metadata for the side menu to show "used in last request."

The model should receive a source-grounded context block, not a vague instruction to use the corpus.

## Verification Commands

Build smoke test:

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --limit 3 \
  --output /tmp/zhealth-openwebui-corpus-test
```

Full rebuild:

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --output /Volumes/Public/ZHealth/.hivemind/openwebui-corpus
```

Manifest summary:

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

Open WebUI health:

```bash
curl -fsS http://localhost:3002/api/v1/health || curl -fsS http://localhost:3002/health
```

Split sync dry run:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --dry-run
```

One-group sync:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs \
  --group mindless-mobility/day01
```

Full split sync:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs
```

Access audit:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --audit-access \
  --public-read
```

Orchestrator memory health:

```bash
curl -fsS http://localhost:8080/v1/memory/health | python3 -m json.tool
```

ZHealth memory search smoke test:

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

Guardrail check:

```bash
env | sort | rg 'OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|MISTRAL_API_KEY' || true
```

## Rollback And Repair

Fast rollback:

1. Set Hivemind context mode to `off`.
2. Stop attaching split ZHealth context automatically.
3. Reattach the legacy monolithic `ZHealth Corpus` Knowledge object only as an emergency manual fallback.
4. Leave split Knowledge objects in place until the fallback is confirmed.

Manifest rollback:

```bash
cp /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.YYYYMMDD-HHMMSS.bak.json \
  /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json
```

Then dry-run before applying:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --dry-run
```

Access repair:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --repair-access \
  --public-read
```

Clear accidental grants:

```bash
OPENWEBUI_EMAIL="$OPENWEBUI_EMAIL" OPENWEBUI_PASSWORD="$OPENWEBUI_PASSWORD" \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --repair-access \
  --clear-access-grants
```

Targeted content repair:

1. Rebuild the corpus.
2. List groups from the manifest.
3. Sync only the known-good group with `--group`.
4. Run the dry run again and confirm the affected group is unmodified.
5. If Open WebUI vectors are stale, reindex the affected Knowledge base from the UI or use the admin reindex route.

Orchestrator repair:

1. Disable the `zhealth` profile in context planning if bad chunks are being selected.
2. Reindex only the affected source, directory, or profile.
3. Confirm stale chunks are inactive or deleted.
4. Re-run the memory search smoke test and a negative non-ZHealth prompt.

## Acceptance Criteria

- Generated corpus follows chapter -> episode -> topic structure.
- Open WebUI shows editable `ZHealth / {course} / {chapter}` collections.
- File visibility comes from `knowledge_file`, not legacy data fields or vector-only state.
- Access grants can be audited, repaired, cleared, and verified.
- Qdrant grouping is split by course/chapter instead of one monolithic collection.
- Auto-context selection can be disabled, suggested, or included only on high-confidence ZHealth requests.
- Verification commands cover build, sync, visibility, grants, memory search, and key guardrails.
- Rollback can pause auto-context and restore or repair generated/synced state without source/frontend edits.
