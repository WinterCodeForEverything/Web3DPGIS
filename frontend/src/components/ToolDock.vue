<script setup lang="ts">
import { computed } from 'vue'
import type { Model3D } from '@/api/types'
import { availableTools, type ToolDefinition } from '@/tools'
import IconButton from './IconButton.vue'

// The toolbar and the open tool's panel, the same in every viewer. Only one tool is open at a time;
// switching unmounts the previous panel, which then removes its handlers and drawings.
const props = defineProps<{ tools: ToolDefinition[]; model: Model3D | null; label?: string }>()
const active = defineModel<string | null>( 'active', { default: null } )

const shown = computed( () => availableTools( props.tools, props.model ) )
const open = computed( () => props.tools.find( t => t.id === active.value ) ?? null )

function toggle( id: string ) {
	active.value = active.value === id ? null : id
}
</script>

<template>
	<aside class="toolbar frost" :aria-label="label ?? 'Tools'">
		<template v-if="$slots.default">
			<slot />
			<hr />
		</template>
		<IconButton v-for="t in shown" :key="t.id" :icon="t.icon" :label="t.title" :on="active === t.id" @click="toggle( t.id )" />
	</aside>

	<section v-if="open" class="panel glass" :aria-label="open.title">
		<header class="row">
			<h2 style="margin: 0">{{ open.title }}</h2>
			<span class="spacer" />
			<button class="icon-circle" aria-label="Close tool" @click="active = null">✕</button>
		</header>
		<component :is="open.component" :key="open.id" />
	</section>
</template>

<style scoped>
/* one frosted column of icon buttons; the viewer's own options sit above a hairline, the tools below */
.toolbar { position: absolute; top: 12px; left: 12px; display: flex; flex-direction: column; gap: 2px; padding: 6px; z-index: 3; /* above the panel, so the names show over it */
	border-radius: var(--ds-rounded-lg); }
.toolbar hr { width: 28px; margin: 4px auto; border: none; border-top: 1px solid rgba(255, 255, 255, 0.16); }
.panel { position: absolute; top: 12px; left: 80px; width: 320px; max-height: calc(100% - 24px); overflow: auto; z-index: 2;
	border: 1px solid var(--ds-hairline); border-radius: var(--ds-rounded-lg); padding: 17px; display: flex; flex-direction: column; gap: 10px; }
</style>
