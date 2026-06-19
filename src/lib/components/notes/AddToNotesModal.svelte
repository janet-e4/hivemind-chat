<script lang="ts">
	import { getContext } from 'svelte';
	import { marked } from 'marked';
	import { toast } from 'svelte-sonner';

	import dayjs from '$lib/dayjs';
	import Modal from '$lib/components/common/Modal.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Note from '$lib/components/icons/Note.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Refresh from '$lib/components/icons/Refresh.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { createNewNote, getNoteById, searchNotes, updateNoteById } from '$lib/apis/notes';

	const i18n = getContext('i18n');

	export let show = false;
	export let selection = '';
	export let onSaved: () => void = () => {};

	type NoteListItem = {
		id: string;
		title: string;
		data?: {
			content?: {
				md?: string;
			};
		};
		updated_at?: number;
	};

	let mode: 'new' | 'existing' = 'new';
	let title = '';
	let content = '';
	let noteSearch = '';
	let existingNotes: NoteListItem[] = [];
	let selectedNoteId = '';
	let loadingNotes = false;
	let saving = false;
	let error = '';
	let previousShow = false;
	let searchTimer: ReturnType<typeof setTimeout> | null = null;

	const defaultTitle = () => `${$i18n.t('New Note')} ${dayjs().format('YYYY-MM-DD HH:mm')}`;

	const resetState = () => {
		mode = 'new';
		title = defaultTitle();
		content = selection ?? '';
		noteSearch = '';
		existingNotes = [];
		selectedNoteId = '';
		error = '';
	};

	const loadNotes = async () => {
		loadingNotes = true;
		error = '';

		try {
			const result = await searchNotes(
				localStorage.token,
				noteSearch.trim() || null,
				null,
				null,
				'updated_at',
				1
			);

			existingNotes = Array.isArray(result?.items) ? result.items : [];

			if (existingNotes.length > 0) {
				if (!existingNotes.some((note) => note.id === selectedNoteId)) {
					selectedNoteId = existingNotes[0].id;
				}
			} else {
				selectedNoteId = '';
			}
		} catch (err) {
			const message = err instanceof Error ? err.message : String(err);
			error = message;
		} finally {
			loadingNotes = false;
		}
	};

	const saveNote = async () => {
		if (saving) return;

		const trimmedTitle = title.trim();
		const trimmedContent = content.trim();

		if (!trimmedContent) {
			error = $i18n.t('Note content is required');
			return;
		}

		saving = true;
		error = '';

		try {
			if (mode === 'new') {
				await createNewNote(localStorage.token, {
					title: trimmedTitle || defaultTitle(),
					data: {
						content: {
							json: null,
							html: marked.parse(content),
							md: content
						}
					},
					meta: null,
					access_grants: []
				});
				toast.success($i18n.t('Note created successfully'));
			} else {
				if (!selectedNoteId) {
					throw new Error($i18n.t('Please select a note'));
				}

				const existingNote = await getNoteById(localStorage.token, selectedNoteId);
				if (!existingNote) {
					throw new Error($i18n.t('Unable to load note'));
				}

				const existingContent = existingNote.data?.content?.md ?? '';
				const nextContent = existingContent
					? `${existingContent.replace(/\s+$/, '')}\n\n${content}`
					: content;

				await updateNoteById(localStorage.token, selectedNoteId, {
					title: existingNote.title,
					data: {
						content: {
							json: null,
							html: marked.parse(nextContent),
							md: nextContent
						}
					},
					meta: existingNote.meta ?? null,
					access_grants: existingNote.access_grants ?? []
				});
				toast.success($i18n.t('Note updated successfully'));
			}

			show = false;
			onSaved();
		} catch (err) {
			const message = err instanceof Error ? err.message : String(err);
			error = message;
			toast.error(message);
		} finally {
			saving = false;
		}
	};

	$: if (show && !previousShow) {
		resetState();
	}

	$: previousShow = show;

	$: if (show && mode === 'existing') {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			void loadNotes();
		}, 250);
	}

	$: if (!show) {
		clearTimeout(searchTimer);
	}

	const selectExistingNote = (noteId: string) => {
		selectedNoteId = noteId;
		mode = 'existing';
	};
</script>

<Modal size="lg" bind:show>
	<div class="flex max-h-[85vh] flex-col">
		<header
			class="flex items-start justify-between gap-3 border-b border-gray-100 px-5 py-4 dark:border-gray-800"
		>
			<div class="min-w-0">
				<div class="text-sm font-medium text-gray-900 dark:text-gray-100">
					{$i18n.t('Add to Notes')}
				</div>
				<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('Edit the selection before saving it to a new or existing note.')}
				</p>
			</div>
			<button
				type="button"
				class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
				aria-label={$i18n.t('Close')}
				on:click={() => {
					show = false;
				}}
			>
				<XMark className="size-4" />
			</button>
		</header>

		<div class="grid gap-4 px-5 py-4">
			<div class="flex gap-2 rounded-2xl bg-gray-50 p-1 dark:bg-gray-900">
				<button
					type="button"
					class={`flex-1 rounded-xl px-3 py-2 text-sm transition ${
						mode === 'new'
							? 'bg-white text-gray-900 shadow-sm dark:bg-gray-850 dark:text-gray-50'
							: 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
					}`}
					on:click={() => {
						mode = 'new';
					}}
				>
					{$i18n.t('New Note')}
				</button>
				<button
					type="button"
					class={`flex-1 rounded-xl px-3 py-2 text-sm transition ${
						mode === 'existing'
							? 'bg-white text-gray-900 shadow-sm dark:bg-gray-850 dark:text-gray-50'
							: 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100'
					}`}
					on:click={() => {
						mode = 'existing';
						if (existingNotes.length === 0) {
							void loadNotes();
						}
					}}
				>
					{$i18n.t('Existing Note')}
				</button>
			</div>

			{#if mode === 'new'}
				<label class="grid gap-2 text-sm">
					<span class="font-medium text-gray-700 dark:text-gray-200">{$i18n.t('Title')}</span>
					<input
						bind:value={title}
						class="rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-hidden focus:border-gray-300 focus:ring-2 focus:ring-gray-500/20 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700 dark:focus:ring-gray-400/20"
						placeholder={$i18n.t('New Note')}
					/>
				</label>
			{:else}
				<div class="grid gap-2 text-sm">
					<div class="flex items-center justify-between gap-2">
						<span class="font-medium text-gray-700 dark:text-gray-200">
							{$i18n.t('Select a note')}
						</span>
						<button
							type="button"
							class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
							on:click={() => void loadNotes()}
						>
							<Refresh className="size-3.5" />
							{$i18n.t('Refresh')}
						</button>
					</div>
					<div class="relative">
						<Search
							className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-gray-400"
						/>
						<input
							bind:value={noteSearch}
							class="w-full rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 outline-hidden focus:border-gray-300 focus:ring-2 focus:ring-gray-500/20 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700 dark:focus:ring-gray-400/20"
							placeholder={$i18n.t('Search Notes')}
						/>
					</div>

					<div
						class="max-h-56 overflow-y-auto rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
					>
						{#if loadingNotes}
							<div class="flex items-center justify-center py-8 text-gray-500 dark:text-gray-400">
								<Spinner className="size-5" />
							</div>
						{:else if existingNotes.length === 0}
							<div class="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
								{$i18n.t('No Notes')}
							</div>
						{:else}
							<div class="divide-y divide-gray-100 dark:divide-gray-800">
								{#each existingNotes as note (note.id)}
									<button
										type="button"
										class={`flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-gray-50 dark:hover:bg-gray-850 ${
											selectedNoteId === note.id ? 'bg-gray-50 dark:bg-gray-850' : ''
										}`}
										on:click={() => selectExistingNote(note.id)}
									>
										<div
											class="mt-0.5 rounded-lg bg-gray-100 p-2 text-gray-500 dark:bg-gray-800 dark:text-gray-300"
										>
											<Note className="size-4" />
										</div>
										<div class="min-w-0 flex-1">
											<div class="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
												{note.title}
											</div>
											<div class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
												{note.updated_at
													? dayjs(note.updated_at / 1000000).format('LLL')
													: $i18n.t('Unknown')}
											</div>
										</div>
									</button>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			{/if}

			<label class="grid gap-2 text-sm">
				<span class="font-medium text-gray-700 dark:text-gray-200">{$i18n.t('Content')}</span>
				<Textarea
					bind:value={content}
					rows={12}
					className="min-h-56 rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-900 outline-hidden focus:border-gray-300 focus:ring-2 focus:ring-gray-500/20 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:focus:border-gray-700 dark:focus:ring-gray-400/20"
					placeholder={$i18n.t('Add your notes here')}
				/>
			</label>

			{#if error}
				<div
					class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
				>
					{error}
				</div>
			{/if}

			<div class="flex items-center justify-end gap-2">
				<button
					type="button"
					class="rounded-full border border-gray-200 px-4 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-850"
					on:click={() => {
						show = false;
					}}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					type="button"
					class="inline-flex items-center gap-2 rounded-full bg-black px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-900 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-black dark:hover:bg-gray-100"
					disabled={saving || !content.trim() || (mode === 'existing' && !selectedNoteId)}
					on:click={() => void saveNote()}
				>
					{#if saving}
						<Spinner className="size-4" />
					{:else}
						<Plus className="size-4" />
					{/if}
					{mode === 'new' ? $i18n.t('Create Note') : $i18n.t('Add to Note')}
				</button>
			</div>
		</div>
	</div>
</Modal>
