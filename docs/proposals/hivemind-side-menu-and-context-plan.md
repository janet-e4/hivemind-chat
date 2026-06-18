# Hivemind Chat Side Menu and Context Plan

Date: 2026-06-14  
Status: proposal  
Primary repo: `hivemind-chat`  
Related repos surveyed: `hivemind-orchestrator`, `hivemind-paperclip`

## Executive Summary

Hivemind should treat the conversation screen as two coordinated surfaces:

1. The main chat stream remains the place where the user writes and reads.
2. A new Hivemind side menu on the right edge of the conversation pane becomes the home for navigation, context, corpus discovery, tools, and provenance.

The existing conversation minimap is a good first resident for this side menu. It already has the right mental model: a compact always-visible conversation map that helps the user jump, inspect, and act without losing their place. Instead of keeping it as a floating widget, it should become the rail and first tab of a self-contained Hivemind side menu.

For retrieval and writing context, Hivemind should stop relying on one monolithic Open WebUI Knowledge object such as "ZHealth Corpus" as the canonical source. Open WebUI Knowledge can stay as a manual or legacy compatibility layer, but the reliable path should be:

`filesystem corpus -> orchestrator ingestion -> structured memory/search -> chat-side context planner -> visible side-menu approval/provenance -> model prompt`

This matches the multi-project architecture already present in `hivemind-orchestrator`. The orchestrator already watches a transcript/corpus directory, publishes ingestion jobs, embeds chunks into Qdrant-backed memory tiers, and exposes a memory search API. The missing pieces are standard source identity, query-time context planning, deterministic reindexing, a chat UI that lets the user see and steer what was selected, and a migration path away from brittle monolithic Knowledge attachments.

## Research Inputs

### Local Hivemind Chat Findings

The Hivemind-specific chat customizations in this repo are smaller and more targetable than they first appear. The meaningful custom work is concentrated around conversation UI, file payload handling, and model capability tagging.

Key local files:

- `src/lib/components/chat/Chat.svelte`
  - Renders the chat pane and currently mounts `ConversationMinimap` inside the message area.
  - The page already has a horizontal `PaneGroup` where chat and `ChatControls` are separate panes.
  - This means the new Hivemind side menu can live inside the conversation pane without immediately rewriting the whole chat controls layout.

- `src/lib/components/chat/ConversationMinimap.svelte`
  - A fixed right-side minimap with message markers, role colors, branch indicators, file/source/citation indicators, hover previews, and delegated message actions.
  - Uses `createMessagesList(history, history.currentId)`.
  - Calls `messagesRef.getMessageActionState()` and `messagesRef.runMessageAction()` instead of duplicating message behavior.
  - Visibility is controlled by `$settings.showConversationMinimap`, desktop breakpoint, and branch message count.

- `src/lib/components/chat/Messages.svelte`
  - Exports stable methods that the minimap depends on:
    - `ensureMessageRendered`
    - `scrollToMessage`
    - `getMessageActionState`
    - `runMessageAction`
  - These methods are the correct seam to preserve when moving minimap behavior into a side menu.

- `src/lib/components/chat/Messages/ResponseMessage.svelte`
- `src/lib/components/chat/Messages/UserMessage.svelte`
  - Include the `message-{id}` anchors and scroll positioning needed by the minimap.
  - Avoid further changes here unless needed; these files are high-churn upstream Open WebUI components.

- `src/lib/components/chat/Settings/Interface.svelte`
  - Adds the "Conversation Quick Browse" setting.
  - This should evolve into a Hivemind side menu preference group instead of remaining a single minimap toggle.

- `src/lib/stores/index.ts`
  - Already has several side-surface stores such as `showControls`, `showOverview`, `showArtifacts`, `showFileNav`, `showFileNavPath`, `showFileNavDir`, and `selectedTerminalId`.
  - The side menu should reuse or consolidate these concepts instead of adding another unrelated overlay system.

- `backend/open_webui/utils/models.py`
  - Tags Hivemind/Helix local models with multimodal and file capabilities.
  - This is important because context features should be attached to Hivemind model identities, not generic provider key configuration.

- `backend/open_webui/utils/middleware.py`
  - Adds `add_hivemind_file_payloads`, which inlines user-attached files for Hivemind local models.
  - Existing Open WebUI RAG remains available through `chat_completion_files_handler`.

- `backend/open_webui/routers/retrieval.py`
  - Upload processing now asynchronously notifies the orchestrator at `/v1/events/ingest/file`.
  - This is good for attached chat files, but it is not a query-time corpus discovery mechanism.

### Related Hivemind Orchestrator Findings

`hivemind-orchestrator` already contains the right backend foundation for a better context system.

Important files and behavior:

- `compose/docker-compose.yml`
  - Mounts the configured transcript/corpus source into the stack:
    - host: `${TRANSCRIPT_SOURCE_PATH:-../instances/${COMPOSE_PROJECT_NAME:-hivemind-fresh}/corpus}`
    - container: `/data/corpus`
  - Runs Open WebUI with `OPENAI_API_BASE_URL=http://orchestrator:8080/v1`.
  - Uses `RAG_OPENAI_API_BASE_URL=http://orchestrator:8080/v1` and `RAG_OPENAI_API_KEY=hivemind-local`.
  - This respects the project rule: Hivemind Chat must not configure normal foundation-model API keys directly.

- `services/scheduler/app/jobs/corpus_watch.py`
  - Recursively scans `/data/corpus`.
  - Supports transcript, text, markdown, PDF, image, and audio extensions.
  - Publishes changed files to `rag.ingest`.
  - Maintains `/data/corpus/.manifest.jsonl`.
  - Skips hidden files and upload paths to avoid double ingestion.

- `services/orchestrator/app/events_router.py`
  - Exposes `/v1/events/ingest/file`.
  - Saves uploaded files into `/data/corpus/uploads`.
  - Publishes ingestion payloads to `rag.ingest`.
  - This is already used by `hivemind-chat` upload processing.

- `services/worker-rag/README.md`
  - Defines the universal ingestion worker as the data-plane path into shared memory.
  - Default tiering maps transcripts/audio to `truth` and text/PDF/image to `research`.

- `services/shared/contracts/ingestion.py`
  - Provides extractor contracts for text, transcript, PDF, image, and audio.
  - Supplies media type detection and tier defaults.

- `services/shared/contracts/memory.py`
  - Defines memory tiers:
    - `research`
    - `candidate`
    - `truth`
  - Stores vectors in Qdrant collections named by tier.
  - Mirrors audit metadata to Mongo and graph structure to Neo4j.

- `services/orchestrator/app/memory_router.py`
  - Exposes `/v1/memory/ingest`, `/v1/memory/ingest_batch`, `/v1/memory/search`, `/v1/memory/{id}`, and `/v1/memory/health`.
  - Supports metadata filtering and tier-scoped search.

- `services/worker-rag/app/handler.py`
  - Extracts, chunks, embeds, and writes memory records to Qdrant.
  - Current chunk IDs are random UUIDs. This is a reliability issue for corpus reindexing because changed files can create duplicate or stale chunks unless cleanup is handled separately.

- `scripts/corpus_publish.py`
  - Provides a host-side way to publish corpus files into the ingestion queue.

- `scripts/openwebui_knowledge_upload.py`
  - Seeds or updates an Open WebUI Knowledge collection from corpus markdown.
  - Useful as a compatibility bridge, but it should not remain the primary context path.

- `docs/memory-interface.md`
  - Documents the canonical Hivemind memory interface and is the right backend contract to build on.

### Hivemind Paperclip Finding

`hivemind-paperclip` includes a useful adjacent idea in `plugin-llm-wiki`: raw RAG often rediscovers the same source material repeatedly, while a durable generated wiki can compound understanding over time. That should be considered a later layer for ZHealth, after the source-grounded transcript retrieval path is reliable.

## Online Research Summary

The proposal aligns with current Open WebUI and retrieval ecosystem direction:

- Open WebUI's RAG documentation describes the current pattern as retrieving relevant information from documents or multimedia, then adding that retrieved text to the prompt. It also warns that small context windows can cause retrieved data to be missed or underused.  
  Source: [Open WebUI RAG](https://docs.openwebui.com/features/chat-conversations/rag/)

- Open WebUI Knowledge is designed for collections of documents that can be searched and attached to models. It supports focused retrieval, full-context mode, hybrid search, reranking, and native tool-based browsing. That makes it useful, but it is still an Open WebUI-facing abstraction rather than the canonical Hivemind corpus.  
  Source: [Open WebUI Knowledge](https://docs.openwebui.com/features/workspace/knowledge/)

- Open WebUI now supports native MCP server configuration for streamable HTTP MCP servers, and also warns that tool/plugin execution can be powerful and risky. This supports using MCP-style context access carefully, with root restrictions and admin-managed tools.  
  Sources: [Open WebUI MCP](https://docs.openwebui.com/features/extensibility/mcp/), [Open WebUI Tools](https://docs.openwebui.com/features/extensibility/plugin/tools/)

- MCP resources are specifically meant to expose contextual data such as files, database schemas, or application information. The spec explicitly supports clients auto-including resources based on heuristics or model selection.  
  Source: [MCP Resources Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)

- MCP roots define filesystem boundaries that servers should respect, while clients should validate paths, obtain user consent, and manage root accessibility. This is directly relevant to a transcript/corpus context system.  
  Source: [MCP Roots Specification](https://modelcontextprotocol.io/specification/2025-06-18/client/roots)

- MCP security guidance emphasizes authorization, consent, and confused-deputy risks. Hivemind context tools should be root-scoped, read-audited, and visible to the user.  
  Source: [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)

- Qdrant recommends reciprocal rank fusion as a safe default for hybrid retrieval when no evaluation set exists, and multi-stage retrieval where cheaper methods gather candidates before more accurate reranking.  
  Source: [Qdrant Hybrid Queries](https://qdrant.tech/documentation/search/hybrid-queries/)

- LangChain's current retrieval guidance distinguishes simple RAG from agentic RAG, where a model decides when and how to retrieve through tools. It also recommends connecting to an existing knowledge base when one already exists instead of rebuilding it.  
  Source: [LangChain Retrieval](https://docs.langchain.com/oss/python/langchain/retrieval)

- Contextual compression is a standard way to retrieve broadly first, then shrink results to the specific information relevant to the query. That is important for transcript-heavy newsletter and marketing workflows.  
  Source: [LangChain Contextual Compression](https://www.langchain.com/blog/improving-document-retrieval-with-contextual-compression)

## Problems To Solve

### Conversation UI Problems

1. Hivemind conversation features are visible as individual modifications rather than a coherent UI system.
2. The minimap is useful, but it floats outside a broader navigation/context model.
3. Future context, corpus, source, and tool controls need a stable home that does not clutter the chat stream.
4. Chat navigation, sources, file context, artifacts, overview, and terminal/tool state currently risk becoming separate overlays.
5. Upstream Open WebUI changes will be easier to merge if Hivemind custom UI is isolated in a small set of components.

### Context Problems

1. The monolithic "ZHealth Corpus" Knowledge object is too opaque and unreliable for precise writing work.
2. The user needs to target specific source material on the filesystem, especially video transcripts and related text artifacts.
3. Context should be automatically discovered when appropriate, but it must also be inspectable and steerable.
4. Corpus indexing needs deterministic source identity, reindex cleanup, and provenance.
5. The model should see relevant excerpts, not an unbounded blob.
6. The user should see what context was used, why it was selected, and where it came from.

## Proposed Architecture

### Layer 1: Hivemind Side Menu In Chat

Add a self-contained side menu to the right edge of the conversation pane.

Recommended component structure:

- `src/lib/components/chat/HivemindSideMenu.svelte`
  - Owns the side rail, slideout panel, tabs, pinned/open state, keyboard handling, and responsive behavior.

- `src/lib/components/chat/HivemindSideMenu/ConversationMap.svelte`
  - Receives the same props currently used by `ConversationMinimap`.
  - Can wrap or refactor the existing minimap logic.

- `src/lib/components/chat/HivemindSideMenu/ContextPanel.svelte`
  - Shows auto-selected context, manual source picks, search queries, candidate snippets, provenance, and token budget.

- `src/lib/components/chat/HivemindSideMenu/CorpusPanel.svelte`
  - Browses indexed source files and transcript metadata.
  - Lets the user pin a source, directory, topic, speaker, course, date range, or collection for the current conversation.

- `src/lib/components/chat/HivemindSideMenu/ToolsPanel.svelte`
  - Later home for Hivemind tools, terminal state, MCP resources, and related actions.

- `src/lib/components/chat/HivemindSideMenu/types.ts`
  - Shared tab IDs, context item types, source metadata types, and UI state types.

Initial tabs:

- Map
  - Conversation minimap.
  - Message preview.
  - Branch/source/file indicators.
  - Message actions delegated to `Messages.svelte`.

- Context
  - Current context packet.
  - Auto/manual mode.
  - "Used in last request" provenance.
  - Candidate context before sending.
  - Remove/pin/source actions.

- Corpus
  - Search and browse transcript/source inventory.
  - Filters by corpus profile, media type, topic, speaker, date, course/product, and tier.

Future tabs:

- Notes
- Artifacts
- Tools
- Review

The side menu should have three display modes:

- Collapsed rail
  - Always visible on desktop if enabled.
  - Shows minimap markers and tab icons.

- Hover/open slideout
  - Opens when the user hovers, focuses, or clicks the rail.
  - Should not cover the message input in an incoherent way.

- Pinned panel
  - User can keep it open.
  - Width should be stable and persisted.

Mobile behavior:

- Hide the minimap rail by default.
- Use a bottom sheet or full-screen drawer for the side menu.
- Preserve source/context inspection but avoid a dense desktop minimap on mobile.

Settings:

- Keep existing `showConversationMinimap` for backward compatibility.
- Add or migrate toward:
  - `showHivemindSideMenu`
  - `hivemindSideMenuPinned`
  - `hivemindSideMenuWidth`
  - `hivemindSideMenuActiveTab`
  - `hivemindContextMode`: `off | suggest | auto`

### Layer 2: Context Packet Model

The chat UI should send or request structured context packets instead of attaching a giant Knowledge collection.

Proposed context packet shape:

```ts
type HivemindContextPacket = {
	id: string;
	conversationId: string;
	messageId?: string;
	mode: 'manual' | 'suggested' | 'automatic';
	taskType?: 'newsletter' | 'email_sequence' | 'marketing' | 'research' | 'general';
	query: string;
	generatedQueries: string[];
	filters: HivemindContextFilters;
	items: HivemindContextItem[];
	tokenBudget: {
		requested: number;
		estimated: number;
	};
	createdAt: string;
};

type HivemindContextItem = {
	id: string;
	sourceId: string;
	sourcePath?: string;
	sourceTitle?: string;
	sourceKind: 'transcript' | 'markdown' | 'pdf' | 'audio' | 'image' | 'chat_upload' | 'other';
	tier: 'truth' | 'research' | 'candidate';
	text: string;
	reason: string;
	score?: number;
	rerankScore?: number;
	startTimeSeconds?: number;
	endTimeSeconds?: number;
	speaker?: string;
	date?: string;
	topicTags?: string[];
	checksum?: string;
	metadata: Record<string, unknown>;
};
```

This packet should be visible in the side menu before or after the request depending on mode.

Modes:

- Off
  - No automatic context.

- Suggest
  - The system finds candidates and shows them in the side menu.
  - User chooses which to include.
  - Best default while trust is being built.

- Auto
  - The system includes high-confidence context automatically.
  - The side menu still shows exactly what was included and why.

### Layer 3: Orchestrator Context API

Add a context planning layer to `hivemind-orchestrator` rather than stuffing this logic into Open WebUI.

Proposed endpoints:

```http
POST /v1/context/plan
```

Purpose:

- Given the current chat request, classify the task, generate retrieval queries, choose filters, and return candidate context.

Input:

```json
{
	"conversation_id": "...",
	"messages": [],
	"model": "helix-...",
	"task_hint": "newsletter",
	"mode": "suggest",
	"profile": "zhealth",
	"manual_sources": [],
	"token_budget": 6000
}
```

Output:

```json
{
	"packet": {
		"id": "...",
		"mode": "suggested",
		"taskType": "newsletter",
		"generatedQueries": [],
		"filters": {},
		"items": [],
		"tokenBudget": {
			"requested": 6000,
			"estimated": 4200
		}
	}
}
```

```http
POST /v1/context/search
```

Purpose:

- Direct source search for the side menu and manual workflows.

Supports:

- Query text.
- Tier.
- Source profile.
- Metadata filters.
- Time/date filters.
- Media type.
- Top K.
- Diversification rules.

```http
GET /v1/context/sources
```

Purpose:

- List known indexed corpus sources for browsing.

Supports:

- Profile.
- Directory prefix.
- File type.
- Ingestion status.
- Last indexed time.
- Checksum.
- Topic/speaker/course tags.

```http
POST /v1/context/reindex
```

Purpose:

- Reindex one source, one directory, or one profile.

```http
DELETE /v1/context/sources/{source_id}
```

Purpose:

- Remove a source from active context search, including old chunks.

The existing `/v1/memory/search` can remain the low-level primitive. The new `/v1/context/*` layer should be the user/workflow-aware layer that knows about transcripts, writing tasks, source sets, and context packet assembly.

### Layer 4: Source Registry and Metadata

Create a durable source registry. It can begin as orchestrator database tables or a small service-level collection before being formalized further.

Required source fields:

- `source_id`
  - Stable ID derived from profile, root ID, and normalized relative path.

- `source_version_id`
  - Version ID derived from source ID and content checksum.

- `profile`
  - Example: `zhealth`.

- `root_id`
  - Named corpus root, not arbitrary filesystem access.

- `relative_path`
  - Path under the root.

- `display_title`
  - Clean title for UI.

- `media_type`
  - transcript, text, pdf, image, audio, video-derived transcript, etc.

- `checksum`
  - Content hash.

- `mtime`
- `size_bytes`
- `indexed_at`
- `index_status`
  - pending, indexed, failed, stale, deleted.

- `default_tier`
  - truth, research, candidate.

- `metadata`
  - Flexible JSON for:
    - speaker
    - course
    - module
    - product
    - date
    - tags
    - audience
    - offer
    - transcript timecodes
    - source URL
    - original filename

Recommended chunk metadata:

- `source_id`
- `source_version_id`
- `source_profile`
- `root_id`
- `relative_path`
- `checksum`
- `chunk_id`
- `chunk_index`
- `chunk_total`
- `text_hash`
- `start_time_seconds`
- `end_time_seconds`
- `speaker`
- `title`
- `topic_tags`
- `course`
- `module`
- `created_at`
- `indexed_at`

This metadata lets Hivemind answer questions like:

- "Use the vestibular course transcripts."
- "Find Eric's explanation of pain as an output."
- "Write this in the style of the July newsletter arc."
- "Only use transcripts from this directory."
- "Show me exactly which video this claim came from."

### Layer 5: Retrieval Pipeline

Recommended query-time flow:

1. Detect whether context is needed.
   - Use rules first:
     - Newsletter/email/marketing/ZHealth/course/transcript/source-specific language should trigger context planning.
     - Pure UI/code tasks should not pull ZHealth context.

2. Classify task type and profile.
   - Example:
     - task type: `newsletter`
     - profile: `zhealth`
     - desired source kind: `transcript`

3. Generate retrieval plan.
   - Produce multiple queries:
     - semantic version
     - keyword version
     - transcript-style phrase version
     - optional negative constraints

4. Search memory.
   - Use Qdrant vector search through existing memory APIs.
   - Add sparse/BM25 search when available.
   - Use Reciprocal Rank Fusion as the safe default for combining dense and keyword results.

5. Diversify.
   - Avoid all top chunks coming from one transcript unless the user asked for that transcript.
   - Cap per-source chunks.
   - Prefer high-confidence transcript chunks for factual ZHealth claims.

6. Rerank.
   - Use cross-encoder or model-based reranking where available.
   - Keep this inside orchestrator/provider configuration, not in chat API key configuration.

7. Compress.
   - Extract only the relevant spans from long chunks.
   - Preserve citations and timecodes.

8. Assemble packet.
   - Respect token budget.
   - Include source titles, relative paths, timecodes, and reasons.

9. Inject into chat.
   - Either as a system-context block or request metadata consumed by orchestrator persona routing.
   - The exact injection point should be controlled by orchestrator, not duplicated in Open WebUI.

10. Show provenance.

- The side menu should show what was selected before send in Suggest mode and after send in Auto mode.

### Layer 6: Prompt Integration

The model should not receive a vague "use corpus" instruction. It should receive structured context with provenance.

Example injected context:

```text
Hivemind selected source context for this request.

Use these excerpts as grounded source material. Do not invent claims beyond them.
When using a claim, preserve enough provenance for the user to inspect it later.

[1] Source: Vestibular Foundations transcript
Path: zhealth/courses/vestibular/foundations/session-03.vtt
Time: 00:14:08-00:15:21
Reason: Matches the user's request for newsletter material on balance and threat modulation.
Excerpt:
...

[2] Source: July newsletter notes
Path: zhealth/newsletters/2025-07/theme-notes.md
Reason: Matches requested campaign arc and tone.
Excerpt:
...
```

For writing tasks, the context packet should separate:

- Source facts.
- Voice/style examples.
- Offer/CTA constraints.
- Prior newsletter campaign continuity.
- Claims that need careful provenance.

## Implementation Plan

### Phase 0: Document and Align

Deliverables:

- This proposal.
- Agreement on first implementation slice.
- Confirm the live ZHealth corpus root and profile naming.

Decisions needed:

- Default context mode:
  - Recommended: `suggest`.

- First corpus profile:
  - Recommended: `zhealth`.

- Whether the side menu initially ships behind a setting:
  - Recommended: yes.

### Phase 1: Side Menu Shell and Minimap Migration

Goal:

- Move the minimap into a coherent Hivemind side menu without changing retrieval behavior yet.

Chat repo tasks:

1. Add `HivemindSideMenu.svelte`.
2. Move `ConversationMinimap` into the new shell or wrap it as the Map tab.
3. Replace the direct `ConversationMinimap` mount in `Chat.svelte` with `HivemindSideMenu`.
4. Keep the existing `messagesRef` delegation contract.
5. Add side menu stores/settings in `src/lib/stores/index.ts`.
6. Update settings UI in `Settings/Interface.svelte`.
7. Ensure the side rail does not overlap the message input, navbar, or `ChatControls`.
8. Add mobile behavior.

Acceptance criteria:

- Existing minimap behavior still works.
- Message jump still works.
- Hover/focus previews still work.
- Message actions still route through `Messages.svelte`.
- User can disable the feature.
- The side menu is keyboard reachable.
- Desktop and mobile layouts are visually verified.

### Phase 2: Context Panel UI Without Automation

Goal:

- Add the context side panel as a visible home for future context packets.

Chat repo tasks:

1. Add `ContextPanel.svelte`.
2. Add local context packet store.
3. Show empty state, manual pinned sources, and last-used context packet.
4. Add controls:
   - Off/Suggest/Auto mode.
   - Clear context.
   - Pin current uploaded file.
   - Inspect sources.
5. Show chat-upload ingestion status when the upload hook fires.

Backend dependency:

- None required beyond current upload ingestion hook.

Acceptance criteria:

- The UI makes context state visible even before auto retrieval exists.
- No prompt behavior changes yet.
- Uploaded file ingestion status can be represented in the panel when available.

### Phase 3: Source Inventory API

Goal:

- Let the chat side menu browse the real corpus/index instead of Open WebUI Knowledge.

Orchestrator tasks:

1. Add source registry.
2. Add `GET /v1/context/sources`.
3. Add source status:
   - pending
   - indexed
   - failed
   - stale
   - deleted
4. Add source metadata extraction from paths and sidecar metadata files.
5. Add path/root validation.

Chat repo tasks:

1. Add API client for `/v1/context/sources`.
2. Add `CorpusPanel.svelte`.
3. Support browse, search, filter, and manual pin.

Acceptance criteria:

- The user can see which transcript files Hivemind knows about.
- The user can filter by profile and directory.
- The user can pin a specific source to the current conversation.
- Paths are relative/display-safe by default.

### Phase 4: Deterministic Ingestion and Reindex Cleanup

Goal:

- Make source updates reliable and auditable.

Orchestrator tasks:

1. Change worker-rag chunk IDs from random UUIDs to deterministic IDs.
   - Recommended basis:
     - path-stable `source_id`
     - checksum-based `source_version_id`
     - `chunker_version`
     - `chunk_index`
     - optional `text_hash`

2. On changed source:
   - Mark old chunks stale or delete all chunks with prior `source_id`.
   - Insert replacement chunks.

3. Extend corpus watch manifest:
   - Store checksum in addition to mtime and size.
   - Detect deleted files.
   - Emit cleanup events for removed sources.

4. Add a reindex endpoint:
   - source
   - directory
   - profile

Acceptance criteria:

- Reindexing the same source does not create duplicate active chunks.
- Updating a transcript replaces old chunks.
- Deleted files stop appearing in search.
- Side menu source status accurately reflects index state.

### Phase 5: Manual Context Search

Goal:

- Let users manually find and add transcript/source context from the side menu.

Orchestrator tasks:

1. Add `POST /v1/context/search`.
2. Use existing `/v1/memory/search` internally.
3. Support filters:
   - profile
   - tier
   - source kind
   - source ID
   - directory prefix
   - speaker
   - topic
   - course/module
   - date range
4. Return snippets with provenance.

Chat repo tasks:

1. Corpus search UI.
2. Add-to-context action.
3. Remove-from-context action.
4. Context preview before send.

Acceptance criteria:

- User can search transcripts by natural language.
- User can manually add precise snippets to the next request.
- The model receives only selected context.
- The side menu records what was used.

### Phase 6: Suggested Automatic Context

Goal:

- Add context suggestions that are visible before they affect the prompt.

Orchestrator tasks:

1. Add `POST /v1/context/plan`.
2. Detect task type and profile.
3. Generate multi-query search plan.
4. Retrieve, diversify, rerank, and compress results.
5. Return a context packet with reasons and token estimates.

Chat repo tasks:

1. When context mode is `suggest`, call `/v1/context/plan` before send.
2. Show candidate packet in the side menu.
3. Let user approve, edit, or send without context.

Acceptance criteria:

- For a ZHealth newsletter prompt, the side menu suggests relevant transcript snippets.
- The user can see why each snippet was chosen.
- Nothing is silently added in Suggest mode.
- The final prompt includes approved context only.

### Phase 7: Automatic Context

Goal:

- Allow high-confidence context to be included automatically with full provenance.

Orchestrator tasks:

1. Define confidence thresholds.
2. Add source diversity and duplication checks.
3. Add context packet logging.
4. Add fail-closed behavior when search is unavailable.

Chat repo tasks:

1. Enable Auto mode.
2. Show "used in last request" context.
3. Add quick remove/disable actions.

Acceptance criteria:

- Auto mode includes context only when confidence is high.
- Every included item is visible to the user.
- The user can disable Auto mode globally or per conversation.
- Retrieval failure does not block ordinary chat.

### Phase 8: Migration From Open WebUI Knowledge

Goal:

- Move the ZHealth workflow away from the monolithic Knowledge object without losing continuity.

Tasks:

1. Inventory the current "ZHealth Corpus" Knowledge collection.
2. Export or map each Knowledge file to a corpus source path.
3. Ingest canonical files through orchestrator.
4. Compare search results:
   - Open WebUI Knowledge retrieval
   - Hivemind context search
5. Keep Open WebUI Knowledge available as a fallback until the new path passes evaluation.
6. Remove auto-dependency on the Knowledge object from ZHealth writing workflows.

Acceptance criteria:

- New ZHealth requests can retrieve from orchestrator memory without attaching the Knowledge object.
- The user can target specific transcript directories and files.
- The side menu shows source provenance better than the Knowledge object did.

### Phase 9: Evaluation and Quality Harness

Goal:

- Make retrieval quality measurable.

Create an evaluation set for ZHealth writing workflows:

- Newsletter prompt examples.
- Email sequence prompt examples.
- Specific transcript lookup examples.
- "Do not retrieve" prompts.
- Known correct source snippets.

Metrics:

- Recall of expected source.
- Precision of top context packet.
- Source diversity.
- Citation/provenance completeness.
- Token budget adherence.
- User approval/rejection rate in Suggest mode.

Recommended initial tests:

1. "Write a newsletter about pain as an output using Eric's transcript language."
2. "Find the transcript where he explains visual threat and peripheral vision."
3. "Draft a three-email sequence for an upcoming course using only vestibular source material."
4. "Summarize this chat message without adding corpus context."
5. "Use the July newsletter arc and pull two supporting transcript moments."

## Files To Change First

In `hivemind-chat`:

- `src/lib/components/chat/Chat.svelte`
- `src/lib/components/chat/ConversationMinimap.svelte`
- `src/lib/components/chat/HivemindSideMenu.svelte`
- `src/lib/components/chat/HivemindSideMenu/ConversationMap.svelte`
- `src/lib/components/chat/HivemindSideMenu/ContextPanel.svelte`
- `src/lib/components/chat/HivemindSideMenu/CorpusPanel.svelte`
- `src/lib/components/chat/HivemindSideMenu/types.ts`
- `src/lib/stores/index.ts`
- `src/lib/components/chat/Settings/Interface.svelte`
- `src/lib/apis/hivemind/context.ts`

In `hivemind-orchestrator`:

- `services/orchestrator/app/context_router.py`
- `services/orchestrator/app/memory_router.py`
- `services/orchestrator/app/personas/api.py`
- `services/orchestrator/app/personas/routing.py`
- `services/worker-rag/app/handler.py`
- `services/scheduler/app/jobs/corpus_watch.py`
- `services/shared/contracts/ingestion.py`
- `services/shared/contracts/memory.py`
- `compose/docker-compose.yml`
- `docs/memory-interface.md`

## Security and Permissions

Hard requirements:

1. Do not configure normal OpenAI, Anthropic, or other foundation-model API keys in `hivemind-chat`.
2. Keep provider auth inside host CLI credentials, orchestrator adapters, or generated instance config.
3. Treat filesystem context as root-scoped.
4. Never allow arbitrary path traversal from chat UI to host filesystem.
5. Show users which roots/profiles are available.
6. Make selected context visible before or after use depending on mode.
7. Log source IDs and checksums used in a request.
8. Keep worker corpus mounts read-only where possible.
9. Gate reindex/delete operations behind admin privileges.

Suggested root model:

```json
{
	"root_id": "zhealth-corpus",
	"profile": "zhealth",
	"display_name": "ZHealth Corpus",
	"container_path": "/data/corpus",
	"allow_read": true,
	"allow_write": false,
	"allowed_extensions": [".txt", ".md", ".vtt", ".srt", ".pdf", ".mp3", ".m4a", ".wav"]
}
```

## UX Details

### Side Rail

The rail should be compact and stable:

- Map markers remain visible.
- Icons indicate Map, Context, Corpus, and Tools.
- Active tab is highlighted.
- Badges show:
  - context candidates available
  - context used in last request
  - source indexing failures
  - upload ingestion pending

### Context Panel

The panel should answer four questions at a glance:

1. Is context mode off, suggest, or auto?
2. What context is selected for the next request?
3. What was used in the last request?
4. Where did each item come from?

Each context item should show:

- Source title.
- Relative path.
- Snippet.
- Reason selected.
- Tier.
- Timecode when available.
- Remove/pin action.

### Corpus Panel

The corpus browser should support:

- Search.
- Directory tree.
- Filters.
- Ingestion status.
- Source details.
- Add source to context.
- Reindex source for admins.

### Prompt-Time Flow

Recommended default:

1. User types a ZHealth writing request.
2. Context mode is `suggest`.
3. Before send, Hivemind creates a candidate packet.
4. Side menu opens to Context if there are candidates.
5. User can approve, edit, or send without context.
6. The approved packet is attached to the request.
7. After response, the side menu shows "used in last request."

This is slower than invisible automation, but it creates trust and helps tune retrieval quality.

## Risks

### Upstream Open WebUI Churn

Risk:

- Large changes to `Chat.svelte` and message components can make upstream merges painful.

Mitigation:

- Keep Hivemind custom UI behind `HivemindSideMenu`.
- Preserve the `Messages.svelte` delegation API.
- Avoid editing individual message components unless required.

### Stale or Duplicate Corpus Chunks

Risk:

- Random chunk UUIDs can leave stale chunks active after source changes.

Mitigation:

- Deterministic chunk IDs.
- Source-level cleanup on reindex.
- Source registry status.

### Over-Retrieval

Risk:

- The system may include too much transcript context and dilute the model's answer.

Mitigation:

- Token budgets.
- Context compression.
- Per-source caps.
- Suggest mode first.

### False Positive Context

Risk:

- The model receives ZHealth context for unrelated requests.

Mitigation:

- Rule-based task gates.
- Profile detection.
- User-visible mode.
- Fail closed when uncertain.

### Filesystem Leakage

Risk:

- Context tooling exposes unrelated host files.

Mitigation:

- Named roots only.
- Relative paths in UI.
- Path validation.
- Admin-only root management.

## Recommended First Milestone

Build the side menu shell and move the minimap first.

Why:

- It is valuable on its own.
- It creates the permanent UI home for context.
- It keeps the first implementation contained to `hivemind-chat`.
- It reduces the risk of mixing UI migration with retrieval backend changes.

Milestone 1 deliverables:

- `HivemindSideMenu` component.
- Existing minimap moved into Map tab.
- Settings migration.
- Empty Context and Corpus tabs.
- Desktop and mobile verification.

Recommended second milestone:

- Add source inventory API and Corpus panel.

Recommended third milestone:

- Add manual context search and context packets.

Recommended fourth milestone:

- Add suggested automatic context for ZHealth writing prompts.

## Open Questions

1. What is the canonical live ZHealth corpus host path for the current production/dev instance?
2. Should the first context profile be named `zhealth`, `zhealth-corpus`, or something instance-specific?
3. Are there sidecar metadata files already next to transcripts, or should Hivemind infer metadata from paths first?
4. Should newsletter/email voice examples live in the same corpus profile or a separate `zhealth-style` profile?
5. Should automatic context be allowed for all Hivemind models or only Helix/ZHealth personas?
6. Should context packets be stored in Open WebUI chat metadata, orchestrator audit storage, or both?
7. Should source registry state live in Mongo, Qdrant payload indexes, or both?

## Bottom Line

The durable fix is not to make the existing Open WebUI Knowledge object bigger or more carefully named. The durable fix is to make Hivemind's filesystem corpus a first-class, indexed, inspectable, source-grounded context system, with the chat UI exposing the plan and provenance in a dedicated right-side Hivemind side menu.

That gives the user a cleaner conversation area, a better home for the minimap, a trustworthy way to target transcripts, and a path toward automatic context that can be evaluated and debugged instead of guessed at.
