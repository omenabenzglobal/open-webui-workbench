<script lang="ts">
	import { page } from '$app/stores';

	import Chat from '$lib/components/chat/Chat.svelte';
	import WorkbenchDock from '$lib/components/workbench/WorkbenchDock.svelte';
</script>

<WorkbenchDock>
	<Chat chatIdProp={$page.params.id} />
</WorkbenchDock>
