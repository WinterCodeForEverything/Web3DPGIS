<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { VIEWERS, type ViewerKind } from '@/viewerChoice'

const props = defineProps<{ id: number; viewer: ViewerKind }>()
const router = useRouter()

// each viewer is its own chunk, so opening the 3D view never downloads Cesium and vice versa
const components = {
	model: defineAsyncComponent( () => import( './ThreeViewerView.vue' ) ),
	map: defineAsyncComponent( () => import( './MapViewerView.vue' ) ),
}

function chooseViewer( kind: ViewerKind ) {
	router.replace( { query: kind === VIEWERS[ 0 ].kind ? {} : { viewer: kind } } )
}
</script>

<template>
	<div class="model-page">
		<!-- keyed so switching tears the old viewer down completely before the new one starts -->
		<component :is="components[ props.viewer ]" :id="props.id" :key="props.viewer" />
		<div class="switcher frost" role="group" aria-label="Viewer">
			<button v-for="v in VIEWERS" :key="v.kind" :class="{ on: props.viewer === v.kind }" :aria-pressed="props.viewer === v.kind" :title="v.description" @click="chooseViewer( v.kind )">
				{{ v.title }}
			</button>
		</div>
	</div>
</template>

<style scoped>
.model-page { position: relative; height: 100%; }
/* a segmented pill: the frosted capsule holds one pill per viewer, the open one in Action Blue */
.switcher { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 5; display: flex; padding: 4px; gap: 2px;
	border-radius: var(--ds-pill); }
.switcher button { padding: 7px 18px; border-radius: var(--ds-pill); white-space: nowrap; }
</style>
