<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { VIEWERS, type ViewerKind } from '@/viewers'

const props = defineProps<{ id: number; viewer: ViewerKind }>()
const router = useRouter()

// each viewer is its own chunk, so opening the 3D view never downloads Cesium and vice versa
const components = {
	model: defineAsyncComponent( () => import( './ModelViewerView.vue' ) ),
	map: defineAsyncComponent( () => import( './ViewerView.vue' ) ),
}

function choose( kind: ViewerKind ) {
	router.replace( { query: kind === VIEWERS[ 0 ].kind ? {} : { viewer: kind } } )
}
</script>

<template>
	<div class="model-page">
		<!-- keyed so switching tears the old viewer down completely before the new one starts -->
		<component :is="components[ props.viewer ]" :id="props.id" :key="props.viewer" />
		<div class="switcher" role="group" aria-label="Viewer">
			<button v-for="v in VIEWERS" :key="v.kind" :class="{ on: props.viewer === v.kind }" :aria-pressed="props.viewer === v.kind" :title="v.description" @click="choose( v.kind )">
				{{ v.title }}
			</button>
		</div>
	</div>
</template>

<style scoped>
.model-page { position: relative; height: 100%; }
.switcher { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 5; display: flex; padding: 3px; gap: 2px;
	background: rgba(27, 31, 39, 0.85); border-radius: 8px; }
.switcher button { background: transparent; color: #fff; border-color: transparent; padding: 5px 12px; font-size: 14px; }
.switcher button.on { background: var(--accent); }
</style>
