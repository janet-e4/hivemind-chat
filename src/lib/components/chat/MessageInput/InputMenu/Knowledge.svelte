<script lang="ts">
	import { onDestroy, onMount, tick, getContext } from 'svelte';

	import { decodeString } from '$lib/utils';
	import { knowledge } from '$lib/stores';

	import {
		getKnowledgeBases,
		searchKnowledgeBases,
		searchKnowledgeFilesById
	} from '$lib/apis/knowledge';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Database from '$lib/components/icons/Database.svelte';
	import DocumentPage from '$lib/components/icons/DocumentPage.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Loader from '$lib/components/common/Loader.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';

	const i18n = getContext('i18n');

	export let onSelect = (e) => {};

	let loaded = false;
	let selectedIdx = 0;

	let selectedItem = null;

	let selectedFileItemsPage = 1;

	let selectedFileItems = null;
	let selectedFileItemsTotal = null;

	let selectedFileItemsLoading = false;
	let selectedFileAllItemsLoaded = false;

	$: if (selectedItem) {
		initSelectedFileItems();
	}

	const initSelectedFileItems = async () => {
		selectedFileItemsPage = 1;
		selectedFileItems = null;
		selectedFileItemsTotal = null;
		selectedFileAllItemsLoaded = false;
		selectedFileItemsLoading = false;
		await tick();
		await getSelectedFileItemsPage();
	};

	const loadMoreSelectedFileItems = async () => {
		if (selectedFileAllItemsLoaded) return;
		selectedFileItemsPage += 1;
		await getSelectedFileItemsPage();
	};

	const getSelectedFileItemsPage = async () => {
		if (!selectedItem) return;
		selectedFileItemsLoading = true;

		const res = await searchKnowledgeFilesById(
			localStorage.token,
			selectedItem.id,
			null,
			null,
			null,
			null,
			selectedFileItemsPage
		).catch(() => {
			return null;
		});

		if (res) {
			selectedFileItemsTotal = res.total;
			const pageItems = res.items;

			if ((pageItems ?? []).length === 0) {
				selectedFileAllItemsLoaded = true;
			} else {
				selectedFileAllItemsLoaded = false;
			}

			if (selectedFileItems) {
				const existingIds = new Set(selectedFileItems.map((item) => item.id));
				const newItems = pageItems.filter((item) => !existingIds.has(item.id));
				selectedFileItems = [...selectedFileItems, ...newItems];
			} else {
				selectedFileItems = pageItems;
			}
		}

		selectedFileItemsLoading = false;
		return res;
	};

	let page = 1;
	let items = null;
	let total = null;

	let itemsLoading = false;
	let allItemsLoaded = false;
	let featuredQuery = '';
	let featuredItems: any[] = [];
	let featuredItemsLoading = false;
	let featuredSearchTimer: ReturnType<typeof setTimeout> | null = null;
	let lastFeaturedQuery = '';
	let featuredSearchRequestId = 0;

	type KnowledgeSearchItem = {
		id?: string;
		name?: string;
		description?: string;
		[key: string]: unknown;
	};

	const maxKnowledgeSearchPages = 500;

	const normalizeKnowledgeName = (name: unknown) =>
		decodeString(`${name ?? ''}`)
			.trim()
			.replace(/\s*\/\s*/g, ' / ');

	const isFeaturedKnowledge = (item: any) => Boolean(item?.id);

	const parseKnowledgeName = (name = '') => {
		const [collection = '', topic = ''] = normalizeKnowledgeName(name).split(' / ');
		return {
			collection: collection.trim(),
			topic: topic.trim() || name
		};
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

	const loadFeaturedItems = async () => {
		const requestId = ++featuredSearchRequestId;
		featuredItemsLoading = true;

		try {
			const allItems = await searchAllKnowledgeBasePages(featuredQuery);
			if (requestId !== featuredSearchRequestId) {
				return;
			}

			featuredItems = allItems
				.filter(isFeaturedKnowledge)
				.sort((a, b) => normalizeKnowledgeName(a.name).localeCompare(normalizeKnowledgeName(b.name)));
		} catch {
			if (requestId === featuredSearchRequestId) {
				featuredItems = [];
			}
		} finally {
			if (requestId === featuredSearchRequestId) {
				featuredItemsLoading = false;
			}
		}
	};

	$: if (loaded) {
		init();
	}

	const init = async () => {
		reset();
		await tick();
		await Promise.all([getItemsPage(), loadFeaturedItems()]);
	};

	const reset = () => {
		page = 1;
		items = null;
		total = null;
		allItemsLoaded = false;
		itemsLoading = false;
	};

	const loadMoreItems = async () => {
		if (allItemsLoaded) return;
		page += 1;
		await getItemsPage();
	};

	const getItemsPage = async () => {
		itemsLoading = true;
		const res = await getKnowledgeBases(localStorage.token, page).catch(() => {
			return null;
		});

		if (res) {
			total = res.total;
			const pageItems = res.items;

			if ((pageItems ?? []).length === 0) {
				allItemsLoaded = true;
			} else {
				allItemsLoaded = false;
			}

			if (items) {
				const existingIds = new Set(items.map((item) => item.id));
				const newItems = pageItems.filter((item) => !existingIds.has(item.id));
				items = [...items, ...newItems];
			} else {
				items = pageItems;
			}
		} else {
			total = total ?? 0;
			items = items ?? [];
			allItemsLoaded = true;
		}

		itemsLoading = false;
		return res;
	};

	$: if (loaded && featuredQuery !== lastFeaturedQuery) {
		lastFeaturedQuery = featuredQuery;
		if (featuredSearchTimer) {
			clearTimeout(featuredSearchTimer);
		}
		featuredSearchTimer = setTimeout(() => {
			void loadFeaturedItems();
		}, 250);
	}

	onMount(async () => {
		await tick();
		loaded = true;
	});

	onDestroy(() => {
		if (featuredSearchTimer) {
			clearTimeout(featuredSearchTimer);
		}
	});
</script>

{#if loaded && items !== null}
	<div class="flex flex-col gap-0.5">
		<div class="mb-1 border-b border-gray-100 pb-2 dark:border-gray-800">
			<div class="mb-1 flex items-center justify-between gap-2 px-2 text-[11px] font-medium uppercase text-gray-500 dark:text-gray-400">
				<div>{$i18n.t('Featured Knowledge')}</div>
				{#if featuredItemsLoading}
					<Spinner className="size-3" />
				{/if}
			</div>

			<input
				class="mb-1 w-full rounded-lg border border-gray-100 bg-white px-2.5 py-1.5 text-xs outline-hidden placeholder:text-gray-400 focus:border-gray-300 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700"
				bind:value={featuredQuery}
				placeholder={$i18n.t('Search collection, source, or topic')}
				aria-label={$i18n.t('Search featured knowledge')}
			/>

			{#if featuredItems.length > 0}
				<div class="max-h-64 overflow-y-auto pr-1">
					{#each featuredItems as item (item.id)}
						{@const parsed = parseKnowledgeName(decodeString(item?.name))}
						<button
							class="w-full rounded-xl px-2.5 py-2 text-left text-sm transition hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-100"
							type="button"
							on:click={() => {
								onSelect({
									type: 'collection',
									...item
								});
							}}
						>
							<div class="flex items-start gap-2">
								<Tooltip content={$i18n.t('Collection')} placement="top">
									<Database className="mt-0.5 size-4 shrink-0" />
								</Tooltip>

								<div class="min-w-0 flex-1">
									<div class="flex min-w-0 items-center gap-1.5">
										<div class="max-w-24 shrink-0 truncate rounded-md bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">
											{parsed.collection}
										</div>
										<div class="line-clamp-1 text-sm font-medium text-gray-900 dark:text-gray-100">
											{parsed.topic}
										</div>
									</div>
									{#if item.description}
										<div class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">
											{item.description}
										</div>
									{/if}
								</div>
							</div>
						</button>
					{/each}
				</div>
			{:else if !featuredItemsLoading}
				<div class="px-2 py-2 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('No featured knowledge found.')}
				</div>
			{/if}
		</div>

		{#if items.length === 0}
			<div class="py-4 text-center text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('No knowledge bases found.')}
			</div>
		{:else}
			{#each items as item, idx (item.id)}
				<div
					class=" px-2.5 py-1 rounded-xl w-full text-left flex justify-between items-center text-sm {idx ===
					selectedIdx
						? ' bg-gray-50 dark:bg-gray-800 dark:text-gray-100 selected-command-option-button'
						: ''}"
				>
					<button
						class="w-full flex-1"
						type="button"
						on:click={() => {
							onSelect({
								type: 'collection',
								...item
							});
						}}
						on:mousemove={() => {
							selectedIdx = idx;
						}}
						on:mouseleave={() => {
							if (idx === 0) {
								selectedIdx = -1;
							}
						}}
						data-selected={idx === selectedIdx}
					>
						<div class="w-full text-left text-black dark:text-gray-100 flex items-center gap-1">
							<Tooltip content={$i18n.t('Collection')} placement="top">
								<Database className="size-4" />
							</Tooltip>

							<Tooltip
								content={item.description || decodeString(item?.name)}
								placement="top-start"
								className="flex flex-1 min-w-0"
							>
								<div class="line-clamp-1 flex-1 text-sm">
									{decodeString(item?.name)}
								</div>
							</Tooltip>
						</div>
					</button>

					<Tooltip content={$i18n.t('Show Files')} placement="top">
						<button
							type="button"
							class=" ml-2 opacity-50 hover:opacity-100 transition"
							on:click={() => {
								if (selectedItem && selectedItem.id === item.id) {
									selectedItem = null;
								} else {
									selectedItem = item;
								}
							}}
						>
							{#if selectedItem && selectedItem.id === item.id}
								<ChevronDown className="size-3" />
							{:else}
								<ChevronRight className="size-3" />
							{/if}
						</button>
					</Tooltip>
				</div>

				{#if selectedItem && selectedItem.id === item.id}
					<div class="pl-3 mb-1 flex flex-col gap-0.5">
						{#if selectedFileItems === null && selectedFileItemsTotal === null}
							<div class=" py-1 flex justify-center">
								<Spinner className="size-3" />
							</div>
						{:else if selectedFileItemsTotal === 0}
							<div class=" text-xs text-gray-500 dark:text-gray-400 italic py-0.5 px-2">
								{$i18n.t('No files in this knowledge base.')}
							</div>
						{:else}
							{#each selectedFileItems as file, fileIdx (file.id)}
								<button
									class=" px-2.5 py-1 rounded-xl w-full text-left flex justify-between items-center text-sm hover:bg-gray-50 hover:dark:bg-gray-800 hover:dark:text-gray-100"
									type="button"
									on:click={() => {
										onSelect({
											type: 'file',
											name: file?.meta?.name,
											...file
										});
									}}
								>
									<div class=" flex items-center gap-1.5">
										<Tooltip content={$i18n.t('Collection')} placement="top">
											<DocumentPage className="size-4" />
										</Tooltip>

										<Tooltip content={decodeString(file?.meta?.name)} placement="top-start">
											<div class="line-clamp-1 flex-1 text-sm">
												{decodeString(file?.meta?.name)}
											</div>
										</Tooltip>
									</div>
								</button>
							{/each}

							{#if !selectedFileAllItemsLoaded && !selectedFileItemsLoading}
								<Loader
									on:visible={async (e) => {
										if (!selectedFileItemsLoading) {
											await loadMoreSelectedFileItems();
										}
									}}
								>
									<div
										class="w-full flex justify-center py-4 text-xs animate-pulse items-center gap-2"
									>
										<Spinner className=" size-3" />
										<div class=" ">{$i18n.t('Loading...')}</div>
									</div>
								</Loader>
							{/if}
						{/if}
					</div>
				{/if}
			{/each}

			{#if !allItemsLoaded}
				<Loader
					on:visible={(e) => {
						if (!itemsLoading) {
							loadMoreItems();
						}
					}}
				>
					<div class="w-full flex justify-center py-4 text-xs animate-pulse items-center gap-2">
						<Spinner className=" size-4" />
						<div class=" ">{$i18n.t('Loading...')}</div>
					</div>
				</Loader>
			{/if}
		{/if}
	</div>
{:else}
	<div class="py-4.5">
		<Spinner />
	</div>
{/if}
