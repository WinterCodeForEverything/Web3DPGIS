<script setup lang="ts">
import { onBeforeUnmount, onMounted, provide, ref, shallowRef, watch } from 'vue'
import { ApiError, api } from '@/api/client'
import type { Model3D } from '@/api/types'
import LabelEditor from '@/labels/LabelEditor.vue'
import LabelPopup from '@/labels/LabelPopup.vue'
import { labelHostKey } from '@/labels/host'
import { createLabelStore, labelStoreKey } from '@/labels/store'
import MeasurePanel from '@/measure/MeasurePanel.vue'
import { measureHostKey } from '@/measure/host'
import { drawLabels, threeLabelHost } from '@/modelviewer/labels'
import { threeMeasureHost } from '@/modelviewer/measure'
import { ModelViewer } from '@/modelviewer/viewer'

const props = defineProps<{ id: number }>()

const container = ref<HTMLDivElement>()
const model = shallowRef<Model3D | null>( null )
const viewer = shallowRef<ModelViewer | null>( null )
const progress = ref( 0 )
const ready = ref( false )
const error = ref( '' )
const autoRotate = ref( false )
const grid = ref( false )
const wireframe = ref( false )
// the open tool panel; each tool takes over clicks on the model while it is open
const activeTool = ref<'measure' | 'labels' | null>( null )
const toast = ref<{ message: string; kind: string } | null>( null )
let toastTimer: number | undefined
let removeLabels: ( () => void ) | undefined

function notify( message: string, kind: 'info' | 'error' = 'info' ) {
	toast.value = { message, kind }
	window.clearTimeout( toastTimer )
	toastTimer = window.setTimeout( () => { toast.value = null }, 4000 )
}

// labels use the same store, editor and popup as the map viewer; only drawing and picking are three.js-specific
const labels = createLabelStore( props.id )
provide( labelStoreKey, labels )
provide( labelHostKey, threeLabelHost( viewer, model, notify ) )
// measuring uses the same panel, maths and saved measurements as the map viewer
provide( measureHostKey, threeMeasureHost( viewer, model, notify ) )

function toggleTool( tool: 'measure' | 'labels' ) {
	activeTool.value = activeTool.value === tool ? null : tool
}

onMounted( async () => {
	try {
		model.value = await api.model( props.id )
		if ( model.value.status !== 'ready' || !model.value.tileset_url ) {
			error.value = `This model is ${model.value.status}; it can be viewed once processing has finished.`
			return
		}
		viewer.value = new ModelViewer( container.value!, model.value.tileset_url, {
			heightOffset: model.value.height_offset,
			onProgress: fraction => { progress.value = fraction },
			onReady: () => { ready.value = true },
			onError: message => { error.value = `Could not load the model: ${message}` },
		} )
		removeLabels = drawLabels( viewer.value, labels )
		void labels.reload()
	} catch ( e ) {
		error.value = e instanceof ApiError && e.status === 404 ? 'Model not found, or you do not have access to it.' : `Could not load the model: ${e instanceof Error ? e.message : e}`
	}
} )

onBeforeUnmount( () => {
	activeTool.value = null
	removeLabels?.()
	viewer.value?.dispose()
	window.clearTimeout( toastTimer )
} )

watch( autoRotate, on => viewer.value?.setAutoRotate( on ) )
watch( grid, on => viewer.value?.setGrid( on ) )
watch( wireframe, on => viewer.value?.setWireframe( on ) )
</script>

<template>
	<div class="viewer-page">
		<div ref="container" class="stage" />

		<aside v-if="viewer" class="toolbar" aria-label="View options">
			<button @click="viewer.resetView()">Reset view</button>
			<button :class="{ on: autoRotate }" :aria-pressed="autoRotate" @click="autoRotate = !autoRotate">Rotate</button>
			<button :class="{ on: grid }" :aria-pressed="grid" @click="grid = !grid">Grid</button>
			<button :class="{ on: wireframe }" :aria-pressed="wireframe" @click="wireframe = !wireframe">Wireframe</button>
			<button :class="{ on: activeTool === 'measure' }" :aria-pressed="activeTool === 'measure'" @click="toggleTool( 'measure' )">Measure</button>
			<button v-if="model?.can_edit" :class="{ on: activeTool === 'labels' }" :aria-pressed="activeTool === 'labels'" @click="toggleTool( 'labels' )">Labels</button>
		</aside>

		<section v-if="viewer && activeTool" class="panel" :aria-label="activeTool === 'measure' ? 'Measure' : 'Labels'">
			<header class="row">
				<h2 style="margin: 0">{{ activeTool === 'measure' ? 'Measure' : 'Labels' }}</h2>
				<span class="spacer" />
				<button class="link" aria-label="Close tool" @click="activeTool = null">✕</button>
			</header>
			<MeasurePanel v-if="activeTool === 'measure'" />
			<LabelEditor v-else />
		</section>

		<LabelPopup v-if="viewer" />

		<div v-if="viewer && !ready && !error" class="loading" role="status">
			Loading model… {{ Math.round( progress * 100 ) }}%
			<div class="progress"><div :style="{ width: progress * 100 + '%' }" /></div>
		</div>
		<p v-if="viewer" class="hint">Drag to rotate · right-drag to pan · scroll to zoom</p>

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
.stage { position: absolute; inset: 0; overflow: hidden; }
.toolbar { position: absolute; top: 12px; left: 12px; display: flex; flex-direction: column; gap: 6px; z-index: 2; }
.toolbar button { min-width: 96px; justify-content: center; background: rgba(27, 31, 39, 0.85); color: #fff; border-color: transparent; }
.toolbar button.on { background: var(--accent); }
.panel { position: absolute; top: 12px; left: 124px; width: 320px; max-height: calc(100% - 24px); overflow: auto; z-index: 2;
	background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2; width: 220px; text-align: center;
	background: rgba(27, 31, 39, 0.85); color: #fff; padding: 10px 14px; border-radius: 6px; font-size: 14px; display: flex; flex-direction: column; gap: 8px; }
.hint { position: absolute; bottom: 30px; right: 12px; margin: 0; z-index: 2; color: #c8ccd4; font-size: 13px; }
.title { position: absolute; bottom: 30px; left: 12px; z-index: 2; background: rgba(27, 31, 39, 0.75); color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 14px; }
.title .muted { color: #c8ccd4; }
.overlay { position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%); z-index: 3; }
.toast { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 4; padding: 8px 14px; border-radius: 6px; background: rgba(27, 31, 39, 0.9); color: #fff; font-size: 14px; }
.toast.error { background: var(--danger); }
</style>
