<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { type Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { v4 as uuidv4 } from 'uuid';
	import { toast } from 'svelte-sonner';
	import { mobile, settings, hivemindFileNavRequest } from '$lib/stores';
	import { uploadFile } from '$lib/apis/files';
	import { getKnowledgeBases, searchKnowledgeBases } from '$lib/apis/knowledge';
	import { decodeString } from '$lib/utils';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ConversationMinimap from '$lib/components/chat/ConversationMinimap.svelte';
	import InstanceFileManager from '$lib/components/chat/InstanceFileManager.svelte';
	import Database from '$lib/components/icons/Database.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import MapIcon from '$lib/components/icons/Map.svelte';
	import Pin from '$lib/components/icons/Pin.svelte';
	import PinSlash from '$lib/components/icons/PinSlash.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let history: any = {};
	export let messagesRef: any;
	export let scrollContainerElement: HTMLDivElement | undefined;
	export let readOnly = false;
	export let files: any[] = [];
	export let prompt = '';
	export let chatId: string | null = null;
	export let conversationId: string | null = null;
	export let onInsertPath: (path: string) => void = () => {};

	type SideMenuTab = 'map' | 'context' | 'corpus' | 'files';
	type ContextMode = 'off' | 'suggest' | 'auto';

	const stateStorageKey = 'hivemind-side-menu-state';
	const tabs: { id: SideMenuTab; label: string }[] = [
		{ id: 'files', label: 'Files' },
		{ id: 'context', label: 'Context' },
		{ id: 'corpus', label: 'Corpus' },
		{ id: 'map', label: 'Map' }
	];

	let activeTab: SideMenuTab = 'files';
	let open = false;
	let pinned = false;
	let mounted = false;
	let hasMessages = false;
	let hasConversationSurface = false;
	let enabled = false;
	let contextMode: ContextMode = 'suggest';
	let corpusQuery = '';
	let corpusKnowledgeItems: any[] = [];
	let corpusLoading = false;
	let corpusError = '';
	let corpusLoadRequestId = 0;
	let corpusSearchTimer: ReturnType<typeof setTimeout> | null = null;
	let lastCorpusQuery = corpusQuery;
	let autoAttachedForPrompt = '';
	let resolvedConversationId = '';
	let suppressNextAutoAttach = false;
	let pendingFileNavPath: string | null = null;

	type KnowledgeSearchItem = {
		id?: string;
		name?: string;
		description?: string;
		[key: string]: unknown;
	};

	const maxKnowledgeSearchPages = 500;

	const persistState = () => {
		if (!mounted) {
			return;
		}

		try {
			localStorage.setItem(stateStorageKey, JSON.stringify({ activeTab, pinned, contextMode }));
		} catch {
			// Ignore unavailable or blocked localStorage.
		}
	};

	const selectTab = (tab: SideMenuTab) => {
		activeTab = tab;
		open = true;
		persistState();
	};

	const setPinned = (value: boolean) => {
		pinned = value;
		open = value || open;
		persistState();
	};

	const closePanel = () => {
		open = false;
		pinned = false;
		persistState();
	};

	const sideMenuTooltipOptions = {
		delay: [120, 150],
		appendTo: () => document.body
	};

	const getTabLabel = (tab: SideMenuTab) => {
		return tabs.find((item) => item.id === tab)?.label ?? 'Hivemind';
	};

	const normalizeKnowledgeItem = (item: any) => ({
		type: 'collection',
		status: 'processed',
		...item
	});

	const normalizeKnowledgeName = (name: unknown) =>
		decodeString(`${name ?? ''}`)
			.trim()
			.replace(/\s*\/\s*/g, ' / ');

	const isCorpusKnowledge = (item: any) => Boolean(item?.id);

	const isAttached = (item: any) =>
		files.some((file) => file?.type === 'collection' && file?.id === item?.id);

	const attachKnowledge = (item: any) => {
		if (!item?.id || isAttached(item)) {
			return;
		}

		files = [...files, normalizeKnowledgeItem(item)];
	};

	const detachKnowledge = (item: any) => {
		files = files.filter((file) => !(file?.type === 'collection' && file?.id === item?.id));
	};

	const toggleKnowledge = (item: any) => {
		if (isAttached(item)) {
			detachKnowledge(item);
		} else {
			attachKnowledge(item);
		}
	};

	const attachedCorpusItems = () =>
		files.filter((file) => file?.type === 'collection' && isCorpusKnowledge(file));

	const attachDownloadedFile = async (blob: Blob, name: string, contentType: string) => {
		if (!blob || !name) {
			return;
		}

		const tempItemId = uuidv4();
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: '',
			name,
			collection_name: '',
			status: 'uploading',
			error: '',
			itemId: tempItemId,
			size: blob.size,
			content_type: contentType || blob.type || 'application/octet-stream'
		};

		files = [...files, fileItem];

		try {
			const file = new File([blob], name, {
				type: contentType || blob.type || 'application/octet-stream'
			});
			const uploadedFile = await uploadFile(localStorage.token, file);

			if (uploadedFile?.error) {
				toast.warning(uploadedFile.error);
			}

			const idx = files.findIndex((item) => item.itemId === tempItemId);
			if (idx !== -1) {
				files[idx] = {
					...fileItem,
					status: 'uploaded',
					file: uploadedFile,
					id: uploadedFile.id,
					url: `${uploadedFile.id}`,
					collection_name: uploadedFile?.meta?.collection_name || uploadedFile?.collection_name,
					content_type: uploadedFile?.meta?.content_type || uploadedFile?.content_type
				};
				files = files;
			}
		} catch (error) {
			files = files.filter((item) => item.itemId !== tempItemId);
			toast.error($i18n.t('Failed to attach file'));
			console.error(error);
		}
	};

	const searchAllKnowledgeBasePages = async (query: string) => {
		const allItems: KnowledgeSearchItem[] = [];
		const seenIds = new Set<string>();
		let fetchedItemCount = 0;
		let page = 1;
		let total: number | null = null;
		let hasMorePages = true;
		const normalizedQuery = query.trim();

		while (hasMorePages && page <= maxKnowledgeSearchPages) {
			let res;
			try {
				res = normalizedQuery
					? await searchKnowledgeBases(localStorage.token, normalizedQuery, null, page)
					: await getKnowledgeBases(localStorage.token, page);
			} catch (error) {
				if (allItems.length > 0) {
					break;
				}
				throw error;
			}

			const pageItems: KnowledgeSearchItem[] = Array.isArray(res?.items) ? res.items : [];

			if (typeof res?.total === 'number') {
				total = res.total;
			}

			fetchedItemCount += pageItems.length;

			for (const item of pageItems) {
				const itemId = item?.id;
				if (!itemId || !seenIds.has(itemId)) {
					if (itemId) {
						seenIds.add(itemId);
					}
					allItems.push(item);
				}
			}

			if (pageItems.length === 0 || (total !== null && fetchedItemCount >= total)) {
				hasMorePages = false;
			} else {
				page += 1;
			}
		}

		return allItems;
	};

	const loadCorpusKnowledge = async (
		query = corpusQuery,
		options: { updateList?: boolean } = {}
	) => {
		const updateList = options.updateList ?? query === corpusQuery;
		const requestId = updateList ? ++corpusLoadRequestId : corpusLoadRequestId;

		if (updateList) {
			corpusLoading = true;
			corpusError = '';
		}

		try {
			const allItems = await searchAllKnowledgeBasePages(query);
			if (updateList && requestId !== corpusLoadRequestId) {
				return [];
			}

			const nextItems = allItems
				.filter(isCorpusKnowledge)
				.map(normalizeKnowledgeItem)
				.sort((a, b) => normalizeKnowledgeName(a.name).localeCompare(normalizeKnowledgeName(b.name)));

			if (updateList) {
				corpusKnowledgeItems = nextItems;
			}
			return nextItems;
		} catch (err) {
			if (updateList && requestId === corpusLoadRequestId) {
				console.error(err);
				corpusError = 'Unable to load knowledge sources';
				corpusKnowledgeItems = [];
			}
			return [];
		} finally {
			if (updateList && requestId === corpusLoadRequestId) {
				corpusLoading = false;
			}
		}
	};

	const setContextMode = (mode: ContextMode) => {
		contextMode = mode;
		persistState();
	};

	const autoAttachFromPrompt = async () => {
		const query = prompt.trim();
		if (contextMode !== 'auto' || query.length < 4 || query === autoAttachedForPrompt) {
			return;
		}

		autoAttachedForPrompt = query;
		const items = await loadCorpusKnowledge(query, { updateList: false });
		const match = items.find((item) => !isAttached(item));
		if (match) {
			attachKnowledge(match);
		}
	};

	const handleInsertPath = (path: string) => {
		const normalized = `${path ?? ''}`.trim();
		if (!normalized) {
			return;
		}

		suppressNextAutoAttach = true;
		onInsertPath(normalized);
	};

	onMount(() => {
		try {
			const savedState = JSON.parse(localStorage.getItem(stateStorageKey) ?? '{}');
			if (['map', 'context', 'corpus', 'files'].includes(savedState?.activeTab)) {
				activeTab = savedState.activeTab;
			}
			if (['off', 'suggest', 'auto'].includes(savedState?.contextMode)) {
				contextMode = savedState.contextMode;
			}
			pinned = savedState?.pinned === true;
			open = pinned;
		} catch {
			// Ignore malformed or unavailable persisted menu state.
		}

		mounted = true;
		if (enabled) {
			void loadCorpusKnowledge();
		}
	});

	onDestroy(() => {
		if (corpusSearchTimer) {
			clearTimeout(corpusSearchTimer);
		}
	});

	$: hasMessages = Object.keys(history?.messages ?? {}).length > 0;
	$: resolvedConversationId = `${conversationId ?? chatId ?? ''}`.trim();
	$: hasConversationSurface = Boolean(resolvedConversationId);
	$: enabled = ($settings?.showHivemindSideMenu ?? true) && !$mobile && hasConversationSurface;
	$: if (mounted && enabled && contextMode === 'auto' && prompt.trim().length >= 4) {
		if (suppressNextAutoAttach) {
			suppressNextAutoAttach = false;
		} else {
			void autoAttachFromPrompt();
		}
	}
	$: if (mounted && corpusQuery !== lastCorpusQuery) {
		lastCorpusQuery = corpusQuery;
		if (corpusSearchTimer) {
			clearTimeout(corpusSearchTimer);
		}
		corpusSearchTimer = setTimeout(() => {
			void loadCorpusKnowledge();
		}, 250);
	}

	$: if ($hivemindFileNavRequest && enabled) {
		pendingFileNavPath = $hivemindFileNavRequest;
		hivemindFileNavRequest.set(null);
		activeTab = 'files';
		open = true;
		setTimeout(() => { pendingFileNavPath = null; }, 0);
	}
</script>

{#if enabled}
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<aside
		data-testid="hivemind-side-menu"
		class="pointer-events-none absolute bottom-3 right-3 top-16 z-40 hidden max-w-[calc(100%-1.5rem)] items-stretch md:flex"
		aria-label={$i18n.t('Hivemind side menu')}
		data-active-tab={activeTab}
		data-open={open || pinned}
		data-has-messages={hasMessages}
		data-has-conversation-surface={hasConversationSurface}
	>
		<div class="pointer-events-auto flex h-full min-h-0 items-stretch">
			<div
				data-testid="hivemind-side-menu-rail"
				class="flex h-full w-14 shrink-0 flex-col overflow-hidden rounded-xl border border-gray-200 bg-white/90 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-950/90"
			>
				<div
					class="flex shrink-0 flex-col gap-1 border-b border-gray-100 p-1.5 dark:border-gray-900"
					data-testid="hivemind-side-menu-tabs"
				>
					{#each tabs as tab (tab.id)}
						<Tooltip
							content={$i18n.t(tab.label)}
							placement="left"
							interactive={true}
							tippyOptions={sideMenuTooltipOptions}
						>
							<button
								type="button"
								class="flex h-9 w-full items-center justify-center rounded-lg transition focus:outline-hidden focus:ring-2 focus:ring-gray-500/60 {activeTab ===
								tab.id
									? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-950'
									: 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100'}"
								aria-label={$i18n.t(tab.label)}
								aria-pressed={activeTab === tab.id}
								data-testid={`hivemind-side-menu-tab-${tab.id}`}
								on:click={() => selectTab(tab.id)}
							>
								{#if tab.id === 'map'}
									<MapIcon className="size-4" />
								{:else if tab.id === 'context'}
									<Database className="size-4" />
								{:else if tab.id === 'corpus'}
									<Folder className="size-4" />
								{:else}
									<Document className="size-4" />
								{/if}
							</button>
						</Tooltip>
					{/each}
				</div>

				<div class="min-h-0 flex-1 px-1.5 py-2" data-testid="hivemind-side-menu-rail-content">
					{#if !(open || pinned) || activeTab !== 'map'}
						<ConversationMinimap
							{history}
							{messagesRef}
							{scrollContainerElement}
							{readOnly}
							layout="rail"
						/>
					{/if}
				</div>
			</div>

			{#if open || pinned}
				<section
					data-testid="hivemind-side-menu-panel"
					class="ml-2 flex h-full {activeTab === 'files'
						? 'w-[min(86vw,42rem)]'
						: 'w-80'} max-w-[calc(100vw-7rem)] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white/95 shadow-xl backdrop-blur dark:border-gray-800 dark:bg-gray-950/95"
					aria-label={$i18n.t(getTabLabel(activeTab))}
					data-active-tab={activeTab}
				>
					<header
						class="flex shrink-0 items-center justify-between gap-2 border-b border-gray-100 px-3 py-2 dark:border-gray-900"
						data-testid="hivemind-side-menu-panel-header"
					>
						<div class="min-w-0 text-sm font-medium text-gray-900 dark:text-gray-100">
							{$i18n.t(getTabLabel(activeTab))}
						</div>

						<div class="flex items-center gap-1">
							<Tooltip
								content={pinned ? $i18n.t('Unpin') : $i18n.t('Pin')}
								placement="bottom"
								interactive={true}
								tippyOptions={sideMenuTooltipOptions}
							>
								<button
									type="button"
									class="rounded-lg p-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 focus:outline-hidden focus:ring-2 focus:ring-gray-500/60 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
									aria-label={pinned ? $i18n.t('Unpin') : $i18n.t('Pin')}
									aria-pressed={pinned}
									data-testid="hivemind-side-menu-pin"
									on:click={() => setPinned(!pinned)}
								>
									{#if pinned}
										<PinSlash className="size-4" />
									{:else}
										<Pin className="size-4" />
									{/if}
								</button>
							</Tooltip>

							<Tooltip
								content={$i18n.t('Close')}
								placement="bottom"
								interactive={true}
								tippyOptions={sideMenuTooltipOptions}
							>
								<button
									type="button"
									class="rounded-lg p-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 focus:outline-hidden focus:ring-2 focus:ring-gray-500/60 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
									aria-label={$i18n.t('Close')}
									data-testid="hivemind-side-menu-close"
									on:click={closePanel}
								>
									<XMark className="size-4" />
								</button>
							</Tooltip>
						</div>
					</header>

					<div
						class="min-h-0 flex-1 overflow-hidden {activeTab === 'files' ? 'p-2' : 'p-3'}"
						data-testid="hivemind-side-menu-panel-content"
					>
						{#if activeTab === 'map'}
							<ConversationMinimap
								{history}
								{messagesRef}
								{scrollContainerElement}
								{readOnly}
								layout="panel"
							/>
						{:else if activeTab === 'files'}
							<div class="flex h-full min-h-0 flex-col gap-2">
								<InstanceFileManager
									chatId={resolvedConversationId}
									onInsertPath={handleInsertPath}
									onAttachFile={attachDownloadedFile}
									navToPath={pendingFileNavPath}
								/>
							</div>
						{:else if activeTab === 'context'}
							<div class="flex h-full min-h-0 flex-col gap-3 text-xs">
								<div
									class="rounded-lg border border-gray-200 bg-white/70 p-3 dark:border-gray-800 dark:bg-gray-900/40"
								>
									<div class="font-medium text-gray-900 dark:text-gray-100">
										{$i18n.t('Context Mode')}
									</div>
									<div
										class="mt-2 grid grid-cols-3 gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-900"
									>
										{#each ['off', 'suggest', 'auto'] as mode}
											<button
												type="button"
												class="rounded-md px-2 py-1 text-[11px] transition {contextMode === mode
													? 'bg-white text-gray-900 shadow-xs dark:bg-gray-800 dark:text-gray-100'
													: 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'}"
												aria-pressed={contextMode === mode}
												on:click={() => setContextMode(mode as ContextMode)}
											>
												{$i18n.t(mode === 'off' ? 'Off' : mode === 'suggest' ? 'Suggest' : 'Auto')}
											</button>
										{/each}
									</div>
								</div>

								<div
									class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-800"
								>
									{#if attachedCorpusItems().length === 0}
										<div class="p-4 text-center text-gray-500 dark:text-gray-400">
											{$i18n.t('No corpus context selected')}
										</div>
									{:else}
										<div class="divide-y divide-gray-100 dark:divide-gray-900">
											{#each attachedCorpusItems() as item (item.id)}
												<div class="flex items-center gap-2 px-3 py-2">
													<Database className="size-4 shrink-0 text-gray-500 dark:text-gray-400" />
													<div class="min-w-0 flex-1">
														<div class="truncate font-medium text-gray-900 dark:text-gray-100">
															{item.name}
														</div>
														<div class="truncate text-[11px] text-gray-500 dark:text-gray-400">
															{item.description ?? item.id}
														</div>
													</div>
													<button
														type="button"
														class="rounded-md px-2 py-1 text-[11px] text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
														on:click={() => detachKnowledge(item)}
													>
														{$i18n.t('Remove')}
													</button>
												</div>
											{/each}
										</div>
									{/if}
								</div>
							</div>
						{:else}
							<div class="flex h-full min-h-0 flex-col gap-3 text-xs">
								<input
									type="search"
									bind:value={corpusQuery}
									placeholder={$i18n.t('Search sources')}
									class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700 outline-hidden focus:ring-2 focus:ring-gray-500/30 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200"
									on:keydown={(event) => {
										if (event.key === 'Enter') {
											void loadCorpusKnowledge();
										}
									}}
								/>

								<div
									class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-800"
								>
									{#if corpusLoading}
										<div class="p-4 text-center text-gray-500 dark:text-gray-400">
											{$i18n.t('Loading sources')}
										</div>
									{:else if corpusError}
										<div class="p-4 text-center text-red-500">
											{$i18n.t(corpusError)}
										</div>
									{:else if corpusKnowledgeItems.length === 0}
										<div class="p-4 text-center text-gray-500 dark:text-gray-400">
											{$i18n.t('No sources found')}
										</div>
									{:else}
										<div class="divide-y divide-gray-100 dark:divide-gray-900">
											{#each corpusKnowledgeItems as item (item.id)}
												<button
													type="button"
													class="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-gray-50 dark:hover:bg-gray-900/70"
													aria-pressed={isAttached(item)}
													on:click={() => toggleKnowledge(item)}
												>
													<Database className="size-4 shrink-0 text-gray-500 dark:text-gray-400" />
													<div class="min-w-0 flex-1">
														<div class="truncate font-medium text-gray-900 dark:text-gray-100">
															{item.name}
														</div>
														<div class="truncate text-[11px] text-gray-500 dark:text-gray-400">
															{item.description ?? item.id}
														</div>
													</div>
													<div
														class="shrink-0 rounded-md px-2 py-1 text-[11px] {isAttached(item)
															? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-950'
															: 'bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300'}"
													>
														{$i18n.t(isAttached(item) ? 'Added' : 'Add')}
													</div>
												</button>
											{/each}
										</div>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				</section>
			{/if}
		</div>
	</aside>
{/if}
