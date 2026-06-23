<script>
	import { onDestroy, onMount, tick, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import Markdown from './Markdown.svelte';
	import {
		artifactCode,
		chatId,
		mobile,
		settings,
		showArtifacts,
		showControls,
		showEmbeds
	} from '$lib/stores';
	import FloatingButtons from '../ContentRenderer/FloatingButtons.svelte';
	import AddToNotesModal from '$lib/components/notes/AddToNotesModal.svelte';
	import { createMessagesList, replaceOutsideCode } from '$lib/utils';

	/**
	 * Extracts all top-level <details>...</details> blocks from content,
	 * handling nested <details> via depth tracking.
	 * Returns { detailsContent, plainContent }.
	 */
	const extractDetailsBlocks = (text) => {
		const blocks = [];
		let remaining = text;
		let result = '';
		const openTag = '<details';
		const closeTag = '</details>';

		while (true) {
			const start = remaining.indexOf(openTag);
			if (start === -1) {
				result += remaining;
				break;
			}

			result += remaining.slice(0, start);

			// Find matching closing tag with depth tracking
			let depth = 1;
			let idx = start + openTag.length;
			while (depth > 0 && idx < remaining.length) {
				if (remaining.startsWith(openTag, idx)) {
					depth++;
				} else if (remaining.startsWith(closeTag, idx)) {
					depth--;
				}
				if (depth > 0) idx++;
			}

			if (depth === 0) {
				const end = idx + closeTag.length;
				blocks.push(remaining.slice(start, end));
				remaining = remaining.slice(end);
			} else {
				// Unmatched opening tag, treat as plain text
				result += remaining.slice(start);
				remaining = '';
				break;
			}
		}

		return {
			detailsContent: blocks.join('\n'),
			plainContent: result.trim()
		};
	};

	export let id;
	export let content;

	export let history;
	export let messageId;

	export let selectedModels = [];

	export let done = true;
	export let model = null;
	export let sources = null;

	export let save = false;
	export let preview = false;
	export let floatingButtons = true;

	export let editCodeBlock = true;
	export let topPadding = false;

	export let onSave = (e) => {};
	export let onSourceClick = (e) => {};
	export let onTaskClick = (e) => {};
	export let onSetInputText = (text) => {};

	let contentContainerElement;
	let floatingButtonsElement;
	let showAddToNotesModal = false;
	let selectedTextForNotes = '';
	let selectedFloatingText = '';

	let sourceIds = [];
	$: getSourceIds(sources);

	const getSourceIds = (sources) => {
		const result = [];
		for (const source of sources ?? []) {
			for (let index = 0; index < (source.document ?? []).length; index++) {
				if (model?.info?.meta?.capabilities?.citations == false) {
					result.push('N/A');
					continue;
				}
				const metadata = source.metadata?.[index];
				const id = metadata?.source ?? 'N/A';
				if (metadata?.name) {
					result.push(metadata.name);
				} else if (id.startsWith('http://') || id.startsWith('https://')) {
					result.push(id);
				} else {
					result.push(source?.source?.name ?? id);
				}
			}
		}
		sourceIds = [...new Set(result)];
	};

	const getSelectionInsideContent = () => {
		if (!contentContainerElement) {
			return null;
		}

		const selection = window.getSelection();
		if (!selection || selection.rangeCount === 0 || selection.toString().trim().length === 0) {
			return null;
		}

		const range = selection.getRangeAt(0);
		const commonAncestor = range.commonAncestorContainer;
		const selectionNode =
			commonAncestor.nodeType === Node.TEXT_NODE ? commonAncestor.parentElement : commonAncestor;

		if (!selectionNode || !contentContainerElement.contains(selectionNode)) {
			return null;
		}

		return { selection, range };
	};

	const updateButtonPosition = (event) => {
		const buttonsContainerElement = document.getElementById(`floating-buttons-${id}`);
		const eventTarget = event?.target;
		if (
			eventTarget &&
			!contentContainerElement?.contains(eventTarget) &&
			!buttonsContainerElement?.contains(eventTarget)
		) {
			closeFloatingButtons();
			return;
		}

		setTimeout(async () => {
			await tick();

			const selectionState = getSelectionInsideContent();

			if (selectionState) {
				const { selection, range } = selectionState;
				const rect = range.getBoundingClientRect();

				const parentRect = contentContainerElement.getBoundingClientRect();
				selectedFloatingText = selection.toString();

				// Adjust based on parent rect
				const top = rect.bottom - parentRect.top;
				const left = rect.left - parentRect.left;

				if (buttonsContainerElement) {
					buttonsContainerElement.style.display = 'block';

					// Calculate space available on the right
					const spaceOnRight = parentRect.width - left;
					let halfScreenWidth = $mobile ? window.innerWidth / 2 : window.innerWidth / 3;

					if (spaceOnRight < halfScreenWidth) {
						const right = parentRect.right - rect.right;
						buttonsContainerElement.style.right = `${right}px`;
						buttonsContainerElement.style.left = 'auto'; // Reset left
					} else {
						// Enough space, position using 'left'
						buttonsContainerElement.style.left = `${left}px`;
						buttonsContainerElement.style.right = 'auto'; // Reset right
					}
					buttonsContainerElement.style.top = `${top + 5}px`; // +5 to add some spacing
				}
			} else {
				closeFloatingButtons();
			}
		}, 0);
	};

	const closeFloatingButtons = () => {
		const buttonsContainerElement = document.getElementById(`floating-buttons-${id}`);
		if (buttonsContainerElement) {
			buttonsContainerElement.style.display = 'none';
		}

		if (floatingButtonsElement) {
			// check if closeHandler is defined

			if (typeof floatingButtonsElement?.closeHandler === 'function') {
				// call the closeHandler function
				floatingButtonsElement?.closeHandler();
			}
		}
		selectedFloatingText = '';
	};

	const openAddToNotesModal = (text) => {
		selectedTextForNotes = text ?? '';
		showAddToNotesModal = true;
	};

	const keydownHandler = (e) => {
		if (e.key === 'Escape') {
			closeFloatingButtons();
		}
	};

	// Reactive listener attachment: re-attaches when floatingButtons
	// transitions from false → true (e.g. when message.done flips).
	let listenersAttached = false;

	function attachListeners() {
		if (!listenersAttached && contentContainerElement) {
			contentContainerElement.addEventListener('mouseup', updateButtonPosition);
			contentContainerElement.addEventListener('keyup', updateButtonPosition);
			contentContainerElement.addEventListener('contextmenu', updateButtonPosition);
			document.addEventListener('mouseup', updateButtonPosition);
			document.addEventListener('keyup', updateButtonPosition);
			document.addEventListener('keydown', keydownHandler);
			listenersAttached = true;
		}
	}

	function detachListeners() {
		if (listenersAttached) {
			contentContainerElement?.removeEventListener('mouseup', updateButtonPosition);
			contentContainerElement?.removeEventListener('keyup', updateButtonPosition);
			contentContainerElement?.removeEventListener('contextmenu', updateButtonPosition);
			document.removeEventListener('mouseup', updateButtonPosition);
			document.removeEventListener('keyup', updateButtonPosition);
			document.removeEventListener('keydown', keydownHandler);
			listenersAttached = false;
		}
	}

	$: if (floatingButtons && contentContainerElement) {
		attachListeners();
	} else {
		detachListeners();
	}

	onDestroy(() => {
		detachListeners();
	});
</script>

<div bind:this={contentContainerElement}>
	{#if $settings?.renderMarkdownInAssistantMessages ?? true}
		<Markdown
			{id}
			content={model?.info?.meta?.capabilities?.citations == false
				? replaceOutsideCode(content, (segment) =>
						segment.replace(/\s*(\[(?:\d+(?:#[^,\]\s]+)?(?:,\s*\d+(?:#[^,\]\s]+)?)*)\])+/g, '')
					)
				: content}
			{model}
			{save}
			{preview}
			{done}
			{editCodeBlock}
			{topPadding}
			{sourceIds}
			{onSourceClick}
			{onTaskClick}
			{onSave}
			onUpdate={async (token) => {
				const { lang, text: code } = token;

				if (
					($settings?.detectArtifacts ?? true) &&
					(['html', 'svg'].includes(lang) || (lang === 'xml' && code.includes('svg'))) &&
					!$mobile &&
					$chatId
				) {
					await tick();
					showArtifacts.set(true);
					showControls.set(true);
				}
			}}
			onPreview={async (value) => {
				console.log('Preview', value);
				await artifactCode.set(value);
				await showControls.set(true);
				await showArtifacts.set(true);
				await showEmbeds.set(false);
			}}
		/>
	{:else}
		{@const extracted = extractDetailsBlocks(content)}

		{#if extracted.detailsContent}
			<!-- Render structural blocks (tool calls, reasoning, etc.) through Markdown -->
			<Markdown {id} content={extracted.detailsContent} {done} />
		{/if}
		{#if extracted.plainContent}
			<div class="whitespace-pre-wrap">{extracted.plainContent}</div>
		{/if}
	{/if}
</div>

{#if floatingButtons}
	<FloatingButtons
		bind:this={floatingButtonsElement}
		{id}
		actions={$settings?.floatingActionButtons ?? []}
		selectedText={selectedFloatingText}
		onAddToNotes={(text) => {
			openAddToNotesModal(text);
		}}
		onSetInputText={(text) => {
			onSetInputText(text);
			closeFloatingButtons();
		}}
	/>
{/if}

<AddToNotesModal
	bind:show={showAddToNotesModal}
	selection={selectedTextForNotes}
	onSaved={() => {
		selectedTextForNotes = '';
	}}
/>
