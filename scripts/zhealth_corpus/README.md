# ZHealth Open WebUI Corpus Tools

These tools convert hivemind-stt output under `/Volumes/Public/ZHealth` into
Open WebUI-ready knowledge files.

## Shape

The generated corpus is organized as:

```text
course/chapter/episode/001-topic-label.md
course/chapter/episode/002-topic-label.md
```

Each Markdown file contains YAML front matter with stable IDs and source
metadata:

- `course`, `chapter`, `episode`, `topic`
- `chapter_id`, `episode_id`, `topic_id`
- `start_time`, `end_time`
- source transcript/media paths

The sync manifest groups files into one Open WebUI knowledge base per
course/chapter. In the current Qdrant integration, each Open WebUI knowledge
base maps to its own logical collection/tenant, so this avoids the unreliable
single monolithic `ZHealth Corpus` object.

## Build

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --source /Volumes/Public/ZHealth \
  --output /Volumes/Public/ZHealth/.hivemind/openwebui-corpus
```

For a quick parser test:

```bash
python3 scripts/zhealth_corpus/build_openwebui_corpus.py \
  --limit 3 \
  --output /tmp/zhealth-openwebui-corpus-test
```

## Sync

Use an Open WebUI session token, or pass local first-install credentials from
`hivemind-orchestrator make credentials`.

Before syncing, make sure Open WebUI RAG embeddings are local or otherwise
available. For this Hivemind setup, avoid normal foundation-model API keys and
prefer the bundled local sentence-transformers path:

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
PY
```

```bash
OPENWEBUI_EMAIL='...' OPENWEBUI_PASSWORD='...' \
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --manifest /Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json \
  --base-url http://localhost:3002/api/v1 \
  --create-missing-kbs
```

To sync only one chapter group:

```bash
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --group mindless-mobility/day01
```

### Access grants

By default the sync script keeps Open WebUI's safe private behavior: new
knowledge bases are created with no access grants, and existing knowledge base
grants are left unchanged.

To create or sync ZHealth knowledge bases with additional access grants:

```bash
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --create-missing-kbs \
  --public-read \
  --grant-user-email coach@example.com:both
```

`--public-read` adds `user:*:read`. `--grant-user-email` is repeatable and
accepts `email:read`, `email:write`, or `email:both`; `write` grants only write,
so use `both` when the user should be able to view and edit.

Requested grants are added while preserving existing grants. To make the target
policy exact, add `--replace-access-grants`. The script verifies the grants
returned by Open WebUI after an update and exits non-zero if server-side
permissions filtered out requested or preserved grants.

To audit without syncing files or changing access:

```bash
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --audit-access \
  --public-read \
  --group mindless-mobility/day01
```

To repair only access grants without syncing files:

```bash
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --repair-access \
  --public-read \
  --grant-user-email coach@example.com:read
```

To explicitly clear all access grants on the targeted ZHealth knowledge bases:

```bash
python3 scripts/zhealth_corpus/sync_openwebui_corpus.py \
  --repair-access \
  --clear-access-grants
```

## Notes

- These scripts do not configure standard OpenAI/Anthropic/etc. API keys.
- Topic splitting is deterministic and based on STT segment timing/word counts.
- Prefer `.smoothed.named.verbose.json` when present, then other verbose JSON,
  then smoothed text, then raw text.
