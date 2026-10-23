<script setup lang="ts">
import type * as Cesium from 'cesium'
import { computed, markRaw, onBeforeUnmount, onMounted, provide, ref, shallowRef, type Component } from 'vue'
import { ApiError, api } from '@/api/client'
import type { Model3D } from '@/api/types'
import LabelPopup from '@/components/LabelPopup.vue'
import { createLabelLayer, labelLayerKey, type LabelLayer } from '@/viewer/labels'
import { createViewer, loadTileset, viewerKey, type ViewerContext } from '@/viewer/core'
import FlightTool from '@/viewer/tools/FlightTool.vue'
import HeightTool from '@/viewer/tools/HeightTool.vue'
import LabelTool from '@/viewer/tools/LabelTool.vue'
import MeasureTool from '@/viewer/tools/MeasureTool.vue'
import SightlineTool from '@/viewer/tools/SightlineTool.vue'
import ViewshedTool from '@/viewer/tools/ViewshedTool.vue'
import WalkTool from '@/viewer/tools/WalkTool.vue'

const props = defineProps<{ id: number }>()

interface ToolEntry { id: string; title: string; component: Component; editOnly?: boolean }
const TOOLS: ToolEntry[] = [
	{ id: 'measure', title: 'Measure', component: markRaw( MeasureTool ) },
	{ id: 'labels', title: 'Labels', component: markRaw( LabelTool ), editOnly: true },
	{ id: 'flight', title: 'Flight', component: markRaw( FlightTool ) },
	{ id: 'walk', title: 'Walk', component: markRaw( WalkTool ) },
	{ id: 'sightline', title: 'Sight line', component: markRaw( SightlineTool ) },
	{ id: 'viewshed', title: 'Viewshed', component: markRaw( ViewshedTool ) },
	{ id: 'height', title: 'Height', component: markRaw( HeightTool ), editOnly: true },
]

const container = ref<HTMLDivElement>()
const model = shallowRef<Model3D | null>( null )
const tileset = shallowRef<Cesium.Cesium3DTileset | null>( null )
const context = shallowRef<ViewerContext | null>( null )
const labelLayer = shallowRef<LabelLayer | null>( null )
const activeTool = ref<string | null>( null )
const error = ref( '' )
const toast = ref<{ message: string; kind: string } | null>( null )
let toastTimer: number | undefined

const tools = computed( () => TOOLS.filter( t => !t.editOnly || model.value?.can_edit ) )
const active = computed( () => TOOLS.find( t => t.id === activeTool.value ) ?? null )

function notify( message: string, kind: 'info' | 'error' = 'info' ) {
	toast.value = { message, kind }
	window.clearTimeout( toastTimer )
	toastTimer = window.setTimeout( () => { toast.value = null }, 4000 )
}

// provide() must run during setup; consumers only read these once the viewer exists
const contextProxy = {
	get viewer() { return context.value!.viewer },
	tileset,
	model: model as ViewerContext['model'],
	notify,
} as ViewerContext
provide( viewerKey, contextProxy )
provide( labelLayerKey, {
	get labels() { return labelLayer.value!.labels },
	get selected() { return labelLayer.value!.selected },
	reload: () => labelLayer.value!.reload(),
	destroy: () => labelLayer.value?.destroy(),
} as LabelLayer )

onMounted( async () => {
	try {
		model.value = await api.model( props.id )
		if ( model.value.status !== 'ready' || !model.value.tileset_url ) {
			error.value = `This model is ${model.value.status}; it can be viewed once processing has finished.`
			return
		}
		const viewer = createViewer( container.value! )
		context.value = { viewer, tileset, model: model as ViewerContext['model'], notify }
		labelLayer.value = createLabelLayer( viewer, model.value.id )
		void labelLayer.value.reload()
		tileset.value = await loadTileset( viewer, model.value.tileset_url, model.value.height_offset )
	} catch ( e ) {
		error.value = e instanceof ApiError && e.status === 404 ? 'Model not found, or you do not have access to it.' : `Could not load the model: ${e instanceof Error ? e.message : e}`
	}
} )

onBeforeUnmount( () => {
	activeTool.value = null
	labelLayer.value?.destroy()
	context.value?.viewer.destroy()
	window.clearTimeout( toastTimer )
} )

function toggle( id: string ) {
	// switching unmounts the previous tool panel, whose session then removes its handlers and drawings
	activeTool.value = activeTool.value === id ? null : id
}
</script>

<template>
	<div class="viewer-page">
		<div ref="container" class="globe" />

		<aside v-if="context" class="toolbar" aria-label="Tools">
			<button v-for="t in tools" :key="t.id" :class="{ on: activeTool === t.id }" :aria-pressed="activeTool === t.id" @click="toggle( t.id )">
				{{ t.title }}
			</button>
		</aside>

		<section v-if="context && active" class="panel" :aria-label="active.title">
			<header class="row">
				<h2 style="margin: 0">{{ active.title }}</h2>
				<span class="spacer" />
				<button class="link" aria-label="Close tool" @click="activeTool = null">✕</button>
			</header>
			<component :is="active.component" :key="active.id" />
		</section>

		<LabelPopup v-if="labelLayer" />

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
.toolbar { position: absolute; top: 12px; left: 12px; display: flex; flex-direction: column; gap: 6px; z-index: 2; }
.toolbar button { min-width: 96px; justify-content: center; background: rgba(27, 31, 39, 0.85); color: #fff; border-color: transparent; }
.toolbar button.on { background: var(--accent); }
.panel { position: absolute; top: 12px; left: 124px; width: 320px; max-height: calc(100% - 24px); overflow: auto; z-index: 2;
	background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.title { position: absolute; bottom: 30px; left: 12px; z-index: 2; background: rgba(27, 31, 39, 0.75); color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 14px; }
.title .muted { color: #c8ccd4; }
.overlay { position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%); z-index: 3; }
.toast { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 4; padding: 8px 14px; border-radius: 6px; background: rgba(27, 31, 39, 0.9); color: #fff; font-size: 14px; }
.toast.error { background: var(--danger); }
</style>
