<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { createEventDispatcher, getContext, onMount } from 'svelte';
    import { getLanguages, changeLanguage } from '$lib/i18n';

	import { flyAndScale } from '$lib/utils/transitions';
	import { goto } from '$app/navigation';
	import { fade, slide } from 'svelte/transition';

	const i18n = getContext('i18n');
    let languages: Awaited<ReturnType<typeof getLanguages>> = [];
    let lang = $i18n.language;

	export let show = false;
	export let className = 'max-w-[240px]';

	const dispatch = createEventDispatcher();

    onMount(async () => {
        languages = await getLanguages();
    })
</script>

<div class="flex hover:bg-gray-100 rounded-xl py-2 px-1 mx-2">
    <div class="max-w-[30px] max-h-[30px] object-cover rounded-full self-center mr-1.5 ml-2 bg-white p-1">
        <svg 
            xmlns="http://www.w3.org/2000/svg"
            fill="none" 
            viewBox="0 0 24 24"
            class="w-6 h-6 text-gray-800 dark:text-white" aria-hidden="true" 
            width="24" 
            height="24"
        >
            <path 
                stroke="currentColor" 
                stroke-linecap="round" 
                stroke-linejoin="round" 
                stroke-width="1.3" 
                d="m13 19 3.5-9 3.5 9m-6.125-2h5.25M3 7h7m0 0h2m-2 0c0 1.63-.793 3.926-2.239 5.655M7.5 6.818V5m.261 7.655C6.79 13.82 5.521 14.725 4 15m3.761-2.345L5 10m2.761 2.655L10.2 15"/>
        </svg>
    </div>
    <select
        class="dark:bg-gray-900 w-fit pr-8 rounded-sm py-2 px-2 font-medium outline-hidden text-left self-centered truncate cursor-pointer"
        bind:value={lang}
        on:change={(e) => {
            changeLanguage(lang);
        }}
    >
        {#each languages as language}
            <option value={language['code']}>
                {language['title']}
            </option>
        {/each}
    </select>
</div>
