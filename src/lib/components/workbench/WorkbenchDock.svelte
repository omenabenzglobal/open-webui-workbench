<script lang="ts">
	import WorkspaceTree from './WorkspaceTree.svelte';
	import TerminalDeck from './TerminalDeck.svelte';
	import TaskMonitor from './TaskMonitor.svelte';

	// Panel visibility state
	let showWorkspaceTree = false;
	let showDeck = false;
	let activeDeckTab: 'terminal' | 'tasks' = 'terminal';
</script>

<div class="relative w-full h-full flex overflow-hidden">
	<!-- Left Side Panel: Workspace Tree -->
	{#if showWorkspaceTree}
		<div class="w-72 h-full flex-shrink-0 z-20 shadow-lg border-r border-gray-200 dark:border-gray-800 transition-all duration-200 ease-in-out">
			<WorkspaceTree />
		</div>
	{/if}

	<!-- Center Panel: Core Chat Surface & Bottom Deck -->
	<div class="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
		<!-- Main Chat Slot Surface -->
		<div class="flex-1 min-w-0 h-full relative overflow-hidden">
			<slot />

			<!-- Floating Workbench Control Bar (Top Right) -->
			<div class="absolute top-3 right-16 z-30 flex items-center gap-1.5 p-1 rounded-lg bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border border-gray-200 dark:border-gray-800 shadow-md">
				<!-- Toggle Workspace Tree Button -->
				<button
					class="flex items-center gap-1 px-2.5 py-1 text-xs rounded font-medium transition-colors {showWorkspaceTree ? 'bg-emerald-600 text-white shadow-sm' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}"
					on:click={() => (showWorkspaceTree = !showWorkspaceTree)}
					title="Toggle Workspace File Tree"
				>
					<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
					</svg>
					<span class="hidden md:inline">Workspace</span>
				</button>

				<!-- Toggle Terminal / Deck Button -->
				<button
					class="flex items-center gap-1 px-2.5 py-1 text-xs rounded font-medium transition-colors {showDeck ? 'bg-blue-600 text-white shadow-sm' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}"
					on:click={() => (showDeck = !showDeck)}
					title="Toggle Terminal & Tasks Deck"
				>
					<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
					</svg>
					<span class="hidden md:inline">Terminal</span>
				</button>
			</div>
		</div>

		<!-- Bottom Deck Panel: Terminal & Task Monitor -->
		{#if showDeck}
			<div class="h-72 w-full flex-shrink-0 z-20 border-t border-gray-200 dark:border-gray-800 flex flex-col bg-gray-950 shadow-2xl transition-all duration-200 ease-in-out">
				<!-- Deck Tabs Bar -->
				<div class="px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex items-center justify-between text-xs font-mono">
					<div class="flex items-center gap-2">
						<button
							class="px-2.5 py-1 rounded font-semibold transition-colors {activeDeckTab === 'terminal' ? 'bg-gray-800 text-emerald-400 border border-gray-700' : 'text-gray-400 hover:text-gray-200'}"
							on:click={() => (activeDeckTab = 'terminal')}
						>
							>_ Terminal
						</button>
						<button
							class="px-2.5 py-1 rounded font-semibold transition-colors {activeDeckTab === 'tasks' ? 'bg-gray-800 text-purple-400 border border-gray-700' : 'text-gray-400 hover:text-gray-200'}"
							on:click={() => (activeDeckTab = 'tasks')}
						>
							⚙ Tasks & Receipts
						</button>
					</div>

					<button
						class="p-1 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
						on:click={() => (showDeck = false)}
						title="Close deck"
					>
						<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>

				<!-- Deck Active View -->
				<div class="flex-1 overflow-hidden">
					{#if activeDeckTab === 'terminal'}
						<TerminalDeck />
					{:else if activeDeckTab === 'tasks'}
						<TaskMonitor />
					{/if}
				</div>
			</div>
		{/if}
	</div>
</div>
