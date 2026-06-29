# ZHealth Context System Execution TODO

Date: 2026-06-29  
Status: active execution tracker  
Primary repo: `hivemind-chat`  
Related repos: `hivemind-orchestrator`, `hivemind-stt`, ZHealth corpus at `/Volumes/Public/ZHealth`  
Goal: make the ZHealth split knowledge, right-side conversation menu, and automatic context selection reliable enough for everyday newsletter, email, marketing, and source-grounded writing work.

## Guardrails

- Do not configure normal foundation-model API keys. This system must use the Hivemind local/Open WebUI/orchestrator path and host-authenticated CLI tools.
- Treat `/Volumes/Public/ZHealth` as the source corpus root and `/Volumes/Public/ZHealth/.hivemind/openwebui-corpus` as generated output.
- Keep Open WebUI Knowledge as the compatibility/manual-inspection layer; build the durable context planner around source metadata and orchestrator contracts.
- Preserve unrelated working-tree changes. Do not revert user edits.
- Every data sync or repair command needs a dry-run or backup path before mutation.

## A. Baseline And Safety

- [ ] A01. Capture current `git status --short` for `hivemind-chat`.
- [ ] A02. Capture current `git status --short` for `hivemind-orchestrator`.
- [ ] A03. Confirm the active compose project and Open WebUI port.
- [ ] A04. Confirm `hivemind-zhealth-open-webui-1` is healthy before changes.
- [ ] A05. Run `scripts/zhealth_corpus/verify_openwebui_zhealth.py --require-manifest-match --require-public-read`.
- [ ] A06. Back up the Open WebUI SQLite DB before any grant or KB mutation.
- [ ] A07. Back up `/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json`.
- [ ] A08. Export the current list of `ZHealth /` Knowledge IDs, names, file counts, and grants.
- [ ] A09. Record whether the old monolithic `ZHealth Corpus` exists and whether it is visible to normal users.
- [ ] A10. Confirm no new provider API-key environment configuration is introduced.

## B. Corpus Builder And Source Hygiene

- [ ] B01. Run a limited builder smoke test from `/Volumes/Public/ZHealth`.
- [ ] B02. Run a full builder dry run to a temporary output directory.
- [ ] B03. Compare temporary manifest counts against the canonical manifest.
- [ ] B04. Identify noisy source folders currently becoming chapters, such as `Output`, `Source`, `New folder`, `Wrong`, or `logs`.
- [ ] B05. Add or document an allowlist/denylist policy for source folders.
- [ ] B06. Ensure `.hivemind` generated output is always excluded from source discovery.
- [ ] B07. Confirm transcript source precedence is deterministic.
- [ ] B08. Confirm episode stems with punctuation and duplicate names get stable IDs.
- [ ] B09. Confirm topic markdown frontmatter includes course/chapter/episode/topic metadata.
- [ ] B10. Add `start_time_sec`, `end_time_sec`, `duration_sec`, `num_words`, and `num_segments` to generated metadata if missing.
- [ ] B11. Add `source_manifest`, `source_speakers`, and `transcript_variant` when available.
- [ ] B12. Add a manifest-level schema version.
- [ ] B13. Add a builder command that validates an existing manifest without rebuilding.
- [ ] B14. Add a report for orphaned transcripts, media without transcript, and transcript without media.
- [ ] B15. Document how `hivemind-stt` artifacts become ZHealth corpus episodes.

## C. Open WebUI Sync And Access

- [ ] C01. Run split sync in dry-run mode and store the summary.
- [ ] C02. Confirm all 101 expected split KBs exist.
- [ ] C03. Confirm all 2205 expected files are linked through `knowledge_file`.
- [ ] C04. Confirm all split KBs have `user:*:read`.
- [ ] C05. Confirm normal non-admin users can see split KBs.
- [ ] C06. Confirm the old monolith is either hidden from normal users or clearly marked as legacy.
- [ ] C07. Add a sync option to mark legacy monolith disabled/archived without deleting it.
- [ ] C08. Ensure sync is additive by default and preserves existing grants.
- [ ] C09. Ensure replace-grants mode is explicit and hard to trigger accidentally.
- [ ] C10. Add a concise sync summary with created/updated/skipped/deleted/error counts.
- [ ] C11. Add a `--fail-on-drift` option for CI/local verification.
- [ ] C12. Add a cleanup plan for removed source topics that should be unlinked or archived.
- [ ] C13. Confirm Qdrant collection naming and tenant metadata for each KB.
- [ ] C14. Add a one-collection retrieval smoke test to the sync flow.
- [ ] C15. Document the exact rollback command for DB and manifest restore.

## D. Retrieval And Context Planner

- [ ] D01. Define the context packet JSON contract used by chat.
- [ ] D02. Include selected source title, course, chapter, episode, topic, timestamp, score, and reason in every packet.
- [ ] D03. Add prompt classification for ZHealth/newsletter/email/marketing/source-grounded writing requests.
- [ ] D04. Add explicit non-trigger categories for coding, account/admin, scheduling, and unrelated general chat.
- [ ] D05. Implement metadata-filtered retrieval when the user names a course.
- [ ] D06. Implement metadata-filtered retrieval when the user names a chapter.
- [ ] D07. Implement metadata-filtered retrieval when the user names an episode.
- [ ] D08. Implement metadata-filtered retrieval when the user names a topic or phrase.
- [ ] D09. Add query expansion for Dr. Cobb/ZHealth writing tasks without changing the user’s intent.
- [ ] D10. Add diversity controls so one episode does not dominate all context.
- [ ] D11. Add token budgeting for small, medium, and large context packets.
- [ ] D12. Add confidence thresholds for `suggest` versus `auto`.
- [ ] D13. Add an explanation string for every auto-selected source.
- [ ] D14. Add a no-context result path that tells the UI why nothing was selected.
- [ ] D15. Add evaluation fixtures for newsletter, email sequence, course promo, and transcript-summary prompts.

## E. Right-Side Chat Side Menu

- [ ] E01. Keep the conversation minimap visible in rail mode when the panel is closed.
- [ ] E02. Keep Map, Context, and Corpus tabs available from the right rail.
- [ ] E03. Ensure hover over rail icons, tooltips, and panel controls does not collapse the panel.
- [ ] E04. Add keyboard focus behavior for opening and closing the side menu.
- [ ] E05. Add an explicit pin state that persists per browser.
- [ ] E06. Add a compact attached-context list to the Context tab.
- [ ] E07. Add a “selected for next send” state separate from “used in last response”.
- [ ] E08. Show source provenance for attached context without oversized cards.
- [ ] E09. Add remove/detach controls for each context source.
- [ ] E10. Add a visible mode control for `off`, `suggest`, and `auto`.
- [ ] E11. Ensure `auto` prompt searches do not overwrite the Corpus tab list.
- [ ] E12. Ensure Corpus search debounces and cancels stale requests.
- [ ] E13. Ensure Corpus search works for `Cerebrum`, course names, and episode stems.
- [ ] E14. Ensure Corpus search fetches beyond the first Open WebUI result page.
- [ ] E15. Add empty, loading, and error states for Corpus search.
- [ ] E16. Add a small “verified local corpus” indicator only if it can be backed by the verifier.
- [ ] E17. Test desktop and mobile breakpoints; hide or adapt side menu on mobile.
- [ ] E18. Add Playwright coverage for side-menu open, hover, search, attach, detach.

## F. Chat Knowledge Picker

- [ ] F01. Keep the normal Open WebUI Knowledge picker working for non-ZHealth KBs.
- [ ] F02. Show a dedicated `ZHealth Chapters` section above the generic list.
- [ ] F03. Exclude the legacy `ZHealth Corpus` from the split section.
- [ ] F04. Normalize names with decoded entities and consistent slash spacing.
- [ ] F05. Fetch all result pages for ZHealth query searches.
- [ ] F06. Preserve partial results when a later page fails.
- [ ] F07. Add a search input for course/chapter/topic in the ZHealth section.
- [ ] F08. Ensure selecting a ZHealth chapter attaches a `collection` file object.
- [ ] F09. Ensure the attached chip displays a useful short name.
- [ ] F10. Add files expansion for selected split KBs.
- [ ] F11. Confirm file search/list uses the current `knowledge_file` relationship.
- [ ] F12. Add regression coverage for `NeckBBPG - 17 - Cerebrum`.

## G. Orchestrator Integration

- [ ] G01. Locate or restore the active `hivemind-stt` checkout if needed.
- [ ] G02. Decide whether `hivemind-stt` only produces artifacts or also owns source metadata.
- [ ] G03. Add a ZHealth source registry endpoint in orchestrator if absent.
- [ ] G04. Add context search endpoint that can target ZHealth metadata filters.
- [ ] G05. Add a health endpoint for corpus manifest freshness.
- [ ] G06. Add a drift endpoint comparing source manifest, Open WebUI KBs, and Qdrant vectors.
- [ ] G07. Add orchestrator-side logging for selected context packets.
- [ ] G08. Add telemetry fields for query, selected source IDs, scores, and mode.
- [ ] G09. Add privacy guardrails for filesystem source paths in model-facing context.
- [ ] G10. Document how Open WebUI chat calls the orchestrator context endpoint.

## H. Qdrant And Retrieval Health

- [ ] H01. Confirm the Qdrant collection that stores Open WebUI knowledge points.
- [ ] H02. Confirm collection tenant IDs match Open WebUI Knowledge IDs.
- [ ] H03. Add a script to count vectors per split KB.
- [ ] H04. Add a script to find KBs with zero vectors.
- [ ] H05. Add a script to compare Open WebUI file counts against vector counts.
- [ ] H06. Add a targeted retrieval smoke test for one known KB in each major course.
- [ ] H07. Record top-k score distributions for known-good queries.
- [ ] H08. Decide whether hybrid search should be enabled for ZHealth by default.
- [ ] H09. Evaluate whether current chunk size/overlap is too large for transcript topics.
- [ ] H10. Document Qdrant repair steps for re-indexing one KB.

## I. Testing And Verification

- [ ] I01. Keep `python3 -m py_compile scripts/zhealth_corpus/*.py` clean.
- [ ] I02. Keep focused Svelte compile checks clean for changed components.
- [ ] I03. Run `npm run test:frontend` and record output.
- [ ] I04. Run `npm run check` and separate pre-existing repo-wide errors from new errors.
- [ ] I05. Add browser verification for Workspace > Knowledge.
- [ ] I06. Add browser verification for chat Attach Knowledge.
- [ ] I07. Add browser verification for side-menu Corpus search.
- [ ] I08. Add browser verification for side-menu hover stability.
- [ ] I09. Add API verification for `query=Cerebrum`.
- [ ] I10. Add API verification for retrieval query against the Cerebrum KB.
- [ ] I11. Add normal-user verification, not only admin verification.
- [ ] I12. Add a screenshot artifact path for UI verification failures.
- [ ] I13. Add a single command that prints a pass/fail release summary.

## J. Release And Operations

- [ ] J01. Rebuild the Open WebUI container from the final source state.
- [ ] J02. Confirm `hivemind-zhealth-open-webui-1` is healthy after rebuild.
- [ ] J03. Confirm the browser app loads at `http://localhost:3002`.
- [ ] J04. Confirm Workspace > Knowledge count and visible ZHealth entries.
- [ ] J05. Confirm chat picker attaches `ZHealth / Neck / NeckBBPG - 17 - Cerebrum`.
- [ ] J06. Confirm side menu Corpus search finds `Cerebrum`.
- [ ] J07. Confirm retrieval returns chunks from the selected KB.
- [ ] J08. Write a short operator runbook for rebuild, verify, rollback.
- [ ] J09. Add a changelog entry for the split knowledge and side-menu changes.
- [ ] J10. Decide whether to archive, hide, or leave the legacy `ZHealth Corpus`.
- [ ] J11. Decide whether this ships behind a settings flag by default.
- [ ] J12. Create a release checklist for local, staging, and production-like environments.
- [ ] J13. Capture final acceptance evidence in `docs/proposals`.
- [ ] J14. Commit in logical chunks once the user approves committing.
- [ ] J15. Open a draft PR once the branch is ready.

## Immediate Next Batch

1. Run the verifier and save a short summary under `.hivemind/reports/`.
2. Add normal-user verification for split KB visibility.
3. Add Qdrant vector-count diagnostics for the 101 split KBs.
4. Add focused browser regression coverage for Attach Knowledge and the side menu.
5. Decide the legacy `ZHealth Corpus` disposition and document it.
6. Wire side-menu auto-context to the orchestrator context planner contract.
7. Add context packet provenance display for used sources after a message is sent.
8. Add release/rollback notes to the operator runbook.

## Definition Of Done

- A normal user can find and attach split ZHealth KBs in Workspace, Attach Knowledge, and the side menu.
- `Cerebrum` and at least five other representative queries return the correct split KBs.
- Retrieval returns source-grounded chunks with course/chapter/episode/topic provenance.
- Automatic context selection can be turned off, suggested, or automatic.
- The UI shows what context is selected before send and what was used after response.
- Verification can be run with one documented command.
- Rollback can restore the previous DB/manifest state without deleting source data.
