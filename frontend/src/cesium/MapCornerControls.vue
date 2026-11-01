<script setup lang="ts">
import { inject, ref } from 'vue'
import IconButton from '@/components/IconButton.vue'
import HeightTool from './tools/HeightTool.vue'
import { mapViewerKey } from './mapViewer'

// The column of round buttons above Cesium's full-screen button: Height (owners only), then Reset view.
// Height opens its panel to the left of the column; closing it puts an unsaved height back.
defineProps<{ resetView: () => void }>()
const ctx = inject( mapViewerKey )!
const heightOpen = ref( false )
</script>

<template>
	<div class="corner" aria-label="View">
		<IconButton v-if="ctx.model.value.can_edit" class="round frost" icon="height" label="Height" tip="left" :on="heightOpen" @click="heightOpen = !heightOpen" />
		<IconButton class="round frost" icon="resetView" label="Reset view" tip="left" @click="resetView" />
	</div>
	<section v-if="heightOpen" class="panel glass height-panel" aria-label="Height">
		<header class="row">
			<h2 style="margin: 0">Height</h2>
			<span class="spacer" />
			<button class="icon-circle" aria-label="Close height" @click="heightOpen = false">✕</button>
		</header>
		<HeightTool />
	</section>
</template>

<style scoped>
/* lined up with Cesium's full-screen button (right 12px, bottom 30px, 36px) and stacked above it */
.corner { position: absolute; right: 12px; bottom: 74px; z-index: 3; display: flex; flex-direction: column; gap: 8px; }
.corner .round { width: 36px; height: 36px; border: none; border-radius: 50%; }
/* the same hover and chosen state as Cesium's buttons below */
.corner .round:hover, .corner .round.on { background: var(--ds-primary); }
.corner .round :deep(svg) { width: 22px; height: 22px; }
.height-panel { position: absolute; right: 60px; bottom: 30px; width: 280px; z-index: 2;
	border: 1px solid var(--ds-hairline); border-radius: var(--ds-rounded-lg); padding: 17px; display: flex; flex-direction: column; gap: 10px; }
</style>
