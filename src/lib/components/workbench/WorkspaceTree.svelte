<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	interface TreeNode {
		name: string;
		path: string;
		is_dir: boolean;
		size?: number;
		modified_at?: number;
		children?: TreeNode[];
	}

	let rootNode: TreeNode | null = null;
	let loading = false;
	let searchQuery = '';
	let collapsedPaths: Record<string, boolean> = {};

	// Selected file state
	let selectedFile: { path: string; content: string; originalContent: string } | null = null;
	let isSaving = false;

	async function fetchTree() {
		loading = true;
		try {
			const res = await fetch('/api/v1/workbench/workspace/tree');
			if (!res.ok) {
				throw new Error(`Failed to load workspace tree: ${res.statusText}`);
			}
			rootNode = await res.json();
		} catch (e: any) {
			toast.error(e.message || 'Error fetching workspace tree');
		} finally {
			loading = false;
		}
	}

	function toggleCollapse(path: string) {
		collapsedPaths[path] = !collapsedPaths[path];
		collapsedPaths = { ...collapsedPaths };
	}

	async function openFile(path: string) {
		try {
			const res = await fetch(`/api/v1/workbench/workspace/file?path=${encodeURIComponent(path)}`);
			if (!res.ok) {
				const err = await res.json().catch(() => ({}));
				throw new Error(err.detail || 'Could not read file');
			}
			const data = await res.json();
			selectedFile = {
				path: data.path,
				content: data.content,
				originalContent: data.content
			};
		} catch (e: any) {
			toast.error(e.message || 'Error opening file');
		}
	}

	async function saveFile() {
		if (!selectedFile) return;
		isSaving = true;
		try {
			const res = await fetch('/api/v1/workbench/workspace/file', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					path: selectedFile.path,
					content: selectedFile.content
				})
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({}));
				throw new Error(err.detail || 'Save failed');
			}
			selectedFile.originalContent = selectedFile.content;
			toast.success(`Saved ${selectedFile.path}`);
			fetchTree();
		} catch (e: any) {
			toast.error(e.message || 'Failed to save file');
		} finally {
			isSaving = false;
		}
	}

	function closeEditor() {
		selectedFile = null;
	}

	function formatBytes(bytes?: number): string {
		if (!bytes || bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	function filterTree(node: TreeNode, query: string): boolean {
		if (!query) return true;
		if (node.name.toLowerCase().includes(query.toLowerCase())) return true;
		if (node.children) {
			return node.children.some((child) => filterTree(child, query));
		}
		return false;
	}

	onMount(() => {
		fetchTree();
	});
</script>

<div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 text-sm select-none">
	<!-- Header -->
	<div class="p-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
		<div class="flex items-center gap-2 font-semibold text-gray-700 dark:text-gray-200">
			<svg class="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
			</svg>
			<span>Workspace</span>
		</div>
		<button
			class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
			on:click={fetchTree}
			title="Refresh workspace tree"
		>
			<svg class="w-4 h-4 {loading ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
			</svg>
		</button>
	</div>

	<!-- Search -->
	<div class="p-2 border-b border-gray-200 dark:border-gray-800">
		<input
			type="text"
			bind:value={searchQuery}
			placeholder="Filter files..."
			class="w-full px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
		/>
	</div>

	<!-- Tree View -->
	<div class="flex-1 overflow-y-auto p-2 space-y-0.5">
		{#if loading && !rootNode}
			<div class="p-4 text-center text-xs text-gray-400">Loading files...</div>
		{:else if rootNode && rootNode.children && rootNode.children.length > 0}
			{#each rootNode.children as child}
				{#if filterTree(child, searchQuery)}
					{#if child.is_dir}
						<div>
							<div
								class="flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 font-medium"
								on:click={() => toggleCollapse(child.path)}
							>
								<svg class="w-3.5 h-3.5 transition-transform {collapsedPaths[child.path] ? '' : 'rotate-90'}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
								</svg>
								<svg class="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
									<path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
								</svg>
								<span class="truncate">{child.name}</span>
							</div>

							{#if !collapsedPaths[child.path] && child.children}
								<div class="pl-4 space-y-0.5 border-l border-gray-200 dark:border-gray-800 ml-3 mt-0.5">
									{#each child.children as subChild}
										{#if filterTree(subChild, searchQuery)}
											<div
												class="flex items-center justify-between px-2 py-1 rounded cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 group"
												on:click={() => openFile(subChild.path)}
											>
												<div class="flex items-center gap-1.5 truncate">
													<svg class="w-3.5 h-3.5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
													<span class="truncate">{subChild.name}</span>
												</div>
												<span class="text-[10px] text-gray-400 opacity-0 group-hover:opacity-100">
													{formatBytes(subChild.size)}
												</span>
											</div>
										{/if}
									{/each}
								</div>
							{/if}
						</div>
					{:else}
						<div
							class="flex items-center justify-between px-2 py-1 rounded cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 group"
							on:click={() => openFile(child.path)}
						>
							<div class="flex items-center gap-1.5 truncate">
								<svg class="w-3.5 h-3.5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
								<span class="truncate">{child.name}</span>
							</div>
							<span class="text-[10px] text-gray-400 opacity-0 group-hover:opacity-100">
								{formatBytes(child.size)}
							</span>
						</div>
					{/if}
				{/if}
			{/each}
		{:else}
			<div class="p-4 text-center text-xs text-gray-400">
				Workspace empty.<br />Files created by agents appear here.
			</div>
		{/if}
	</div>

	<!-- File Editor Drawer / Modal -->
	{#if selectedFile}
		<div class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
			<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-2xl w-full max-w-3xl flex flex-col max-h-[85vh] overflow-hidden">
				<!-- Modal Header -->
				<div class="px-4 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between bg-gray-50 dark:bg-gray-800/50">
					<div class="flex items-center gap-2">
						<svg class="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
						</svg>
						<span class="font-mono text-xs font-semibold text-gray-800 dark:text-gray-200">{selectedFile.path}</span>
						{#if selectedFile.content !== selectedFile.originalContent}
							<span class="w-2 h-2 rounded-full bg-amber-500" title="Modified"></span>
						{/if}
					</div>
					<div class="flex items-center gap-2">
						<button
							class="px-2.5 py-1 text-xs font-medium rounded bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50 transition-colors"
							disabled={isSaving}
							on:click={saveFile}
						>
							{isSaving ? 'Saving...' : 'Save File'}
						</button>
						<button
							class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 transition-colors"
							on:click={closeEditor}
						>
							<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
					</div>
				</div>

				<!-- Text Editor Body -->
				<div class="flex-1 p-2 bg-gray-950 font-mono text-xs text-gray-200 overflow-auto">
					<textarea
						bind:value={selectedFile.content}
						class="w-full h-full min-h-[400px] p-2 bg-transparent text-gray-200 focus:outline-none resize-none font-mono"
						spellcheck="false"
					></textarea>
				</div>
			</div>
		</div>
	{/if}
</div>
