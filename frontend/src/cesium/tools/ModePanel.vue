<script setup lang="ts">
import { ref, type Component } from 'vue'
import IconButton from '@/components/IconButton.vue'
import type { IconName } from '@/icons'

// A tool made of several modes (Viewer: Flight / Walk; Analyze: Sight line / Viewshed): a segmented switch on top,
// the chosen mode's panel below. Only the chosen mode is mounted, so switching ends the other and cleans up its session.
export interface ToolMode {
	id: string
	title: string
	icon: IconName
	component: Component
	/** One line under the mode's name saying what it is for. */
	hint: string
}

defineProps<{ label: string; prompt: string; modes: readonly ToolMode[] }>()
const mode = ref<ToolMode | null>( null )
</script>

<template>
	<div class="segmented" role="radiogroup" :aria-label="label">
		<IconButton v-for="m in modes" :key="m.id" :icon="m.icon" :label="m.title" tip="below" :class="{ on: mode?.id === m.id }"
			role="radio" :aria-checked="mode?.id === m.id" @click="mode = m" />
	</div>
	<template v-if="mode">
		<div class="mode">
			<strong>{{ mode.title }}</strong>
			<p class="muted">{{ mode.hint }}</p>
		</div>
		<component :is="mode.component" :key="mode.id" />
	</template>
	<p v-else class="muted">{{ prompt }}</p>
</template>

<style scoped>
.mode { display: flex; flex-direction: column; gap: 2px; }
.mode strong { font-size: 14px; font-weight: 600; letter-spacing: -0.224px; }
p { margin: 0; font-size: 14px; }
</style>
