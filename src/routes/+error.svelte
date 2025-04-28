<script>
	import { page } from '$app/stores';
</script>

<div class=" bg-white dark:bg-gray-800">
	<div class=" flex h-full">
		<div class="m-auto my-10 dark:text-gray-300 text-3xl font-semibold">
			{$page.status}: {$page.error.message}
		</div>
	</div>
</div>
