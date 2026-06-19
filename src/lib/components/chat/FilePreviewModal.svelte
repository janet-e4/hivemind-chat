<script lang="ts">
	import { getContext } from 'svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	export let path = '';
	export let content: string | null = null;
	export let loading = false;
	export let error = '';
	export let onClose: () => void = () => {};

	const filename = path.split('/').pop() ?? path;
	const ext = filename.includes('.') ? filename.split('.').pop()?.toLowerCase() ?? '' : '';

	const isMarkdown = ext === 'md' || ext === 'mdx';
	const isCode = ['ts', 'tsx', 'js', 'jsx', 'py', 'sh', 'bash', 'json', 'yaml', 'yml', 'toml', 'css', 'html', 'svelte', 'vue', 'go', 'rs', 'rb', 'java', 'c', 'cpp', 'h'].includes(ext);

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			onClose();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onClose();
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y-no-static-element-interactions -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<div
	class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
	on:click={handleBackdropClick}
>
	<div
		class="relative flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-800 dark:bg-gray-950"
		role="dialog"
		aria-modal="true"
		aria-label={filename}
	>
		<header class="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 px-4 py-3 dark:border-gray-900">
			<div class="min-w-0 flex-1">
				<div class="truncate text-sm font-medium text-gray-900 dark:text-gray-100">{filename}</div>
				{#if path !== filename}
					<div class="truncate text-[11px] text-gray-500 dark:text-gray-400">{path}</div>
				{/if}
			</div>
			<button
				type="button"
				class="shrink-0 rounded-lg p-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 focus:outline-hidden focus:ring-2 focus:ring-gray-500/60 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
				aria-label={$i18n.t('Close')}
				on:click={onClose}
			>
				<XMark className="size-4" />
			</button>
		</header>

		<div class="min-h-0 flex-1 overflow-auto">
			{#if loading}
				<div class="flex items-center justify-center py-16">
					<Spinner className="size-6" />
				</div>
			{:else if error}
				<div class="px-4 py-8 text-center text-sm text-red-500">{error}</div>
			{:else if content === null}
				<div class="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('No content')}
				</div>
			{:else}
				<pre
					class="m-0 overflow-x-auto whitespace-pre-wrap break-words p-4 text-[12px] leading-relaxed {isCode || isMarkdown ? 'font-mono' : 'font-sans'} text-gray-800 dark:text-gray-200"
				>{content}</pre>
			{/if}
		</div>
	</div>
</div>
