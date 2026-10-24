<script setup lang="ts">
import { computed } from 'vue'
import type { Model3D } from '@/api/types'
import { availableTools, type ToolDefinition } from '@/tools'

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
	<aside class="toolbar" :aria-label="label ?? 'Tools'">
		<slot />
		<button v-for="t in shown" :key="t.id" :class="{ on: active === t.id }" :aria-pressed="active === t.id" @click="toggle( t.id )">
			{{ t.title }}
		</button>
	</aside>

	<section v-if="open" class="panel" :aria-label="open.title">
		<header class="row">
			<h2 style="margin: 0">{{ open.title }}</h2>
			<span class="spacer" />
			<button class="link" aria-label="Close tool" @click="active = null">✕</button>
		</header>
		<component :is="open.component" :key="open.id" />
	</section>
</template>

<style scoped>
.toolbar { position: absolute; top: 12px; left: 12px; display: flex; flex-direction: column; gap: 6px; z-index: 2; }
.toolbar :deep( button ) { min-width: 96px; justify-content: center; background: rgba(27, 31, 39, 0.85); color: #fff; border-color: transparent; }
.toolbar :deep( button.on ) { background: var(--accent); }
.panel { position: absolute; top: 12px; left: 124px; width: 320px; max-height: calc(100% - 24px); overflow: auto; z-index: 2;
	background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; display: flex; flex-direction: column; gap: 10px; }
</style>
