<script lang="ts">
	export let result: Record<string, any>;

	$: workflow = result?.workflow ?? {};
	$: execution = result?.execution ?? {};
	$: outputs = Array.isArray(result?.outputs) ? result.outputs : [];
	$: errors = Array.isArray(result?.errors) ? result.errors : [];
	$: status = String(execution?.status ?? 'unknown').toLowerCase();
	$: statusClass =
		status === 'success'
			? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900'
			: status === 'error' || status === 'failed' || errors.length > 0
				? 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900'
				: status === 'running' || status === 'new' || status === 'waiting'
					? 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:ring-blue-900'
					: 'bg-gray-50 text-gray-700 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-800';

	function formatDate(value: unknown) {
		if (!value) return '';
		const date = new Date(String(value));
		if (Number.isNaN(date.getTime())) return String(value);
		return date.toLocaleString();
	}
</script>

<div
	class="rounded-lg border border-gray-200 bg-white p-3 text-sm shadow-sm dark:border-gray-800 dark:bg-gray-950"
>
	<div class="flex flex-wrap items-start justify-between gap-2">
		<div class="min-w-0">
			<div class="text-[10px] font-medium uppercase text-gray-400 dark:text-gray-500">
				n8n workflow
			</div>
			<div class="mt-0.5 truncate font-semibold text-gray-900 dark:text-gray-100">
				{workflow?.name ?? workflow?.id ?? 'Workflow'}
			</div>
		</div>
		<div class="rounded-full px-2 py-0.5 text-xs font-medium ring-1 {statusClass}">
			{status}
		</div>
	</div>

	{#if result?.summary}
		<p class="mt-2 text-gray-700 dark:text-gray-300">{result.summary}</p>
	{/if}

	<div class="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-400 sm:grid-cols-2">
		{#if execution?.id}
			<div>
				<span class="font-medium text-gray-500 dark:text-gray-500">Execution</span>
				<span class="ml-1 break-all">{execution.id}</span>
			</div>
		{/if}
		{#if execution?.started_at}
			<div>
				<span class="font-medium text-gray-500 dark:text-gray-500">Started</span>
				<span class="ml-1">{formatDate(execution.started_at)}</span>
			</div>
		{/if}
	</div>

	{#if errors.length > 0}
		<div
			class="mt-3 rounded-md bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300"
		>
			{#each errors as error}
				<div>{error?.message ?? JSON.stringify(error)}</div>
			{/each}
		</div>
	{/if}

	{#if outputs.length > 0}
		<div class="mt-3 space-y-1.5">
			{#each outputs.slice(0, 3) as output}
				<div
					class="rounded-md bg-gray-50 p-2 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-300"
				>
					{#if output?.node || output?.status}
						<div class="font-medium">
							{output?.node ?? 'n8n'}{#if output?.status}
								· {output.status}{/if}
						</div>
					{/if}
					{#if output?.data}
						<pre
							class="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono">{JSON.stringify(
								output.data,
								null,
								2
							)}</pre>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<div class="mt-3 flex flex-wrap gap-2 text-xs">
		{#if workflow?.url}
			<a
				class="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
				href={workflow.url}
				target="_blank"
				rel="noreferrer"
			>
				Open workflow
			</a>
		{/if}
		{#if execution?.url}
			<a
				class="font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
				href={execution.url}
				target="_blank"
				rel="noreferrer"
			>
				Open execution
			</a>
		{/if}
	</div>
</div>
