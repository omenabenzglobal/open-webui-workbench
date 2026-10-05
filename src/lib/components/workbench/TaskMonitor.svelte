<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	interface TaskSummary {
		task_id: string;
		title: string;
		status: string;
		prompt: string;
		current_step: number;
		step_limit: number;
		history_length: number;
		created_at: number;
		updated_at: number;
	}

	interface TaskDetail extends TaskSummary {
		history: Array<{
			role: string;
			content?: string;
			tool_calls?: any[];
			tool_call_id?: string;
		}>;
	}

	let tasks: TaskSummary[] = [];
	let loading = false;
	let selectedTaskId: string | null = null;
	let selectedTaskDetail: TaskDetail | null = null;
	let loadingDetail = false;

	// New task input
	let showNewTaskModal = false;
	let newPrompt = '';
	let newTitle = '';
	let newStepLimit = 0;
	let isCreating = false;

	let autoRefresh = true;
	let refreshInterval: any = null;

	async function fetchTasks() {
		loading = true;
		try {
			const res = await fetch('/api/v1/workbench/tasks?limit=30');
			if (res.ok) {
				tasks = await res.json();
			}
		} catch (e: any) {
			console.error('Failed to fetch tasks:', e);
		} finally {
			loading = false;
		}
	}

	async function selectTask(taskId: string) {
		selectedTaskId = taskId;
		loadingDetail = true;
		try {
			const res = await fetch(`/api/v1/workbench/tasks/${taskId}`);
			if (res.ok) {
				selectedTaskDetail = await res.json();
			}
		} catch (e: any) {
			toast.error('Failed to load task details');
		} finally {
			loadingDetail = false;
		}
	}

	async function createTask() {
		if (!newPrompt.trim() || isCreating) return;
		isCreating = true;
		try {
			const res = await fetch('/api/v1/workbench/tasks/create', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					prompt: newPrompt.trim(),
					title: newTitle.trim(),
					step_limit: newStepLimit
				})
			});
			if (!res.ok) {
				throw new Error('Failed to create task');
			}
			const created = await res.json();
			toast.success(`Task created: ${created.title || created.task_id}`);
			newPrompt = '';
			newTitle = '';
			showNewTaskModal = false;
			await fetchTasks();
			selectTask(created.task_id);
		} catch (e: any) {
			toast.error(e.message || 'Error creating task');
		} finally {
			isCreating = false;
		}
	}

	async function triggerRun(taskId: string) {
		try {
			const res = await fetch(`/api/v1/workbench/tasks/${taskId}/run`, {
				method: 'POST'
			});
			if (!res.ok) {
				throw new Error('Failed to schedule execution');
			}
			toast.success('Task execution scheduled');
			fetchTasks();
			if (selectedTaskId === taskId) {
				selectTask(taskId);
			}
		} catch (e: any) {
			toast.error(e.message || 'Error scheduling task');
		}
	}

	function getStatusColor(status: string): string {
		switch (status) {
			case 'COMPLETED':
				return 'bg-emerald-950 text-emerald-400 border border-emerald-800';
			case 'RUNNING':
				return 'bg-blue-950 text-blue-400 border border-blue-800 animate-pulse';
			case 'FAILED':
				return 'bg-rose-950 text-rose-400 border border-rose-800';
			case 'PAUSED':
				return 'bg-amber-950 text-amber-400 border border-amber-800';
			default:
				return 'bg-gray-800 text-gray-300 border border-gray-700';
		}
	}

	onMount(() => {
		fetchTasks();
		refreshInterval = setInterval(() => {
			if (autoRefresh) {
				fetchTasks();
				if (selectedTaskId) {
					selectTask(selectedTaskId);
				}
			}
		}, 4000);
	});

	onDestroy(() => {
		if (refreshInterval) clearInterval(refreshInterval);
	});
</script>

<div class="h-full flex flex-col bg-gray-950 text-gray-200 text-xs font-mono select-none">
	<!-- Header -->
	<div class="px-3 py-2 border-b border-gray-800 flex items-center justify-between bg-gray-900/80">
		<div class="flex items-center gap-2">
			<svg class="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
			</svg>
			<span class="font-semibold text-gray-300">Task Monitor</span>
		</div>
		<div class="flex items-center gap-2">
			<button
				class="px-2 py-1 rounded bg-purple-600 hover:bg-purple-700 text-white font-medium transition-colors"
				on:click={() => (showNewTaskModal = true)}
			>
				+ New Task
			</button>
			<button
				class="p-1 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
				on:click={fetchTasks}
				title="Refresh tasks"
			>
				<svg class="w-3.5 h-3.5 {loading ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Content Area: Split View -->
	<div class="flex-1 flex overflow-hidden">
		<!-- Task List Column -->
		<div class="w-1/3 border-r border-gray-800 overflow-y-auto p-2 space-y-1">
			{#if tasks.length === 0}
				<div class="p-4 text-center text-gray-500">No tasks created yet.</div>
			{/if}

			{#each tasks as task}
				<div
					class="p-2 rounded cursor-pointer border transition-colors {selectedTaskId === task.task_id ? 'bg-gray-800 border-purple-500' : 'bg-gray-900/50 border-gray-800 hover:bg-gray-800/60'}"
					on:click={() => selectTask(task.task_id)}
				>
					<div class="flex items-center justify-between gap-1 mb-1">
						<span class="font-semibold text-gray-200 truncate">{task.title || 'Untitled'}</span>
						<span class="px-1.5 py-0.2 rounded text-[10px] {getStatusColor(task.status)}">
							{task.status}
						</span>
					</div>
					<div class="text-[10px] text-gray-400 flex items-center justify-between">
						<span>Step: {task.current_step} / {task.step_limit === 0 ? '∞' : task.step_limit}</span>
						<span>{new Date(task.updated_at * 1000).toLocaleTimeString()}</span>
					</div>
				</div>
			{/each}
		</div>

		<!-- Task Detail View Column -->
		<div class="flex-1 overflow-y-auto p-3 select-text">
			{#if selectedTaskDetail}
				<div class="space-y-3">
					<div class="flex items-center justify-between pb-2 border-b border-gray-800">
						<div>
							<h3 class="font-bold text-gray-100 text-sm">{selectedTaskDetail.title}</h3>
							<p class="text-gray-400 text-[11px] mt-0.5">{selectedTaskDetail.prompt}</p>
						</div>
						<div class="flex items-center gap-2">
							<span class="px-2 py-0.5 rounded text-[11px] {getStatusColor(selectedTaskDetail.status)}">
								{selectedTaskDetail.status}
							</span>
							{#if selectedTaskDetail.status !== 'RUNNING'}
								<button
									class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
									on:click={() => triggerRun(selectedTaskDetail!.task_id)}
								>
									Run
								</button>
							{/if}
						</div>
					</div>

					<!-- Execution History -->
					<div class="space-y-2">
						<h4 class="font-semibold text-gray-300">Execution Receipts & Exchanges ({selectedTaskDetail.history.length})</h4>
						{#each selectedTaskDetail.history as item, idx}
							<div class="p-2 rounded bg-gray-900 border border-gray-800 space-y-1">
								<div class="flex items-center justify-between text-[11px] text-purple-400">
									<span class="font-bold uppercase">[{item.role}]</span>
									<span class="text-gray-500">#{idx + 1}</span>
								</div>

								{#if item.content}
									<pre class="whitespace-pre-wrap text-gray-300 font-mono text-[11px] overflow-x-auto">{item.content}</pre>
								{/if}

								{#if item.tool_calls}
									<div class="space-y-1 pt-1 border-t border-gray-800">
										<span class="text-[10px] text-amber-400 font-semibold">Tool Calls:</span>
										{#each item.tool_calls as tc}
											<div class="p-1 rounded bg-black/40 text-[10px] text-gray-300 font-mono">
												<span class="text-emerald-400 font-bold">{tc.function?.name}</span>({tc.function?.arguments})
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{:else}
				<div class="h-full flex items-center justify-center text-gray-500">
					Select a task on the left or create a new task to view state receipts.
				</div>
			{/if}
		</div>
	</div>

	<!-- Modal: Create Task -->
	{#if showNewTaskModal}
		<div class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
			<div class="bg-gray-900 border border-gray-800 rounded-lg p-4 w-full max-w-md space-y-3 shadow-2xl">
				<div class="flex items-center justify-between pb-2 border-b border-gray-800">
					<h3 class="font-bold text-gray-100 text-sm">New Autonomous Task</h3>
					<button class="text-gray-400 hover:text-gray-200" on:click={() => (showNewTaskModal = false)}>✕</button>
				</div>

				<div class="space-y-2">
					<div>
						<label class="block text-gray-400 text-[11px] mb-1">Title (optional)</label>
						<input
							type="text"
							bind:value={newTitle}
							placeholder="e.g. Factorial Script"
							class="w-full px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-purple-500"
						/>
					</div>

					<div>
						<label class="block text-gray-400 text-[11px] mb-1">Objective / Prompt</label>
						<textarea
							bind:value={newPrompt}
							rows="4"
							placeholder="Define the task objective for the autonomous agent..."
							class="w-full px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-purple-500 resize-none"
						></textarea>
					</div>

					<div>
						<label class="block text-gray-400 text-[11px] mb-1">Step Limit (0 = Unlimited Autonomous)</label>
						<input
							type="number"
							bind:value={newStepLimit}
							min="0"
							class="w-24 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-purple-500"
						/>
					</div>
				</div>

				<div class="flex justify-end gap-2 pt-2 border-t border-gray-800">
					<button
						class="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300"
						on:click={() => (showNewTaskModal = false)}
					>
						Cancel
					</button>
					<button
						class="px-3 py-1 rounded bg-purple-600 hover:bg-purple-700 text-white font-medium disabled:opacity-50"
						disabled={isCreating || !newPrompt.trim()}
						on:click={createTask}
					>
						{isCreating ? 'Creating...' : 'Create Task'}
					</button>
				</div>
			</div>
		</div>
	{/if}
</div>
