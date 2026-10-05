<script lang="ts">
	import { tick } from 'svelte';
	import { toast } from 'svelte-sonner';

	interface CommandHistoryItem {
		command: string;
		stdout: string;
		stderr: string;
		exit_code: number;
		duration_ms: number;
		timestamp: string;
	}

	let commandInput = '';
	let isRunning = false;
	let history: CommandHistoryItem[] = [];
	let terminalScrollContainer: HTMLDivElement | null = null;

	const presetCommands = [
		'dir',
		'python --version',
		'git status',
		'python -m pytest backend/open_webui/apps/workbench/tests/ -v'
	];

	async function runCommand(cmdToRun?: string) {
		const targetCmd = (cmdToRun || commandInput).trim();
		if (!targetCmd || isRunning) return;

		isRunning = true;
		commandInput = '';

		try {
			const res = await fetch('/api/v1/workbench/terminal/exec', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					command: targetCmd,
					timeout: 30
				})
			});

			const data = await res.json();
			if (!res.ok) {
				throw new Error(data.detail || 'Execution error');
			}

			history = [
				...history,
				{
					command: targetCmd,
					stdout: data.stdout || '',
					stderr: data.stderr || '',
					exit_code: data.exit_code,
					duration_ms: data.duration_ms,
					timestamp: new Date().toLocaleTimeString()
				}
			];

			await tick();
			if (terminalScrollContainer) {
				terminalScrollContainer.scrollTop = terminalScrollContainer.scrollHeight;
			}
		} catch (e: any) {
			toast.error(e.message || 'Command execution failed');
			history = [
				...history,
				{
					command: targetCmd,
					stdout: '',
					stderr: e.message || 'Execution failed',
					exit_code: 1,
					duration_ms: 0,
					timestamp: new Date().toLocaleTimeString()
				}
			];
		} finally {
			isRunning = false;
		}
	}

	function clearTerminal() {
		history = [];
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			runCommand();
		}
	}
</script>

<div class="h-full flex flex-col bg-gray-950 text-gray-200 font-mono text-xs select-text">
	<!-- Terminal Deck Header -->
	<div class="px-3 py-2 border-b border-gray-800 flex items-center justify-between bg-gray-900/80">
		<div class="flex items-center gap-2">
			<span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
			<span class="font-semibold text-gray-300">Terminal Deck (AUTONOMOUS)</span>
		</div>
		<div class="flex items-center gap-2">
			<!-- Presets -->
			<div class="hidden sm:flex items-center gap-1 text-[11px]">
				{#each presetCommands as preset}
					<button
						class="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition-colors"
						on:click={() => runCommand(preset)}
						disabled={isRunning}
					>
						{preset.split(' ')[0]}
					</button>
				{/each}
			</div>
			<button
				class="p-1 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
				on:click={clearTerminal}
				title="Clear output"
			>
				<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Output Log Stream -->
	<div
		bind:this={terminalScrollContainer}
		class="flex-1 overflow-y-auto p-3 space-y-3 font-mono leading-relaxed"
	>
		{#if history.length === 0}
			<div class="text-gray-500 py-6 text-center">
				Terminal ready. Enter commands or let autonomous agents execute tasks.
			</div>
		{/if}

		{#each history as item}
			<div class="space-y-1">
				<div class="flex items-center justify-between text-gray-400">
					<div class="flex items-center gap-2">
						<span class="text-emerald-400">$</span>
						<span class="text-gray-200 font-semibold">{item.command}</span>
					</div>
					<div class="flex items-center gap-2 text-[10px]">
						<span class="px-1.5 py-0.2 rounded {item.exit_code === 0 ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'}">
							exit: {item.exit_code}
						</span>
						<span>{item.duration_ms}ms</span>
						<span class="text-gray-600">{item.timestamp}</span>
					</div>
				</div>

				{#if item.stdout}
					<pre class="whitespace-pre-wrap text-emerald-300/90 pl-3 border-l-2 border-emerald-600/30 overflow-x-auto">{item.stdout}</pre>
				{/if}

				{#if item.stderr}
					<pre class="whitespace-pre-wrap text-rose-300 pl-3 border-l-2 border-rose-600/40 overflow-x-auto">{item.stderr}</pre>
				{/if}
			</div>
		{/each}

		{#if isRunning}
			<div class="flex items-center gap-2 text-gray-400 animate-pulse">
				<span class="text-emerald-400">$</span>
				<span>Executing...</span>
			</div>
		{/if}
	</div>

	<!-- Command Input Prompt -->
	<div class="p-2 border-t border-gray-800 flex items-center gap-2 bg-gray-900">
		<span class="text-emerald-400 font-bold pl-1">$</span>
		<input
			type="text"
			bind:value={commandInput}
			on:keydown={handleKeyDown}
			placeholder="Enter shell command (e.g. dir, python test.py)..."
			disabled={isRunning}
			class="flex-1 bg-transparent text-gray-100 placeholder-gray-500 focus:outline-none font-mono text-xs"
		/>
		<button
			class="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded font-medium transition-colors"
			disabled={isRunning || !commandInput.trim()}
			on:click={() => runCommand()}
		>
			{isRunning ? 'Running...' : 'Run'}
		</button>
	</div>
</div>
