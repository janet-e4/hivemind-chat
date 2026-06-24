<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import {
		settings,
		showControls,
		showFileNavDir,
		terminalServers,
		selectedTerminalId
	} from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import {
		getCwd,
		getTerminalConfig,
		getTerminalServers,
		listFiles,
		searchFiles,
		readFile,
		downloadFileBlob,
		type FileEntry
	} from '$lib/apis/terminal';
	import { formatFileSize } from '$lib/utils';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import FolderOpen from '$lib/components/icons/FolderOpen.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import DocumentArrowUp from '$lib/components/icons/DocumentArrowUp.svelte';
	import Clipboard from '$lib/components/icons/Clipboard.svelte';
	import Refresh from '$lib/components/icons/Refresh.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import FilePreviewModal from '$lib/components/chat/FilePreviewModal.svelte';

	const i18n = getContext('i18n');

	export let chatId: string | null = null;
	export let onInsertPath: (path: string) => void = () => {};
	export let onAttachFile: (
		blob: Blob,
		name: string,
		contentType: string
	) => Promise<void> | void = async () => {};
	export let navToPath: string | null = null;

	let selectedTerminal: { url: string; key: string } | null = null;
	let terminalEnabled = true;
	let currentPath = '/';
	let initialCwd = '/';
	let entries: FileEntry[] = [];
	let loading = false;
	let error = '';
	let mounted = false;
	let previousTerminalSignature = '';
	let previousChatId = chatId;
	let loadingSystemTerminals = false;
	let systemTerminalsLoaded = false;
	let searchQuery = '';
	let activeSearchQuery = '';
	let recursiveSearch = true;
	let searchLoading = false;
	let searchResults: FileEntry[] = [];
	let searchRunId = 0;
	let searchInput: HTMLInputElement | null = null;
	let displayedEntries: FileEntry[] = [];
	let filteredCountLabel = '0';

	let previewPath = '';
	let previewContent: string | null = null;
	let previewLoading = false;
	let previewError = '';
	let showPreview = false;

	type TerminalConnection = { url: string; key: string };
	type SortMode = 'name' | 'modified' | 'created' | 'size';

	let sortBy: SortMode = 'name';
	let sortAsc = true;

	const normalizePath = (path: string) => {
		let normalized = `${path || '/'}`.trim();
		if (!normalized.startsWith('/')) normalized = `/${normalized}`;
		normalized = normalized.replace(/\/+/g, '/');
		return normalized.endsWith('/') ? normalized : `${normalized}/`;
	};

	const hydrateSystemTerminals = async () => {
		if (loadingSystemTerminals || systemTerminalsLoaded) {
			return;
		}

		if (($terminalServers ?? []).some((terminal) => terminal.id)) {
			systemTerminalsLoaded = true;
			return;
		}

		const token = localStorage.token;
		if (!token) {
			systemTerminalsLoaded = true;
			return;
		}

		loadingSystemTerminals = true;
		try {
			const systemTerminals = await getTerminalServers(token);
			const systemEntries = systemTerminals
				.filter((terminal) => terminal?.id)
				.map((terminal) => ({
					id: terminal.id,
					url: `${WEBUI_API_BASE_URL}/terminals/${terminal.id}`,
					name: terminal.name,
					key: token
				}));

			if (systemEntries.length > 0) {
				const directTerminals = ($terminalServers ?? []).filter((terminal) => !terminal.id);
				terminalServers.set([...directTerminals, ...systemEntries]);
			}
		} catch (err) {
			console.error('Failed to load system terminal servers:', err);
		} finally {
			systemTerminalsLoaded = true;
			loadingSystemTerminals = false;
		}
	};

	const getTerminal = (): TerminalConnection | null => {
		const systemTerminal = $selectedTerminalId
			? (($terminalServers ?? []).find((terminal) => terminal.id === $selectedTerminalId) ?? null)
			: ($terminalServers?.[0] ?? null);

		const userTerminal = ($settings?.terminalServers ?? []).find(
			(server) => server.url === $selectedTerminalId
		);

		const isSystem = !!systemTerminal;
		const url = systemTerminal?.url ?? userTerminal?.url ?? '';
		const key = isSystem ? localStorage.token : (userTerminal?.key ?? '');

		return url ? { url, key } : null;
	};

	const sortEntries = (items: FileEntry[]) => {
		return [...items].sort((a, b) => {
			if (a.type !== b.type) {
				return a.type === 'directory' ? -1 : 1;
			}
			if (sortBy === 'modified') {
				const aTime = a.modified ?? 0;
				const bTime = b.modified ?? 0;
				return sortAsc ? aTime - bTime : bTime - aTime;
			}
			if (sortBy === 'created') {
				const aTime = a.created ?? 0;
				const bTime = b.created ?? 0;
				return sortAsc ? aTime - bTime : bTime - aTime;
			}
			if (sortBy === 'size') {
				const aSize = a.type === 'directory' ? -1 : (a.size ?? 0);
				const bSize = b.type === 'directory' ? -1 : (b.size ?? 0);
				return sortAsc ? aSize - bSize : bSize - aSize;
			}
			return a.name.localeCompare(b.name);
		});
	};

	const toggleSort = (mode: SortMode) => {
		if (sortBy === mode) {
			sortAsc = !sortAsc;
		} else {
			sortBy = mode;
			sortAsc = mode === 'name';
		}
		entries = sortEntries(entries);
		searchResults = sortEntries(searchResults);
	};

	const entryPath = (entry: FileEntry) =>
		entry.type === 'directory'
			? `${currentPath}${entry.name.replace(/^\/+/, '')}/`
			: `${currentPath}${entry.name.replace(/^\/+/, '')}`;

	const normalizeSearchEntry = (entry: FileEntry, basePath: string): FileEntry => {
		let name = `${entry.name ?? ''}`.replace(/\\/g, '/').replace(/^\.\//, '');

		if (basePath !== '/' && name.startsWith(basePath)) {
			name = name.slice(basePath.length);
		} else if (basePath === '/' && name.startsWith('/')) {
			name = name.slice(1);
		}

		name = name.replace(/^\/+/, '').replace(/\/+$/, '');
		return { ...entry, name };
	};

	const joinPath = (dir: string, name: string) => {
		const normalizedDir = dir.endsWith('/') ? dir : `${dir}/`;
		return `${normalizedDir}${name.replace(/^\/+/, '')}`;
	};

	const clearSearch = () => {
		searchRunId += 1;
		searchQuery = '';
		activeSearchQuery = '';
		searchResults = [];
		searchLoading = false;
	};

	const formatDate = (epoch?: number): string => {
		if (!epoch) return '—';
		return new Intl.DateTimeFormat(undefined, {
			month: 'numeric',
			day: 'numeric',
			year: '2-digit'
		}).format(new Date(epoch * 1000));
	};

	const formatDateTitle = (epoch?: number): string | undefined => {
		if (!epoch) return undefined;
		return new Intl.DateTimeFormat(undefined, {
			dateStyle: 'medium',
			timeStyle: 'short'
		}).format(new Date(epoch * 1000));
	};

	const loadDir = async (path: string) => {
		if (!selectedTerminal || !terminalEnabled) {
			return;
		}

		loading = true;
		error = '';

		const nextPath = normalizePath(path);
		const pathChanged = nextPath !== currentPath;
		const result = await listFiles(
			selectedTerminal.url,
			selectedTerminal.key,
			nextPath,
			chatId ?? undefined
		);

		if (result === null) {
			entries = [];
			error = $i18n.t('Unable to load files');
			loading = false;
			return;
		}

		currentPath = nextPath;
		entries = sortEntries(result);
		if (pathChanged) {
			clearSearch();
		}
		loading = false;
	};

	const refresh = async () => {
		await loadDir(currentPath);
	};

	const openFullBrowser = () => {
		showControls.set(true);
		showFileNavDir.set(currentPath);
	};

	const insertCurrentPath = () => {
		onInsertPath(currentPath);
	};

	const insertEntryPath = (entry: FileEntry) => {
		onInsertPath(entryPath(entry));
	};

	const attachEntryFile = async (entry: FileEntry) => {
		if (entry.type !== 'file' || !selectedTerminal || loading) {
			return;
		}

		const filePath = entryPath(entry);
		const downloaded = await downloadFileBlob(
			selectedTerminal.url,
			selectedTerminal.key,
			filePath,
			chatId ?? undefined
		);

		if (!downloaded) {
			error = $i18n.t('Unable to attach file');
			return;
		}

		await onAttachFile(
			downloaded.blob,
			downloaded.filename,
			downloaded.blob.type || 'application/octet-stream'
		);
	};

	const handleEntryClick = (entry: FileEntry) => {
		if (entry.type === 'directory') {
			void loadDir(entryPath(entry));
			return;
		}

		void openPreview(entryPath(entry));
	};

	const performSearch = async () => {
		if (!selectedTerminal || !terminalEnabled || loading || previewLoading) {
			return;
		}

		const query = searchQuery.trim();
		const basePath = currentPath;
		const runId = ++searchRunId;

		activeSearchQuery = query;
		searchResults = [];

		if (!query) {
			searchLoading = false;
			return;
		}

		searchLoading = true;

		const endpointResults = await searchFiles(
			selectedTerminal.url,
			selectedTerminal.key,
			query,
			basePath,
			recursiveSearch,
			chatId ?? undefined
		);

		if (runId !== searchRunId) return;

		if (endpointResults) {
			searchResults = sortEntries(
				endpointResults
					.map((entry) => normalizeSearchEntry(entry, basePath))
					.filter((entry) => entry.name)
			);
			searchLoading = false;
			return;
		}

		const normalizedQuery = query.toLowerCase();

		if (!recursiveSearch) {
			searchResults = sortEntries(
				entries.filter(
					(entry) =>
						entry.name.toLowerCase().includes(normalizedQuery) ||
						entryPath(entry).toLowerCase().includes(normalizedQuery)
				)
			);
			searchLoading = false;
			return;
		}

		const matches: FileEntry[] = [];
		const pending = [basePath];
		const visited = new Set<string>();
		const maxVisitedDirs = 500;

		while (pending.length > 0 && visited.size < maxVisitedDirs) {
			if (runId !== searchRunId) return;

			const dir = pending.shift() ?? '/';
			if (visited.has(dir)) continue;
			visited.add(dir);

			const result = await listFiles(
				selectedTerminal.url,
				selectedTerminal.key,
				dir,
				chatId ?? undefined
			);
			if (runId !== searchRunId) return;
			if (!result) continue;

			for (const entry of result) {
				const fullPath = joinPath(dir, entry.name);
				const relativeName = fullPath.startsWith(basePath)
					? fullPath.slice(basePath.length)
					: fullPath;

				if (
					entry.name.toLowerCase().includes(normalizedQuery) ||
					relativeName.toLowerCase().includes(normalizedQuery)
				) {
					matches.push({ ...entry, name: relativeName.replace(/^\/+/, '') });
				}

				if (entry.type === 'directory') {
					pending.push(`${fullPath}/`);
				}
			}
		}

		if (runId !== searchRunId) return;

		searchResults = sortEntries(matches);
		searchLoading = false;
	};

	const goUp = () => {
		if (currentPath === '/') return;
		const trimmed = currentPath.endsWith('/') ? currentPath.slice(0, -1) : currentPath;
		const parent = trimmed.substring(0, trimmed.lastIndexOf('/') + 1) || '/';
		void loadDir(parent);
	};

	const openPreview = async (filePath: string) => {
		if (!selectedTerminal || !terminalEnabled) return;
		previewPath = filePath;
		previewContent = null;
		previewError = '';
		previewLoading = true;
		showPreview = true;

		try {
			const content = await readFile(
				selectedTerminal.url,
				selectedTerminal.key,
				filePath,
				chatId ?? undefined
			);
			previewContent = content;
			if (content === null) {
				previewError = $i18n.t('Unable to read file');
			}
		} catch {
			previewError = $i18n.t('Unable to read file');
		} finally {
			previewLoading = false;
		}
	};

	const resolveNavPath = (rawPath: string): string => {
		if (rawPath.startsWith('/')) return rawPath;
		// Resolve relative to initialCwd
		const base = initialCwd.endsWith('/') ? initialCwd : `${initialCwd}/`;
		const combined = `${base}${rawPath.replace(/^\.\//, '')}`;
		// Normalize: collapse /./  and /../
		const parts = combined.split('/');
		const resolved: string[] = [];
		for (const part of parts) {
			if (part === '' || part === '.') continue;
			if (part === '..') {
				resolved.pop();
			} else {
				resolved.push(part);
			}
		}
		return `/${resolved.join('/')}`;
	};

	const handleNavToPath = async (rawPath: string) => {
		if (!selectedTerminal || !terminalEnabled || !rawPath) return;
		const abs = resolveNavPath(rawPath);
		const isDir = abs.endsWith('/');
		const dirPath = isDir ? abs : abs.substring(0, abs.lastIndexOf('/') + 1) || '/';

		await loadDir(dirPath);

		if (!isDir) {
			void openPreview(abs);
		}
	};

	const init = async () => {
		await hydrateSystemTerminals();

		selectedTerminal = getTerminal();
		if (!selectedTerminal) {
			terminalEnabled = true;
			return;
		}

		const config = await getTerminalConfig(selectedTerminal.url, selectedTerminal.key);
		terminalEnabled = config?.features?.terminal !== false;

		if (!terminalEnabled) {
			error = $i18n.t('Terminal access is disabled');
			return;
		}

		const cwd = await getCwd(selectedTerminal.url, selectedTerminal.key, chatId ?? undefined);
		const cwdNorm = cwd ? normalizePath(cwd) : '/';
		initialCwd = cwdNorm.endsWith('/') ? cwdNorm.slice(0, -1) || '/' : cwdNorm;
		await loadDir(cwdNorm);
	};

	$: displayedEntries = activeSearchQuery ? searchResults : entries;
	$: filteredCountLabel =
		activeSearchQuery.trim().length > 0 ? `${displayedEntries.length}` : `${entries.length}`;

	onMount(() => {
		mounted = true;
		void init();
	});

	$: {
		($selectedTerminalId, $terminalServers, $settings);
		const terminal = getTerminal();
		const signature = terminal ? `${terminal.url}::${terminal.key}` : '';
		if (signature !== previousTerminalSignature) {
			previousTerminalSignature = signature;
			selectedTerminal = terminal;
			if (mounted) {
				void init();
			}
		}
	}

	$: if (mounted && chatId !== previousChatId) {
		previousChatId = chatId;
		if (selectedTerminal && terminalEnabled) {
			void init();
		}
	}

	$: if (mounted && navToPath) {
		void handleNavToPath(navToPath);
	}
</script>

{#if showPreview}
	<FilePreviewModal
		path={previewPath}
		content={previewContent}
		loading={previewLoading}
		error={previewError}
		onClose={() => {
			showPreview = false;
		}}
	/>
{/if}

<div class="flex h-full min-h-0 flex-col gap-2 text-xs">
	<div class="flex items-center gap-1">
		<Tooltip content={$i18n.t('Up')}>
			<button
				type="button"
				class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
				disabled={!selectedTerminal || loading || currentPath === '/'}
				on:click={goUp}
				aria-label={$i18n.t('Up')}
			>
				<ChevronUp className="size-3.5" />
			</button>
		</Tooltip>

		<div
			class="min-w-0 flex-1 truncate rounded-md border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300"
			title={currentPath}
		>
			{currentPath}
			<span class="ml-1 text-gray-400 dark:text-gray-500">{filteredCountLabel}</span>
		</div>

		<Tooltip content={$i18n.t('Insert path')}>
			<button
				type="button"
				class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
				disabled={!selectedTerminal || loading}
				on:click={insertCurrentPath}
				aria-label={$i18n.t('Insert path')}
			>
				<Clipboard className="size-3.5" />
			</button>
		</Tooltip>

		<Tooltip content={$i18n.t('Open full browser')}>
			<button
				type="button"
				class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
				disabled={!selectedTerminal || loading}
				on:click={openFullBrowser}
				aria-label={$i18n.t('Open full browser')}
			>
				<FolderOpen className="size-3.5" />
			</button>
		</Tooltip>

		<Tooltip content={$i18n.t('Refresh')}>
			<button
				type="button"
				class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-40"
				disabled={!selectedTerminal || loading}
				on:click={refresh}
				aria-label={$i18n.t('Refresh')}
			>
				<Refresh className={`size-3.5 ${loading ? 'animate-spin' : ''}`} />
			</button>
		</Tooltip>
	</div>

	<div class="space-y-1">
		<div class="relative">
			<Search
				className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-gray-400 dark:text-gray-500"
			/>
			<input
				bind:this={searchInput}
				bind:value={searchQuery}
				type="search"
				placeholder={$i18n.t('Quick search, then Enter')}
				class="w-full rounded-lg border border-gray-200 bg-white py-2 pl-8 pr-16 text-xs text-gray-700 outline-hidden transition focus:border-gray-300 focus:ring-2 focus:ring-gray-500/20 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200 dark:focus:border-gray-700 dark:focus:ring-gray-400/20"
				on:keydown={(event) => {
					if (event.key === 'Enter') {
						event.preventDefault();
						event.stopPropagation();
						void performSearch();
					}
					if (event.key === 'Escape') {
						clearSearch();
					}
				}}
			/>

			<div class="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
				<Tooltip content={$i18n.t('Search')}>
					<button
						type="button"
						class="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 disabled:cursor-not-allowed disabled:opacity-50 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
						disabled={!selectedTerminal || searchLoading}
						on:click={() => void performSearch()}
						aria-label={$i18n.t('Search')}
					>
						{#if searchLoading}
							<Spinner className="size-3.5" />
						{:else}
							<Search className="size-3.5" />
						{/if}
					</button>
				</Tooltip>

				{#if searchQuery.trim().length > 0 || activeSearchQuery.trim().length > 0}
					<button
						type="button"
						class="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
						on:click={() => {
							clearSearch();
							searchInput?.focus();
						}}
						aria-label={$i18n.t('Clear search')}
					>
						<XMark className="size-3.5" />
					</button>
				{/if}
			</div>
		</div>

		<label
			class="flex w-fit select-none items-center gap-1.5 px-1 text-[11px] text-gray-500 dark:text-gray-400"
		>
			<input
				type="checkbox"
				bind:checked={recursiveSearch}
				class="size-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-850"
				aria-label={$i18n.t('Search all subdirectories')}
			/>
			<span>{$i18n.t('Search subdirectories')}</span>
		</label>
	</div>

	{#if !selectedTerminal}
		<div
			class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-gray-200 bg-white px-3 py-4 text-center text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400"
		>
			{$i18n.t('No terminal connection configured')}
		</div>
	{:else if !terminalEnabled}
		<div
			class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-gray-200 bg-white px-3 py-4 text-center text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400"
		>
			{$i18n.t('Terminal access is disabled')}
		</div>
	{:else if loading}
		<div
			class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-gray-200 bg-white px-3 py-4 text-center dark:border-gray-800 dark:bg-gray-950"
		>
			<Spinner className="size-4" />
		</div>
	{:else if error}
		<div
			class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-gray-200 bg-white px-3 py-4 text-center text-[11px] text-red-500 dark:border-gray-800 dark:bg-gray-950"
		>
			{error}
		</div>
	{:else}
		<div
			class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
		>
			{#if displayedEntries.length === 0}
				<div
					class="flex h-full items-center justify-center px-3 py-6 text-center text-[11px] text-gray-500 dark:text-gray-400"
				>
					{#if activeSearchQuery.trim().length > 0}
						{$i18n.t('No files match your search')}
					{:else}
						{$i18n.t('This folder is empty')}
					{/if}
				</div>
			{:else}
				<div
					class="sticky top-0 z-10 grid grid-cols-[minmax(0,1fr)_4.25rem_5rem_5rem_4.5rem] items-center gap-2 border-b border-gray-100 bg-white/95 px-2 py-1 text-[10px] font-medium uppercase text-gray-400 backdrop-blur dark:border-gray-900 dark:bg-gray-950/95 dark:text-gray-500"
				>
					<button
						type="button"
						class="min-w-0 truncate text-left hover:text-gray-600 dark:hover:text-gray-300"
						on:click={() => toggleSort('name')}
						title={$i18n.t('Sort by name')}
					>
						{$i18n.t('Name')}{sortBy === 'name' ? (sortAsc ? ' ↑' : ' ↓') : ''}
					</button>
					<button
						type="button"
						class="truncate text-right hover:text-gray-600 dark:hover:text-gray-300"
						on:click={() => toggleSort('size')}
						title={$i18n.t('Sort by size')}
					>
						{$i18n.t('Size')}{sortBy === 'size' ? (sortAsc ? ' ↑' : ' ↓') : ''}
					</button>
					<button
						type="button"
						class="truncate text-right hover:text-gray-600 dark:hover:text-gray-300"
						on:click={() => toggleSort('modified')}
						title={$i18n.t('Sort by modified date')}
					>
						{$i18n.t('Modified')}{sortBy === 'modified' ? (sortAsc ? ' ↑' : ' ↓') : ''}
					</button>
					<button
						type="button"
						class="truncate text-right hover:text-gray-600 dark:hover:text-gray-300"
						on:click={() => toggleSort('created')}
						title={$i18n.t('Sort by created date')}
					>
						{$i18n.t('Created')}{sortBy === 'created' ? (sortAsc ? ' ↑' : ' ↓') : ''}
					</button>
					<div aria-hidden="true"></div>
				</div>
				<ul class="divide-y divide-gray-100 dark:divide-gray-900">
					{#each displayedEntries as entry (entryPath(entry))}
						<li>
							<div
								class="flex items-center gap-2 px-2 py-1.5 transition hover:bg-gray-50 dark:hover:bg-gray-900/70"
							>
								<button
									type="button"
									class="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_4.25rem_5rem_5rem] items-center gap-2 text-left"
									on:click={() => handleEntryClick(entry)}
								>
									<div class="flex min-w-0 items-center gap-2">
										{#if entry.type === 'directory'}
											<Folder className="size-4 shrink-0 text-blue-400 dark:text-blue-300" />
										{:else}
											<Document className="size-4 shrink-0 text-gray-400 dark:text-gray-500" />
										{/if}

										<div
											class="min-w-0 flex-1 truncate text-[11px] text-gray-800 dark:text-gray-200"
										>
											{entry.name}
										</div>
									</div>

									<div class="truncate text-right text-[10px] text-gray-400 dark:text-gray-500">
										{entry.size !== undefined && entry.type === 'file'
											? formatFileSize(entry.size)
											: '—'}
									</div>
									<div
										class="truncate text-right text-[10px] text-gray-400 dark:text-gray-500"
										title={formatDateTitle(entry.modified)}
									>
										{formatDate(entry.modified)}
									</div>
									<div
										class="truncate text-right text-[10px] text-gray-400 dark:text-gray-500"
										title={formatDateTitle(entry.created)}
									>
										{formatDate(entry.created)}
									</div>
								</button>

								<Tooltip content={$i18n.t('Insert path')}>
									<button
										type="button"
										class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300"
										on:click={() => insertEntryPath(entry)}
										aria-label={$i18n.t('Insert path')}
									>
										<Clipboard className="size-3.5" />
									</button>
								</Tooltip>

								{#if entry.type === 'file'}
									<Tooltip content={$i18n.t('Attach file')}>
										<button
											type="button"
											class="shrink-0 rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-900 dark:hover:text-gray-300"
											on:click={() => void attachEntryFile(entry)}
											aria-label={$i18n.t('Attach file')}
											disabled={loading}
										>
											<DocumentArrowUp className="size-3.5" />
										</button>
									</Tooltip>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</div>
