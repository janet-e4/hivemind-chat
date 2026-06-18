<script lang="ts">
	import { getContext, onDestroy, tick } from 'svelte';
	import { type Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { models, settings, mobile } from '$lib/stores';
	import { createMessagesList } from '$lib/utils';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let history: any = {};
	export let messagesRef: any;
	export let scrollContainerElement: HTMLDivElement | undefined;
	export let readOnly = false;
	export let layout: 'floating' | 'rail' | 'panel' = 'floating';

	let currentScrollContainer: HTMLDivElement | undefined;
	let activeMessageId = '';
	let hoveredMessageId = '';
	let focusedMessageId = '';
	let scrollTop = 0;
	let scrollHeight = 1;
	let clientHeight = 1;
	let branchMessages: any[] = [];
	let visible = false;
	let previewMessage: any = null;
	let viewportTop = '0%';
	let viewportHeight = '8%';
	let embedded = false;
	let pendingFrame: number | null = null;
	let removeScrollListener: (() => void) | null = null;

	const roleLabel = (role: string) => (role === 'user' ? $i18n.t('User') : $i18n.t('Assistant'));

	const stripPreview = (content = '') => {
		return content
			.replace(/```[\s\S]*?```/g, ' ')
			.replace(/<details[\s\S]*?<\/details>/gi, ' ')
			.replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
			.replace(/\[[^\]]+\]\([^)]+\)/g, '$1')
			.replace(/[#*_`>~|{}[\]()]/g, ' ')
			.replace(/\s+/g, ' ')
			.trim();
	};

	const getSiblingIds = (message: any) => {
		if (!message || !history?.messages) {
			return [];
		}

		if (message.parentId !== null && history.messages[message.parentId]) {
			return history.messages[message.parentId].childrenIds ?? [];
		}

		return Object.values(history.messages)
			.filter((msg: any) => msg.parentId === null)
			.map((msg: any) => msg.id);
	};

	const getBranchMeta = (message: any) => {
		const siblings = getSiblingIds(message);
		return {
			count: siblings.length,
			index: Math.max(siblings.indexOf(message?.id), 0) + 1
		};
	};

	const getModelActions = (message: any) => {
		const model = ($models ?? []).find((model: any) => model.id === message?.model) as any;
		return model?.actions ?? [];
	};

	const getActions = (message: any) => {
		const delegatedActions = messagesRef?.getMessageActionState?.(message.id);
		if (delegatedActions?.length) {
			return delegatedActions;
		}

		const siblings = getSiblingIds(message);
		const actions = [];

		if (siblings.length > 1) {
			actions.push({ id: 'previous', label: $i18n.t('Previous message') });
			actions.push({ id: 'next', label: $i18n.t('Next message') });
		}

		if (!readOnly) {
			actions.push({ id: 'edit', label: $i18n.t('Edit') });
		}

		if (message?.content) {
			actions.push({ id: 'copy', label: $i18n.t('Copy') });
		}

		if (message?.role !== 'user' && message?.done) {
			if (!readOnly) {
				actions.push({ id: 'speak', label: $i18n.t('Read Aloud') });
			}

			if (message?.usage) {
				actions.push({ id: 'info', label: $i18n.t('Info') });
			}

			if (!readOnly) {
				actions.push({ id: 'good', label: $i18n.t('Good Response') });
				actions.push({ id: 'bad', label: $i18n.t('Bad Response') });
				if (message.id === history?.currentId) {
					actions.push({ id: 'continue', label: $i18n.t('Continue Response') });
				}
				actions.push({ id: 'regenerate', label: $i18n.t('Regenerate') });

				getModelActions(message).forEach((action: any) => {
					actions.push({
						id: `model-action-${action.id}`,
						label: action.name ?? action.id
					});
				});
			}
		}

		if (!readOnly && (message?.role !== 'user' || siblings.length > 1)) {
			actions.push({ id: 'delete', label: $i18n.t('Delete'), destructive: true });
		}

		return actions;
	};

	const getMarkerHeight = (message: any) => {
		const length = stripPreview(message?.content ?? '').length;
		const height = 8 + Math.min(26, Math.floor(length / 120) * 4);
		return `${height}px`;
	};

	const updateViewport = () => {
		if (!currentScrollContainer) {
			return;
		}

		scrollTop = currentScrollContainer.scrollTop;
		scrollHeight = Math.max(currentScrollContainer.scrollHeight, 1);
		clientHeight = Math.max(currentScrollContainer.clientHeight, 1);

		const messages = branchMessages;
		let nextActiveMessageId = messages.at(0)?.id ?? '';
		const activeTop = scrollTop + clientHeight * 0.28;

		for (const message of messages) {
			const element = document.getElementById(`message-${message.id}`);
			if (element && element.offsetTop <= activeTop) {
				nextActiveMessageId = message.id;
			}
		}

		activeMessageId = nextActiveMessageId;
	};

	const scheduleViewportUpdate = () => {
		if (pendingFrame !== null) {
			return;
		}

		pendingFrame = requestAnimationFrame(() => {
			pendingFrame = null;
			updateViewport();
		});
	};

	const bindScrollContainer = (element: HTMLDivElement | undefined) => {
		removeScrollListener?.();
		removeScrollListener = null;
		currentScrollContainer = element;

		if (!currentScrollContainer) {
			return;
		}

		currentScrollContainer.addEventListener('scroll', scheduleViewportUpdate, { passive: true });
		removeScrollListener = () => {
			currentScrollContainer?.removeEventListener('scroll', scheduleViewportUpdate);
		};

		scheduleViewportUpdate();
	};

	const jumpToMessage = async (messageId: string) => {
		await messagesRef?.scrollToMessage?.(messageId, { behavior: 'smooth', block: 'start' });
		scheduleViewportUpdate();
	};

	const runAction = async (messageId: string, actionId: string) => {
		await messagesRef?.runMessageAction?.(messageId, actionId);
		await tick();
		scheduleViewportUpdate();
	};

	const handleMarkerKeydown = (event: KeyboardEvent, messageId: string) => {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			jumpToMessage(messageId);
		}
	};

	$: branchMessages =
		history?.messages && history?.currentId ? createMessagesList(history, history.currentId) : [];
	$: embedded = layout !== 'floating';
	$: visible =
		(embedded || ($settings?.showConversationMinimap ?? true)) &&
		!$mobile &&
		(embedded || branchMessages.length > 1);
	$: previewMessage =
		history?.messages?.[hoveredMessageId] ?? history?.messages?.[focusedMessageId] ?? null;
	$: viewportTop = `${Math.max(0, Math.min(100, (scrollTop / scrollHeight) * 100))}%`;
	$: viewportHeight = `${Math.max(8, Math.min(100, (clientHeight / scrollHeight) * 100))}%`;
	$: if (scrollContainerElement !== currentScrollContainer) {
		bindScrollContainer(scrollContainerElement);
	}
	$: if (visible && branchMessages.length) {
		scheduleViewportUpdate();
	}

	onDestroy(() => {
		removeScrollListener?.();
		if (pendingFrame !== null) {
			cancelAnimationFrame(pendingFrame);
		}
	});
</script>

{#if visible}
	<nav
		data-testid="conversation-minimap"
		data-layout={layout}
		data-message-count={branchMessages.length}
		class={layout === 'floating'
			? 'conversation-minimap pointer-events-auto fixed right-4 top-24 z-20 hidden max-h-[calc(100vh-12rem)] items-center gap-2 md:flex'
			: layout === 'panel'
				? 'conversation-minimap flex h-full min-h-0 w-full items-stretch gap-3'
				: 'conversation-minimap flex h-full min-h-0 w-full items-stretch'}
		aria-label={$i18n.t('Conversation quick browse')}
	>
		{#if layout !== 'rail' && (previewMessage || layout === 'panel')}
			{@const branch = getBranchMeta(previewMessage)}
			<aside
				class={layout === 'panel'
					? 'flex min-h-0 flex-1 flex-col rounded-lg border border-gray-200 bg-white/95 p-3 text-xs shadow-sm backdrop-blur dark:border-gray-800 dark:bg-gray-950/95'
					: 'w-72 rounded-lg border border-gray-200 bg-white/95 p-3 text-xs shadow-xl backdrop-blur dark:border-gray-800 dark:bg-gray-950/95'}
				data-testid="conversation-minimap-preview"
				on:mouseenter={() => {
					if (previewMessage) {
						hoveredMessageId = previewMessage.id;
					}
				}}
				on:mouseleave={() => {
					hoveredMessageId = '';
				}}
			>
				{#if previewMessage}
					<div class="mb-2 flex items-center justify-between gap-2">
						<div class="min-w-0 font-medium text-gray-800 dark:text-gray-100">
							{roleLabel(previewMessage.role)}
							{#if previewMessage.model}
								<span class="font-normal text-gray-500 dark:text-gray-400">
									- {previewMessage.model}
								</span>
							{/if}
						</div>

						{#if branch.count > 1}
							<div class="shrink-0 text-gray-500 dark:text-gray-400">
								{branch.index}/{branch.count}
							</div>
						{/if}
					</div>

					<button
						type="button"
						class="line-clamp-5 w-full text-left leading-5 text-gray-700 hover:text-gray-950 dark:text-gray-300 dark:hover:text-white"
						data-testid="conversation-minimap-preview-jump"
						on:click={() => jumpToMessage(previewMessage.id)}
					>
						{stripPreview(previewMessage.content) || $i18n.t('Empty message')}
					</button>

					<div class="mt-3 flex flex-wrap gap-1.5">
						{#each getActions(previewMessage) as action (action.id)}
							<button
								type="button"
								disabled={action.disabled}
								class="rounded-md border px-2 py-1 text-[11px] font-medium transition {action.destructive
									? 'border-red-200 text-red-600 hover:bg-red-50 dark:border-red-900/70 dark:text-red-300 dark:hover:bg-red-950/40'
									: 'border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-900'} disabled:cursor-not-allowed disabled:opacity-40"
								data-testid="conversation-minimap-action"
								data-action-id={action.id}
								on:click={(event) => {
									event.stopPropagation();
									runAction(previewMessage.id, action.id);
								}}
							>
								{action.label}
							</button>
						{/each}
					</div>
				{:else}
					<div
						class="flex h-full min-h-32 items-center justify-center text-center text-xs text-gray-500 dark:text-gray-400"
						data-testid="conversation-minimap-no-selection"
					>
						{$i18n.t('No message selected')}
					</div>
				{/if}
			</aside>
		{/if}

		<div
			data-testid="conversation-minimap-markers"
			data-layout={layout}
			class={layout === 'floating'
				? 'relative flex max-h-[calc(100vh-12rem)] w-11 flex-col gap-1 overflow-hidden rounded-lg border border-gray-200 bg-white/85 p-1.5 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-950/85'
				: layout === 'panel'
					? 'relative flex h-full min-h-0 w-12 shrink-0 flex-col gap-1 overflow-hidden rounded-lg border border-gray-200 bg-white/85 p-1.5 shadow-sm backdrop-blur dark:border-gray-800 dark:bg-gray-950/85'
					: 'relative flex h-full min-h-0 w-full flex-col gap-1 overflow-hidden rounded-md border border-gray-200 bg-white/80 p-1 shadow-sm backdrop-blur dark:border-gray-800 dark:bg-gray-950/80'}
		>
			{#if branchMessages.length > 1}
				<div
					class="pointer-events-none absolute inset-x-1 rounded-md border border-gray-400/60 bg-gray-500/10 dark:border-gray-300/40"
					style:top={viewportTop}
					style:height={viewportHeight}
					data-testid="conversation-minimap-viewport"
				></div>

				{#each branchMessages as message, idx (message.id)}
					{@const branch = getBranchMeta(message)}
					<button
						type="button"
						data-testid="conversation-minimap-marker"
						class="relative z-10 w-full rounded-sm transition hover:opacity-100 focus:outline-hidden focus:ring-2 focus:ring-gray-500/60 {message.id ===
						activeMessageId
							? 'opacity-100'
							: 'opacity-60'} {message.role === 'user'
							? 'bg-sky-500 dark:bg-sky-400'
							: message.error
								? 'bg-red-500 dark:bg-red-400'
								: message.done === false
									? 'bg-amber-500 dark:bg-amber-400'
									: 'bg-emerald-500 dark:bg-emerald-400'}"
						style:height={getMarkerHeight(message)}
						aria-label={`${$i18n.t('Jump to message')} ${idx + 1}: ${roleLabel(message.role)}`}
						data-message-id={message.id}
						data-message-role={message.role}
						data-message-index={idx + 1}
						on:mouseenter={() => {
							hoveredMessageId = message.id;
						}}
						on:mouseleave={() => {
							hoveredMessageId = '';
						}}
						on:focus={() => {
							focusedMessageId = message.id;
						}}
						on:blur={() => {
							focusedMessageId = '';
						}}
						on:keydown={(event) => handleMarkerKeydown(event, message.id)}
						on:click={() => jumpToMessage(message.id)}
					>
						<span class="sr-only">{stripPreview(message.content)}</span>
						{#if branch.count > 1}
							<span class="absolute right-0 top-0 size-1.5 rounded-full bg-white dark:bg-gray-950"
							></span>
						{/if}
						{#if message.files?.length || message.sources?.length || message.citations?.length}
							<span
								class="absolute bottom-0 left-0 size-1.5 rounded-full bg-white/90 dark:bg-gray-950/90"
							></span>
						{/if}
					</button>
				{/each}
			{:else}
				<div
					class="flex h-full min-h-24 items-center justify-center px-1 text-center text-[10px] leading-4 text-gray-400 dark:text-gray-500"
					data-testid="conversation-minimap-empty"
				>
					{$i18n.t('No map yet')}
				</div>
			{/if}
		</div>
	</nav>
{/if}
