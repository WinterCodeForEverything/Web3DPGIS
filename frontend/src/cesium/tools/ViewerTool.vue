<script setup lang="ts">
import { ref } from 'vue'
import IconButton from '@/components/IconButton.vue'
import type { IconName } from '@/icons'
import FlightTool from './FlightTool.vue'
import WalkTool from './WalkTool.vue'

// Ways of moving through the model: replay or record a camera tour (Flight), or walk on its surface (Walk).
// Only the chosen mode is mounted, so switching modes ends the other one and cleans up its session.
const MODES = [
	{ id: 'flight', title: 'Flight', icon: 'flight', component: FlightTool, hint: 'Replay saved camera tours, or record one.' },
	{ id: 'walk', title: 'Walk', icon: 'walk', component: WalkTool, hint: 'Walk on the model at eye height.' },
] as const satisfies readonly { id: string; title: string; icon: IconName; component: unknown; hint: string }[]
type Mode = typeof MODES[number]

const mode = ref<Mode | null>( null )
</script>

<template>
	<div class="segmented" role="radiogroup" aria-label="Viewer mode">
		<IconButton v-for="m in MODES" :key="m.id" :icon="m.icon" :label="m.title" tip="below" :class="{ on: mode?.id === m.id }"
			role="radio" :aria-checked="mode?.id === m.id" @click="mode = m" />
	</div>
	<template v-if="mode">
		<div class="mode">
			<strong>{{ mode.title }}</strong>
			<p class="muted">{{ mode.hint }}</p>
		</div>
		<component :is="mode.component" :key="mode.id" />
	</template>
	<p v-else class="muted">Choose a viewer mode: Flight or Walk.</p>
</template>

<style scoped>
.mode { display: flex; flex-direction: column; gap: 2px; }
.mode strong { font-size: 14px; font-weight: 600; letter-spacing: -0.224px; }
p { margin: 0; font-size: 14px; }
</style>
