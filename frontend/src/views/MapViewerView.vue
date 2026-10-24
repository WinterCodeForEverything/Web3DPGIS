<script setup lang="ts">
import type * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { onBeforeUnmount, onMounted, provide, ref, shallowRef } from 'vue'
import { ApiError } from '@/api/http'
import { modelsApi } from '@/api/models'
import type { Model3D } from '@/api/types'
import LabelPopup from '@/labels/LabelPopup.vue'
import { labelHostKey } from '@/labels/labelHost'
import { createLabelStore, labelStoreKey } from '@/labels/labelStore'
import { cesiumLabelHost, drawLabels } from '@/cesium/labelLayer'
import { createMapViewer, loadTileset, mapViewerKey, type MapViewerContext } from '@/cesium/mapViewer'
import { MAP_TOOLS } from '@/cesium/tools'
import ToolDock from '@/components/ToolDock.vue'

const props = defineProps<{ id: number }>()

const container = ref<HTMLDivElement>()
const model = shallowRef<Model3D | null>( null )
const tileset = shallowRef<Cesium.Cesium3DTileset | null>( null )
const context = shallowRef<MapViewerContext | null>( null )
const labels = createLabelStore( props.id )
let removeLabels: ( () => void ) | undefined
const activeTool = ref<string | null>( null )
const error = ref( '' )
const toast = ref<{ message: string; kind: string } | null>( null )
let toastTimer: number | undefined

function notify( message: string, kind: 'info' | 'error' = 'info' ) {
	toast.value = { message, kind }
	window.clearTimeout( toastTimer )
	toastTimer = window.setTimeout( () => { toast.value = null }, 4000 )
}

// provide() must run during setup; consumers only read these once the viewer exists
const contextProxy = {
	get viewer() { return context.value!.viewer },
	tileset,
	model: model as MapViewerContext['model'],
	notify,
} as MapViewerContext
provide( mapViewerKey, contextProxy )
provide( labelStoreKey, labels )
provide( labelHostKey, cesiumLabelHost( contextProxy ) )

onMounted( async () => {
	try {
		model.value = await modelsApi.model( props.id )
		if ( model.value.status !== 'ready' || !model.value.tileset_url ) {
			error.value = `This model is ${model.value.status}; it can be viewed once processing has finished.`
			return
		}
		const viewer = createMapViewer( container.value! )
		context.value = { viewer, tileset, model: model as MapViewerContext['model'], notify }
		removeLabels = drawLabels( viewer, labels )
		void labels.reload()
		tileset.value = await loadTileset( viewer, model.value.tileset_url, model.value.height_offset )
	} catch ( e ) {
		error.value = e instanceof ApiError && e.status === 404 ? 'Model not found, or you do not have access to it.' : `Could not load the model: ${e instanceof Error ? e.message : e}`
	}
} )

onBeforeUnmount( () => {
	activeTool.value = null
	removeLabels?.()
	context.value?.viewer.destroy()
	window.clearTimeout( toastTimer )
} )

</script>

<template>
	<div class="viewer-page">
		<div ref="container" class="globe" />

		<ToolDock v-if="context" v-model:active="activeTool" :tools="MAP_TOOLS" :model="model" />

		<LabelPopup v-if="context" />

		<div v-if="model" class="title">
			<strong>{{ model.name }}</strong>
			<span class="muted"> · {{ model.owner }}</span>
		</div>
		<div v-if="error" class="overlay card"><p class="error">{{ error }}</p><RouterLink to="/">Back to models</RouterLink></div>
		<div v-if="toast" class="toast" :class="toast.kind" role="status">{{ toast.message }}</div>
	</div>
</template>

<style scoped>
.viewer-page { position: relative; height: 100%; }
.globe { position: absolute; inset: 0; }
.title { position: absolute; bottom: 30px; left: 12px; z-index: 2; background: rgba(27, 31, 39, 0.75); color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 14px; }
.title .muted { color: #c8ccd4; }
.overlay { position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%); z-index: 3; }
.toast { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 4; padding: 8px 14px; border-radius: 6px; background: rgba(27, 31, 39, 0.9); color: #fff; font-size: 14px; }
.toast.error { background: var(--danger); }
</style>
